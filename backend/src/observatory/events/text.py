"""Safe text, RelPath and the versioned secret detectors (ADR-0008 §10).

The credential patterns and the CLI rules are owned here, independently of
``core.logging``; only ADR-0005's key rules and key/value scrub are reused.
Every pattern is possessive or bounded, so each scan is linear in its input.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from observatory.core.logging import REDACTED, is_secret_key, mask_key_values

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
_OPTION: Final = re.compile(rf"{_B}--?+(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*+)(?:=|\s++)(?=(?P<value>\S++))")
_USER: Final = re.compile(rf"{_B}(?:-u\s*+|--user(?:=|\s++))(?=(?P<value>\S++))")
_SET: Final = re.compile(rf"(?i){_B}set\s++(?P<name>[A-Za-z0-9_.-]++)\s++(?=(?P<value>\S++))")
_MYSQL_PASSWORD: Final = re.compile(r"(?<!\S)-p(?=(?P<value>\S++))")
_WORD: Final = re.compile(r"\S++")
_ASSIGNMENT: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*+=")
_MYSQL_COMMANDS: Final = frozenset({"mysql", "mysqldump", "mysqladmin", "mariadb", "mariadb-dump"})
#: Options of the wrappers skipped before the command word that take a separate argument (C6).
_WRAPPER_ARG_OPTIONS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "sudo": frozenset(
            {"-C", "-D", "-g", "-h", "-p", "-R", "-r", "-T", "-t", "-U", "-u"}
            | {"--close-from", "--chdir", "--group", "--host", "--prompt", "--chroot", "--role"}
            | {"--command-timeout", "--type", "--other-user", "--user"}
        ),
        "env": frozenset({"-a", "-C", "-P", "-S", "-u", "--argv0", "--chdir", "--split-string", "--unset"}),
    }
)


def _sub(pattern: str) -> Masker:
    regex = re.compile(pattern)
    return lambda text: regex.sub(REDACTED, text)


def _redact_spans(text: str, spans: Iterator[tuple[int, int]]) -> str:
    """Replace each span (in order of start; overlaps merge) with one ``[REDACTED]``."""
    out: list[str] = []
    pos = 0
    for start, end in spans:
        if start >= pos:
            out.append(text[pos:start])
            out.append(REDACTED)
        pos = max(pos, end)
    out.append(text[pos:])
    return "".join(out)


def _value_masker(regex: re.Pattern[str], accept: Callable[[re.Match[str]], bool]) -> Masker:
    def mask(text: str) -> str:
        spans = (
            m.span("value") for m in regex.finditer(text) if not m["value"].startswith(REDACTED) and accept(m)
        )
        return _redact_spans(text, spans)

    return mask


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


def _command_word(text: str) -> str | None:
    """Basename of the first word after ``sudo``/``env`` (with their options) and ``NAME=value`` (C6)."""
    words = (m.group() for m in _WORD.finditer(text))
    word = next(words, None)
    while word is not None:
        if _ASSIGNMENT.match(word):
            word = next(words, None)
            continue
        base = word.rsplit("/", 1)[-1]
        takes_argument = _WRAPPER_ARG_OPTIONS.get(base)
        if takes_argument is None:
            return base
        word = next(words, None)
        while word is not None and word.startswith("-"):
            end_of_options = word == "--"
            if word in takes_argument:
                next(words, None)
            word = next(words, None)
            if end_of_options:
                break
    return None


_mask_mysql_value = _value_masker(_MYSQL_PASSWORD, lambda _m: True)


def _mask_mysql_password(text: str) -> str:
    return _mask_mysql_value(text) if _command_word(text) in _MYSQL_COMMANDS else text


_mask_options = _value_masker(_OPTION, lambda m: is_secret_key(m["name"]))
_mask_user_password = _value_masker(_USER, lambda m: ":" in m["value"])
_mask_set = _value_masker(_SET, lambda m: is_secret_key(m["name"]))


@dataclass(frozen=True, slots=True)
class RuleSet:
    """One version of the secret rules: credential tier (every key and string) and text tier."""

    version: int
    unidata_version: str
    credential: tuple[Masker, ...]
    text: tuple[Masker, ...]

    def string_hit(self, value: str, *, text_tier: bool) -> bool:
        """True if ``value`` or its NFKC form hits the credential tier (and the text tier if asked)."""
        maskers = self.credential + self.text if text_tier else self.credential
        folded = unicodedata.normalize("NFKC", value)
        forms = (value,) if folded == value else (value, folded)
        return any(mask(form) != form for form in forms for mask in maskers)

    def key_hit(self, key: str, *, name_test: bool = True) -> bool:
        """True if ``key`` hits the credential tier or (with ``name_test``) is secret-named."""
        if self.string_hit(key, text_tier=False):
            return True
        return name_test and (is_secret_key(key) or is_secret_key(unicodedata.normalize("NFKC", key)))

    def sanitize(self, text: str) -> str:
        """Replace every match of both tiers with ``[REDACTED]``; the result is a scan fixed point (C5)."""
        out = text
        for _ in range(_MAX_SANITIZE_ROUNDS):
            for mask in self.credential + self.text:
                out = mask(out)
            if not self.string_hit(out, text_tier=True):
                return out
            out = unicodedata.normalize("NFKC", out)  # a hit only the NFKC form shows
        return REDACTED


_MAX_SANITIZE_ROUNDS: Final = 4

RULES_V1: Final = RuleSet(
    version=1,
    unidata_version="15.0.0",  # ADR-0008 C0: the Unicode data of the pinned Python 3.12
    credential=(_mask_pem, *(_sub(p) for p in _CREDENTIAL_PATTERNS), _mask_url_userinfo),
    text=(_mask_bearer, mask_key_values, _mask_options, _mask_mysql_password, _mask_user_password, _mask_set),
)


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
