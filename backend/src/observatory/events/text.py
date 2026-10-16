"""Safe text, RelPath and the versioned secret detectors (ADR-0008 §10).

The credential patterns and the CLI rules are owned here, independently of
``core.logging``; only ADR-0005's key rules (``is_secret_key``, ``normalize_key``)
are reused. The text tier tokenises each string once and every pattern is
possessive or bounded, so each scan is linear in its input. Importing this
module fails if the Unicode data differs from the pinned version (C24).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from observatory.core.logging import REDACTED, is_secret_key, normalize_key

# --- forbidden characters (§10.2): a fixed, enumerated list ----------------------

#: Inclusive code point ranges (§10.2); enumerated, never derived from Unicode categories.
FORBIDDEN_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x9F),  # C0 except TAB and LF, DEL, C1
    (0xAD, 0xAD), (0x34F, 0x34F), (0x61C, 0x61C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2028, 0x2029), (0x2060, 0x206F),
    (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFFB),
    (0xFDD0, 0xFDEF), (0xD800, 0xDFFF), (0xE000, 0xF8FF), (0xE0000, 0xE0FFF), (0xF0000, 0x10FFFF),
    *((plane * 0x10000 + 0xFFFE, plane * 0x10000 + 0xFFFF) for plane in range(17)),
)  # fmt: skip
_FORBIDDEN_SET: Final = "".join(f"\\U{low:08x}-\\U{high:08x}" for low, high in FORBIDDEN_RANGES)
#: Forbidden in every string; TAB and LF are allowed here (a Text field rejects them as multi-line).
FORBIDDEN: Final = re.compile(f"[{_FORBIDDEN_SET}]")
#: Forbidden in every key: the set above plus TAB and LF.
FORBIDDEN_IN_KEY: Final = re.compile(f"[\\t\\n{_FORBIDDEN_SET}]")

_DOT_SEGMENTS: Final = frozenset({".", "..", "~"})
MAX_PATH_LENGTH: Final = 1024
MAX_PATH_SEGMENTS: Final = 64


def is_safe_line(value: str) -> bool:
    """True if ``value`` has no forbidden character, TAB or LF (single-line safe text)."""
    return FORBIDDEN_IN_KEY.search(value) is None


def is_rel_path(value: str) -> bool:
    """True if ``value`` is a RelPath (§10.5): workspace-relative, POSIX, no traversal."""
    if not 1 <= len(value) <= MAX_PATH_LENGTH or not is_safe_line(value):
        return False
    if value.startswith("/") or any(c in value for c in "\\%:"):
        return False  # ":" also rules out drive letters
    segments = value.split("/")
    if len(segments) > MAX_PATH_SEGMENTS:
        return False
    for segment in segments:
        folded = unicodedata.normalize("NFKC", segment)
        if not segment or segment in _DOT_SEGMENTS or folded in _DOT_SEGMENTS:
            return False
        if "/" in folded or "\\" in folded:
            return False
    return True


# --- detectors (§10.3) -------------------------------------------------------------

Masker = Callable[[str], str]

_B: Final = r"(?<![A-Za-z0-9_-])"  # left boundary
_PEM_HEAD: Final = r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY(?: BLOCK)?-----"
_PEM_END: Final = r"-----END [A-Z ]{0,40}PRIVATE KEY(?: BLOCK)?-----"
_PEM: Final = re.compile(rf"{_PEM_HEAD}(?:(?!{_PEM_END})[\s\S])*+(?:{_PEM_END})?")
_CREDENTIAL_PATTERNS: Final = (
    rf"{_B}sk-[A-Za-z0-9_-]{{20,}}+",
    rf"{_B}gh[pousr]_[A-Za-z0-9]{{36,}}+",
    rf"{_B}github_pat_[A-Za-z0-9_]{{22,}}+",
    rf"{_B}xox[abposr]-[A-Za-z0-9-]{{10,}}+",
    r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])",
    rf"{_B}AIza[A-Za-z0-9_-]{{35}}",
    rf"{_B}eyJ[A-Za-z0-9_-]{{8,}}+\.eyJ[A-Za-z0-9_-]{{8,}}+\.[A-Za-z0-9_-]*+",
)
_URL_TOKEN: Final = re.compile(r"://\S++")
_BEARER: Final = re.compile(r"(?i:bearer|basic)\s++[A-Za-z0-9._~+/-]{16,}+=*+")


def _sub(pattern: str) -> Masker:
    regex = re.compile(pattern)
    return lambda text: regex.sub(REDACTED, text)


def _redact_spans(text: str, spans: Iterable[Span]) -> str:
    """Replace each span (sorted by start; overlaps merge) with one ``[REDACTED]``."""
    out: list[str] = []
    pos = 0
    for start, end in spans:
        if start >= pos:
            out.append(text[pos:start])
            out.append(REDACTED)
        pos = max(pos, end)
    out.append(text[pos:])
    return "".join(out)


def _mask_pem(text: str) -> str:
    return _PEM.sub(REDACTED, text)


def _mask_url_userinfo(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group()[3:]
        at = token.rfind("@")
        colon = token.find(":")
        if 0 <= colon < at and "/" not in token[:colon]:
            return f"://{REDACTED}{token[at:]}"
        return match.group()

    return _URL_TOKEN.sub(replace, text)


def _mask_bearer(text: str) -> str:
    return _BEARER.sub(REDACTED, text)


# --- text tier (C18-C20): one key/value scan and one tokenisation per string ---------------------

Span = tuple[int, int]
Word = tuple[int, int, str]

#: A key at a token start, any horizontal whitespace, then ``=>``, ``=`` or ``:`` (C20).
_KV_KEY: Final = re.compile(r"""(?<![A-Za-z0-9_.-])(?P<key>[A-Za-z0-9_.-]++)['"]?[ \t]*+(?:=>|[:=])[ \t]*+""")
_DELIMITED: Final = r"""[^\s&,;'")\]}>]"""
_PLAIN_VALUE: Final = re.compile(rf"(?i:(?:bearer|basic|token|digest)[ \t]{{1,3}})?{_DELIMITED}++")
_REDACTED_TAIL: Final = re.compile(rf"{_DELIMITED}*+")
_LINE_VALUE: Final = re.compile(r"[^\n]*+")
#: After an opening quote: up to the matching unescaped quote, or to the end of the string (C19).
_QUOTED_REST: Final[Mapping[str, re.Pattern[str]]] = MappingProxyType(
    {quote: re.compile(rf"(?:[^{quote}\\]|\\[\s\S])*+{quote}?") for quote in ("'", '"')}
)
_LINE_VALUE_KEYS: Final = ("cookie", "authorization")
#: A shell-like word: quoted parts run to their closing quote; ``;``, ``|`` and ``&`` separate words.
_WORD: Final = re.compile(r"""(?:'(?:[^'\\]|\\[\s\S])*+'?|"(?:[^"\\]|\\[\s\S])*+"?|[^\s'";|&]++)++""")
_OPTION_HEAD: Final = re.compile(r"--?+(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*+)(?P<eq>=?)")
_MYSQL_COMMANDS: Final = frozenset({"mysql", "mysqldump", "mysqladmin", "mariadb", "mariadb-dump"})
#: The only values that count as already redacted (C18).
_EXACT_REDACTED: Final = frozenset({REDACTED, f"'{REDACTED}'", f'"{REDACTED}"'})


def _secret_name(name: str) -> bool:
    """Secret-named under ADR-0005, or a normalised name ending in ``pwd`` (C20)."""
    return is_secret_key(name) or normalize_key(name).endswith("pwd")


def _value_end(text: str, start: int, *, whole_line: bool) -> int:
    """End of the value that starts at ``start`` (C19 for quotes; ``[REDACTED]x`` is one value, C18)."""
    first = text[start : start + 1]
    if first in _QUOTED_REST:
        match = _QUOTED_REST[first].match(text, start + 1)
    elif text.startswith(REDACTED, start):
        match = _REDACTED_TAIL.match(text, start + len(REDACTED))
    elif whole_line:
        match = _LINE_VALUE.match(text, start)
    else:
        match = _PLAIN_VALUE.match(text, start)
    return match.end() if match is not None else start


def _key_value_spans(text: str) -> Iterator[Span]:
    """Values of secret-named keys written as text: ``password=x``, ``'api_key': 'x'``, ``MYSQL_PWD => x``."""
    pos = 0
    for match in _KV_KEY.finditer(text):
        if match.start() < pos or not _secret_name(match["key"]):
            continue
        whole_line = any(k in normalize_key(match["key"]) for k in _LINE_VALUE_KEYS)
        end = _value_end(text, match.end(), whole_line=whole_line)
        if end > match.end() and text[match.end() : end].rstrip() not in _EXACT_REDACTED:
            pos = end
            yield match.end(), end


def _option_spans(start: int, end: int, word: str, following: Word | None, *, redis: bool) -> Iterator[Span]:
    """``--name=value`` / ``--name value`` (one or two dashes): secret names, ``--user``, redis ``--pass``."""
    head = _OPTION_HEAD.match(word)
    if head is None:
        return
    if head.end() < len(word):
        if not head["eq"]:
            return
        value, text = (start + head.end(), end), word[head.end() :]
    elif following is not None and not head["eq"]:
        value, text = (following[0], following[1]), following[2]
    else:
        return
    name = head["name"]
    if _secret_name(name) or (name == "user" and ":" in text) or (redis and name == "pass"):
        yield value


def _ends_user_cluster(word: str) -> bool:
    """``-u`` alone or ending a short-option cluster (``-Eu``), so the next word is its value (C20)."""
    return word.startswith("-") and word.endswith("u") and word[1:].isascii() and word[1:].isalpha()


def _word_spans(text: str) -> Iterator[Span]:
    """The CLI rules of §10.3 and C20 over one tokenisation of ``text``."""
    words: list[Word] = [(m.start(), m.end(), m.group()) for m in _WORD.finditer(text)]
    names = {word.rsplit("/", 1)[-1] for _, _, word in words}
    mysql, sshpass, redis = bool(names & _MYSQL_COMMANDS), "sshpass" in names, "redis-cli" in names
    for index, (start, end, word) in enumerate(words):
        if word[0] != "-" and not (len(word) == 3 and word.lower() == "set"):
            continue  # every rule starts at an option word or at "set"
        following = words[index + 1] if index + 1 < len(words) else None
        yield from _option_spans(start, end, word, following, redis=redis)
        if following is not None:
            next_span = (following[0], following[1])
            if _ends_user_cluster(word) and ":" in following[2]:
                yield next_span  # -u user:pass, also a cluster ending in u: -Eu user:pass
            if (sshpass and word == "-p") or (redis and word == "-a"):
                yield next_span
            if word in ("-passin", "-passout") and following[2].startswith("pass:"):
                yield following[0] + len("pass:"), following[1]
            if word.lower() == "set" and _secret_name(following[2]) and index + 2 < len(words):
                yield words[index + 2][0], words[index + 2][1]
        attached = word[2:]
        if attached and (
            (word.startswith("-u") and ":" in attached)
            or (word.startswith("-p") and (mysql or sshpass))
            or (word.startswith("-a") and redis)
        ):
            yield start + 2, end


def _mask_text_tier(text: str) -> str:
    """Key/value and CLI values (C18-C20); a value that is exactly ``[REDACTED]`` is left alone."""
    spans = sorted(
        span
        for span in (*_key_value_spans(text), *_word_spans(text))
        if span[1] > span[0] and text[span[0] : span[1]] not in _EXACT_REDACTED
    )
    return _redact_spans(text, spans)


@dataclass(frozen=True, slots=True)
class RuleSet:
    """One version of the secret rules: credential tier (every key and string) and text tier."""

    version: int
    unidata_version: str
    credential: tuple[Masker, ...]
    text: tuple[Masker, ...]

    def string_hit(self, value: str, *, text_tier: bool) -> bool:
        """True if any scanned form of ``value`` hits the credential tier (and the text tier if asked)."""
        maskers = self.credential + self.text if text_tier else self.credential
        return any(mask(form) != form for form in scan_forms(value) for mask in maskers)

    def key_hit(self, key: str, *, name_test: bool = True) -> bool:
        """True if ``key`` hits the credential tier or (with ``name_test``) is secret-named in any form."""
        if self.string_hit(key, text_tier=False):
            return True
        return name_test and any(is_secret_key(form) for form in scan_forms(key))

    def sanitize(self, text: str) -> str:
        """Replace every match of both tiers with ``[REDACTED]``; the result is a scan fixed point (C5)."""
        out = text
        for _ in range(_MAX_SANITIZE_ROUNDS):
            for mask in self.credential + self.text:
                out = mask(out)
            if not self.string_hit(out, text_tier=True):
                return out
            out = unicodedata.normalize("NFKC", strip_forbidden(out))  # a hit only another form shows
        return REDACTED


def strip_forbidden(value: str) -> str:
    """C21: the §10.2 characters removed, and TAB and LF folded to a space."""
    return FORBIDDEN.sub("", value).replace("\t", " ").replace("\n", " ")


def scan_forms(value: str) -> tuple[str, ...]:
    """The forms every check runs on: the string, its NFKC form, its stripped form and that one's NFKC."""
    stripped = strip_forbidden(value)
    forms = dict.fromkeys(
        (value, unicodedata.normalize("NFKC", value), stripped, unicodedata.normalize("NFKC", stripped))
    )
    return tuple(forms)


_MAX_SANITIZE_ROUNDS: Final = 4


def check_unicode_data(actual: str = unicodedata.unidata_version) -> None:
    """C24: the rules are pinned to one Unicode data version; any other fails closed."""
    if actual != RULES_V1.unidata_version:
        raise ImportError(f"observatory.events needs Unicode data {RULES_V1.unidata_version}, found {actual}")


RULES_V1: Final = RuleSet(
    version=1,
    unidata_version="15.0.0",  # ADR-0008 C0: the Unicode data of the pinned Python 3.12
    credential=(_mask_pem, *(_sub(p) for p in _CREDENTIAL_PATTERNS), _mask_url_userinfo),
    text=(_mask_bearer, _mask_text_tier),
)


check_unicode_data()


class UnknownRulesVersion(KeyError, ValueError):
    """An unknown secret rules version (a ``ValueError`` that also satisfies the mapping protocol)."""


class _Rules(Mapping[int, RuleSet]):
    def __init__(self, rules: Mapping[int, RuleSet]) -> None:
        self._rules = dict(rules)

    def __getitem__(self, version: int) -> RuleSet:
        if type(version) is not int or version not in self._rules:
            raise UnknownRulesVersion("unknown secret rules version")
        return self._rules[version]

    def __iter__(self) -> Iterator[int]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)


#: The current rules version; accepting a new event always uses it.
SECRET_RULES_VERSION: Final = 1
#: Every rules version ever released, kept for replay (A-002).
SECRET_RULES: Final[Mapping[int, RuleSet]] = _Rules({1: RULES_V1})


def current_rules_version() -> int:
    """The current rules version (read at call time)."""
    return SECRET_RULES_VERSION


def rules_for(version: object) -> RuleSet:
    """The rule set of ``version``; ``ValueError`` if unknown (or not exactly an ``int``)."""
    if type(version) is not int:
        raise UnknownRulesVersion("unknown secret rules version")
    return SECRET_RULES[version]


def sanitize_text(text: str) -> str:
    """Replace every text-tier and credential-tier match with ``[REDACTED]`` (current rules)."""
    return rules_for(current_rules_version()).sanitize(text)
