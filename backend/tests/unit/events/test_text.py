"""Identifier, time, text, path and secret rules (ADR-0008 §§3, 6, 10; AO-P2-003 AC4).

Also covers clarifications C0 (pinned Unicode data), C1 (text tier at Id
positions), C5 (NFKC sanitising), C6 (CLI details) and C7 (extension depth).
"""

from __future__ import annotations

import json
import random
import time
import unicodedata

import pytest

from observatory.events import (
    SECRET_RULES,
    SECRET_RULES_VERSION,
    RejectCode,
    RuleSet,
    parse_event,
    sanitize_text,
)
from observatory.events.ids import (
    CODE_PATTERN,
    ID_PATTERN,
    PROVIDER_REF_PATTERN,
    SLUG_PATTERN,
    VERSION_PATTERN,
    WORKSPACE_ID_PATTERN,
    canonical_timestamp,
    matches,
    uuid_version,
)
from observatory.events.text import FORBIDDEN, FORBIDDEN_RANGES, is_rel_path
from tests.unit.events.factory import (
    AWS,
    BEARER,
    CREDENTIALS,
    GH,
    GH_PAT,
    GOOGLE,
    JWT,
    PEM,
    PEM_BODY,
    SK,
    SLACK,
    URL,
    accept,
    reject,
    tree,
)

RULES = SECRET_RULES[SECRET_RULES_VERSION]


def _hit(text: str, *, text_tier: bool = True) -> bool:
    return RULES.string_hit(text, text_tier=text_tier)


# --- C0: pinned Unicode data ---------------------------------------------------------------


def test_unidata_version_is_pinned() -> None:
    assert SECRET_RULES_VERSION == 1
    assert RULES.unidata_version == "15.0.0"
    assert unicodedata.unidata_version == RULES.unidata_version


def test_unknown_rules_version_is_a_value_error() -> None:
    for version in (0, 2, -1):
        with pytest.raises(ValueError, match="unknown"):
            SECRET_RULES[version]
        assert version not in SECRET_RULES
    assert list(SECRET_RULES) == [1]
    assert len(SECRET_RULES) == 1


# --- identifiers (§3) ------------------------------------------------------------------------

SCALARS = [
    (
        WORKSPACE_ID_PATTERN,
        ["ws-1", "a", "0" + "a" * 62],
        ["", "WS", "-ws", "ws_1", "a" * 64, "ws 1", "ws-1\n"],
    ),
    (
        ID_PATTERN,
        ["task-42", "coordinator:task-42", "h." + "0f" * 16, "A.b_c:d-e", "a" * 128],
        ["", ".x", "-x", "a b", "a/b", "a" * 129, "caf" + chr(0xE9), "a" + chr(0xFF41), "x\n", "../x"],
    ),
    (SLUG_PATTERN, ["claude-code", "ab"], ["a", "Claude", "1ab", "a_b", "a" * 33]),
    (
        VERSION_PATTERN,
        ["0.0.0", "1.2.3", "9999.9999.999999"],
        ["1.2", "01.2.3", "1.2.3-rc1", "v1.2.3", "1.2.3.4"],
    ),
    (PROVIDER_REF_PATTERN, ["msg_01/abc#1", "!" * 256], ["", "a b", "a" * 257, chr(0xE9), "a\tb"]),
    (CODE_PATTERN, ["rate_limited", "e.x-1"], ["", "Rate", "1x", "a b", "a" * 65]),
]


@pytest.mark.parametrize(("pattern", "good", "bad"), SCALARS)
def test_scalar_patterns(pattern: str, good: list[str], bad: list[str]) -> None:
    assert all(matches(pattern, value) for value in good)
    assert not any(matches(pattern, value) for value in bad)
    assert not matches(pattern, 5)


def test_uuid_rules() -> None:
    assert uuid_version("0190a8f2-6b1c-7d3e-8f4a-123456789abc") == 7
    assert uuid_version("4b1d6c1e-2f3a-4b5c-9d6e-7f8091a2b3c4") == 4
    bad = [
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "0190A8F2-6B1C-7D3E-8F4A-123456789ABC",
        "0190a8f2-6b1c-1d3e-8f4a-123456789abc",  # v1
        "0190a8f2-6b1c-6d3e-8f4a-123456789abc",  # v6
        "0190a8f2-6b1c-7d3e-cf4a-123456789abc",  # variant
        "0190a8f26b1c7d3e8f4a123456789abc",
        "{0190a8f2-6b1c-7d3e-8f4a-123456789abc}",
    ]
    assert [uuid_version(value) for value in bad] == [None] * len(bad)
    assert reject(tree(("event_id", bad[2]))).code is RejectCode.SCHEMA_VIOLATION


def test_malicious_identifiers_are_rejected_in_events() -> None:
    for value in ("../../etc", "a" * 129, "<script>", "x" + chr(0xFF0F) + "y", "1 OR 1=1"):
        rejected = reject(tree(("scope.task_id", value)))
        assert rejected.code is RejectCode.SCHEMA_VIOLATION
        assert rejected.pointer == "/scope/task_id"


# --- time (§6) ------------------------------------------------------------------------------------


def test_timestamps_canonicalise_losslessly() -> None:
    assert canonical_timestamp("2026-03-01T10:00:00Z") == "2026-03-01T10:00:00.000000Z"
    assert canonical_timestamp("2026-03-01T10:00:00.5Z") == "2026-03-01T10:00:00.500000Z"
    assert canonical_timestamp("2000-02-29T23:59:59.123456Z") == "2000-02-29T23:59:59.123456Z"
    event = accept(tree(("time.observed_at", "2099-12-31T23:59:59.1Z"))).event
    assert event.time.observed_at == "2099-12-31T23:59:59.100000Z"


@pytest.mark.parametrize(
    "value",
    [
        "2026-03-01T10:00:00+00:00",
        "2026-03-01T10:00:00",
        "2026-03-01T10:00:00z",
        "2026-03-01 10:00:00Z",
        "2026-03-01T10:00:60Z",
        "2026-02-30T10:00:00Z",
        "2026-13-01T10:00:00Z",
        "2026-03-01T24:00:00Z",
        "1999-12-31T23:59:59Z",
        "2100-01-01T00:00:00Z",
        "2026-03-01T10:00:00.1234567Z",
        "2026-03-01T10:00:00.Z",
        "2026-03-01T10:00:0" + chr(0x0661) + "Z",
        "2026-03-01T10:00:00Z\n",
    ],
)
def test_bad_timestamps(value: str) -> None:
    with pytest.raises(ValueError, match="timestamp"):
        canonical_timestamp(value)
    assert reject(tree(("time.observed_at", value))).code in {
        RejectCode.SCHEMA_VIOLATION,
        RejectCode.FORBIDDEN_CHARACTER,
    }


# --- forbidden characters and safe text (§10.2) ------------------------------------------------------


def test_every_forbidden_range_is_rejected() -> None:
    for low, high in FORBIDDEN_RANGES:
        for code_point in {low, high, (low + high) // 2}:
            assert FORBIDDEN.search(chr(code_point)), hex(code_point)
            rejected = reject(tree(("payload.session_id", "a" + chr(code_point))))
            assert rejected.code is RejectCode.FORBIDDEN_CHARACTER, hex(code_point)
    for allowed in ("\t", "\n", " ", "a", chr(0xE9), chr(0x4E2D), chr(0x1F600), chr(0xFFFD)):
        assert not FORBIDDEN.search(allowed)


def test_tab_and_lf() -> None:
    assert reject(tree(("scope.a\nb", 1))).code is RejectCode.FORBIDDEN_CHARACTER
    multi = {"x-acme": {"note": "line one\nline two"}}
    assert reject(tree(("extensions", multi))).code is RejectCode.SCHEMA_VIOLATION
    assert reject(tree(("extensions", {"x-acme": {"note": "a\tb"}}))).code is RejectCode.SCHEMA_VIOLATION


def test_markup_is_data() -> None:
    note = "<script>alert(1)</script> & <b>"
    event = accept(tree(("extensions", {"x-acme": {"note": note}}))).event
    assert event.extensions == {"x-acme": {"note": note}}


# --- RelPath (§10.5) --------------------------------------------------------------------------------

GOOD_PATHS = [
    "docs/Basic usage/getting-started-guide.md",
    "src/app.py",
    ".github/workflows/ci.yml",
    "a/" * 63 + "b",
    "x" * 1024,
    "..a/b..",
]
BAD_PATHS = [
    "/etc/passwd",
    "a//b",
    "a/",
    "./a",
    "a/../b",
    "~",
    "a/~/b",
    "a\\b",
    "a%2e%2e/b",
    "C:/x",
    "a:b",
    "a/" * 64 + "b",
    "x" * 1025,
    "a\nb",
    "",
    "a/" + chr(0xFF0E) * 2 + "/b",  # fullwidth dots fold to ".."
    "a" + chr(0xFF0F) + "b",  # fullwidth solidus folds to "/"
    "a" + chr(0xFE68) + "b",  # small reverse solidus folds to "\"
    "a/" + chr(0x200B) + "/b",
]


def test_rel_paths() -> None:
    assert all(is_rel_path(p) for p in GOOD_PATHS)
    assert not any(is_rel_path(p) for p in BAD_PATHS)


def test_paths_in_events() -> None:
    def changed(path: str) -> object:
        return tree(
            ("event_type", "file.changed"),
            ("payload", {"path": path, "change": "modified"}),
        )

    assert accept(changed("docs/Basic usage/getting-started-guide.md")).event.payload is not None
    for path in BAD_PATHS[:13]:
        assert reject(changed(path)).code is RejectCode.SCHEMA_VIOLATION, path
    same = tree(
        ("event_type", "file.changed"),
        ("payload", {"path": "a.py", "change": "renamed", "previous_path": "a.py"}),
    )
    assert (reject(same).code, reject(same).pointer) == (
        RejectCode.INVALID_REFERENCE,
        "/payload/previous_path",
    )


# --- detectors (§10.3) ----------------------------------------------------------------------------

CREDENTIAL_NEGATIVES = {
    "openai": ["task-42", "disk-" + "a" * 30, "sk-" + "short", "ask-" + "a" * 30],
    "github": ["gh" + "p_" + "A" * 35, "xgh" + "p_" + "A" * 36, "gh" + "x_" + "A" * 36],
    "github_pat": ["github_" + "pat_" + "A" * 21],
    "slack": ["xox" + "q-1234567890", "xox" + "b-123"],
    "aws": ["AK" + "IA" + "A" * 15, "AK" + "IA" + "A" * 17, "X" + "AKIA" + "A" * 16],
    "google": ["AI" + "za" + "C" * 34, "x" + "AIza" + "C" * 35],
    "jwt": ["ey" + "J" + "a" * 7 + ".eyJ" + "b" * 8 + ".c", "eyJhbGciOi"],
    "pem": ["-----BEGIN " + "PUBLIC KEY-----", "BEGIN " + "PRIVATE KEY"],
    "url": ["https://example.com/a:b@c", "ssh://git@host/x", "https://host/x?q=a:b"],
}


@pytest.mark.parametrize("name", CREDENTIALS)
def test_credential_detectors(name: str) -> None:
    credential = CREDENTIALS[name]
    for text in (credential, "prefix " + credential + " suffix", "id:" + credential):
        assert _hit(text, text_tier=False), name
    for text in CREDENTIAL_NEGATIVES[name]:
        assert not _hit(text, text_tier=False), text
    for path in ("scope.session_id", "payload.session_id", "scope.zz", "source.provider_event_id"):
        assert reject(tree((path, credential[:120]))).code is RejectCode.SECRET_DETECTED


def test_credential_tier_covers_keys() -> None:
    assert reject(tree(("payload." + GH, 1))).code is RejectCode.SECRET_DETECTED
    assert reject(tree(("extensions", {"x-acme": {"k": 1}}), ("scope." + AWS, 1))).pointer == "/scope"


def test_url_password_may_contain_a_slash() -> None:
    assert _hit(URL, text_tier=False)
    assert sanitize_text("clone " + URL) == "clone https://[REDACTED]@host.example/x"


def test_single_line_pem_body_never_survives() -> None:
    out = sanitize_text("key: " + PEM + " tail")
    assert out == "key: [REDACTED] tail"
    unterminated = sanitize_text("x " + PEM.split("\\n-----END")[0])
    assert unterminated == "x [REDACTED]"
    for text in (out, unterminated):
        assert not any(PEM_BODY[i : i + 4] in text for i in range(len(PEM_BODY) - 3))


TEXT_POSITIVES = [
    BEARER,
    "Authorization: basic " + "YWxpY2U6" + "c2VjcmV0cw==",
    "password" + "=" + "x",
    "'api_key': " + "'abc'",
    "--password " + "hunter",
    "-token " + "abc",
    "--api-key=" + "abc",
    "mysql -u root -p" + "hunter",
    "curl -u alice:" + "pw https://h",
    "curl -ualice:" + "pw https://h",
    "curl --user=alice:" + "pw https://h",
    "SET password " + "hunter",
    "redis-cli set auth " + "x",
]
TEXT_NEGATIVES = [
    "Basic authentication enabled",
    "bearer of bad news",
    "author: alice",
    "--verbose yes",
    "mysql -p",
    "echo mysql -phello",
    "mysqlx -phello",
    "curl -u alice https://h",
    "set color blue",
    "docs/Basic usage/getting-started-guide.md".replace("/", " "),
]


def test_text_detectors() -> None:
    for text in TEXT_POSITIVES:
        assert _hit(text), text
        assert not _hit(text, text_tier=False), text
    for text in TEXT_NEGATIVES:
        assert not _hit(text), text


def test_basic_path_is_not_a_hit_as_a_path_but_is_in_text() -> None:
    path = "docs/Basic usage/getting-started-guide.md"
    assert not _hit(path, text_tier=False)
    assert _hit(path)  # the text tier would over-mask it: paths never get that tier
    assert reject(tree(("extensions", {"x-acme": {"note": path}}))).code is RejectCode.SECRET_DETECTED


@pytest.mark.parametrize(
    "command",
    [
        "sudo -u root mysql -p" + "hunter",
        "sudo -g wheel -h host -u root /usr/bin/mysql -p" + "hunter",
        "sudo --user root mariadb -p" + "hunter",
        "sudo -E -- mysqldump -p" + "hunter",
        "env -i A=1 B=2 mysqladmin -p" + "hunter",
        "env -u HOME -C /tmp mariadb-dump -p" + "hunter",
        "env --unset HOME --chdir /tmp mysql -p" + "hunter",
        "sudo env -S x mysql -p" + "hunter",
        "MYSQL_HOST=db sudo -u root env -u X mysql -h db -p" + "hunter",
    ],
)
def test_mysql_rule_skips_sudo_and_env_options(command: str) -> None:
    assert _hit(command)
    assert sanitize_text(command).endswith("-p[REDACTED]")


def test_mysql_rule_needs_the_command_word() -> None:
    for command in ("sudo -u mysql ls -p" + "hunter", "env mysqlsh -p" + "hunter", "ls; mysql -p" + "hunter"):
        assert not _hit(command), command


def test_options_with_one_or_two_dashes() -> None:
    assert sanitize_text("tool -password a --token b --secret=c") == (
        "tool -password [REDACTED] --token [REDACTED] --secret=[REDACTED]"
    )
    assert sanitize_text("--password --token x") == "--password [REDACTED] [REDACTED]"  # spans merge
    assert sanitize_text("--max-tokens=5") == "--max-tokens=[REDACTED]"  # accepted over-masking


# --- the mandatory negative corpus and TD-026 ----------------------------------------------------------

NEGATIVE_CORPUS = [
    "task-1",
    "task-42",
    "risk-team",
    "disk-agent",
    "desk-ops",
    "coordinator:task-42",
    "h." + "0123456789abcdef" * 2,
    "0190a8f2-6b1c-7d3e-8f4a-123456789abc",
    "4b1d6c1e-2f3a-4b5c-9d6e-7f8091a2b3c4",
    "2026-03-01T10:00:00.000000Z",
    "2026-03-01T10:00:00Z",
]


def test_negative_corpus_passes_both_tiers() -> None:
    for value in [*NEGATIVE_CORPUS, "Basic authentication enabled"]:
        assert not _hit(value), value
        assert sanitize_text(value) == value
    for value in NEGATIVE_CORPUS[:7]:
        assert accept(tree(("scope.task_id", value))).event.scope.task_id == value
    note = {"x-acme": {"note": "Basic authentication enabled"}}
    assert accept(tree(("extensions", note))).event.extensions == note


def test_td026_id_shaped_like_a_secret_pair_is_accepted() -> None:
    value = "password" + ":x"
    assert accept(tree(("scope.task_id", value))).event.scope.task_id == value
    assert accept(tree(("scope.session_id", "sess:auth:42"), ("payload.session_id", "sess:auth:42")))
    assert accept(tree(("scope.task_id", "tokenizer:abc")))
    assert reject(tree(("extensions", {"x-acme": {"note": value}}))).code is RejectCode.SECRET_DETECTED


def test_c1_invalid_id_at_an_id_position_gets_the_text_tier() -> None:
    rejected = reject(tree(("scope.task_id", "password" + ": hunter")))
    assert (rejected.code, rejected.pointer) == (RejectCode.SECRET_DETECTED, "/scope")
    rejected = reject(
        tree(("event_type", "file.changed"), ("payload", {"path": "a b/--token x", "change": "x"}))
    )
    assert rejected.code is RejectCode.SCHEMA_VIOLATION  # a valid RelPath: text tier skipped
    bad_path = {"path": "/abs/--token x", "change": "created"}
    assert (
        reject(tree(("event_type", "file.changed"), ("payload", bad_path))).code is RejectCode.SECRET_DETECTED
    )
    assert reject(tree(("spec_version", "1.0 password=x"))).code is RejectCode.SECRET_DETECTED


# --- secret-named keys and the usage exemption ----------------------------------------------------------


def _usage(usage: object, event_type: str = "usage.recorded") -> object:
    payload = {"usage": usage, "accounting": "delta", "unit": "turn"}
    return tree(("event_type", event_type), ("payload", payload))


def test_usage_token_names_are_exempt_only_in_place() -> None:
    usage = {name: 5 for name in ("input_tokens", "output_tokens", "cached_input_tokens", "total_tokens")}
    usage["reasoning_tokens"] = 1
    assert accept(_usage(usage)).event.payload is not None
    denied = [
        _usage({"input_tokens": "5"}),
        _usage({"access_token": 5}),
        _usage({"input_tokens": True}),
        _usage({"input_tokens": 5}, "x-acme.usage"),
        tree(("scope.input_tokens", 5)),
        tree(("extensions", {"x-acme": {"input_tokens": 5}})),
        _usage({"nested": {"input_tokens": 5}}),
    ]
    for data in denied:
        assert reject(data).code is RejectCode.SECRET_DETECTED


@pytest.mark.parametrize("key", ["password", "Api-Key", "x-api-key", "clientSecret", "auth", "dsn", "COOKIE"])
def test_secret_named_keys_at_any_depth(key: str) -> None:
    for path in ("scope." + key, "payload." + key, key):
        assert reject(tree((path, 1))).code is RejectCode.SECRET_DETECTED
    nested = {"x-acme": {"a": {"b": [{key: 1}]}}}
    assert reject(tree(("extensions", nested))).pointer == "/extensions"


def test_nfkc_form_is_scanned_for_keys_and_values() -> None:
    fullwidth_password = "".join(chr(0xFF00 + ord(c) - 0x20) for c in "password")
    assert reject(tree(("scope." + fullwidth_password, 1))).code is RejectCode.SECRET_DETECTED
    fullwidth_sk = "".join(chr(0xFF00 + ord(c) - 0x20) for c in "sk-") + "a" * 24
    assert reject(tree(("scope.task_id", fullwidth_sk))).code is RejectCode.SECRET_DETECTED


# --- sanitize_text (§10.3, C5) -------------------------------------------------------------------------


def test_sanitize_replaces_every_match() -> None:
    for secret in [*CREDENTIALS.values(), BEARER]:
        out = sanitize_text("a " + secret + " b")
        assert "[REDACTED]" in out
        assert not _hit(out)
    assert sanitize_text("ok text") == "ok text"


def test_c5_nfkc_only_hit_sanitises_the_folded_form() -> None:
    fullwidth = "".join(chr(0xFF00 + ord(c) - 0x20) for c in "password") + "=x"
    assert not RULES.string_hit(fullwidth.replace("=x", ""), text_tier=False)
    assert sanitize_text("note " + fullwidth) == "note password=[REDACTED]"


def test_c5_never_settling_falls_back_to_whole_redaction() -> None:
    restless = RuleSet(version=99, unidata_version="15.0.0", credential=(lambda s: s + "!",), text=())
    assert restless.sanitize("anything") == "[REDACTED]"


FRAGMENTS = [
    *CREDENTIALS.values(),
    BEARER,
    "password=x",
    "--token abc",
    "mysql -pabc",
    "-u a:b",
    "set secret v",
    "task-42",
    "plain words",
    " ",
    "=",
    ":",
    "--",
    "[REDACTED]",
    chr(0xFF53) + chr(0xFF4B) + "-" + "z" * 22,
    chr(0xFDFA),
]


def test_sanitize_is_idempotent_and_a_scan_fixed_point() -> None:
    rng = random.Random(20261012)  # noqa: S311 (seeded test data, not cryptography)
    for _ in range(300):
        text = "".join(rng.choice(FRAGMENTS) for _ in range(rng.randint(1, 6)))
        once = sanitize_text(text)
        assert sanitize_text(once) == once, text
        assert not _hit(once), text


# --- linear time (§10.3) ----------------------------------------------------------------------------------

SIZE = 64 * 1024
WORST_CASES = {
    "nfkc expansion": chr(0xFDFA) * (SIZE // 3),
    "pem unterminated": "-----BEGIN " + "PRIVATE KEY-----" + "-----END " * (SIZE // 9),
    "pem headers": ("-----BEGIN " + "A" * 39) * (SIZE // 50),
    "sk prefixes": "sk-" * (SIZE // 3),
    "jwt dots": ("ey" + "J" + "a" * 8 + ".") * (SIZE // 12),
    "url tokens": "://a:" * (SIZE // 5),
    "url one token": "://" + ":" * SIZE,
    "bearer": "basic " * (SIZE // 6),
    "bearer spaces": "basic" + " " * SIZE,
    "key values": "password:" * (SIZE // 9),
    "options": "--password " * (SIZE // 11),
    "dashes": "-" * SIZE,
    "mysql words": "sudo -u " * (SIZE // 8),
    "set": "set " * (SIZE // 4),
    "user": "-u" * (SIZE // 2),
    "spaces": " " * SIZE,
}


@pytest.mark.parametrize("name", WORST_CASES)
def test_detectors_stay_linear_on_64_kib(name: str) -> None:
    text = WORST_CASES[name][:SIZE]
    start = time.perf_counter()
    RULES.string_hit(text, text_tier=True)
    RULES.sanitize(text)
    assert time.perf_counter() - start < 1.0


def test_whole_event_scan_of_64_kib_stays_fast() -> None:
    filler = chr(0xFDFA) * 20000  # 60000 bytes raw, 360000 code points under NFKC
    body = json.dumps(tree(("scope.zz", filler)), ensure_ascii=False).encode("utf-8")
    assert len(body) <= SIZE
    start = time.perf_counter()
    result = parse_event(body)
    assert time.perf_counter() - start < 1.0
    assert getattr(result, "code", None) is RejectCode.SCHEMA_VIOLATION


# --- extensions (§11, C7) ---------------------------------------------------------------------------


def test_extension_rules() -> None:
    ok = {"x-acme": {"a": {"b": {"c": [1, True, "s"]}}}, "x-other": {"n": 9007199254740991}}
    assert accept(tree(("extensions", ok))).event.extensions == ok
    bad = [
        {"x-acme": {"a": {"b": {"c": [[1]]}}}},  # depth 5: the namespace object is depth 1 (C7)
        {"x-acme": {}},
        {"acme": {"a": 1}},
        {"x-a": {"a": 1}},
        {f"x-n{i}": {"a": 1} for i in range(5)},
        {"x-acme": {"1a": 1}},
        {"x-acme": {"a-b": 1}},
        {"x-acme": {"a": [1] * 33}},
        {"x-acme": {"a": ""}},
        {"x-acme": {"a": "y" * 513}},
        {"x-acme": {"a": "y" * 500} | {f"k{i}": "y" * 500 for i in range(8)}},
        {"x-acme": "flat"},
    ]
    for extensions in bad:
        assert reject(tree(("extensions", extensions))).code is RejectCode.SCHEMA_VIOLATION, extensions


@pytest.mark.parametrize("word", ["prompt", "Completion", "content", "response", "body", "stdout", "stderr"])
def test_content_denylist(word: str) -> None:
    assert reject(tree(("extensions", {"x-acme": {"my_" + word: 1}}))).code is RejectCode.SCHEMA_VIOLATION
    assert reject(tree(("extensions", {"x-" + word.lower(): {"a": 1}}))).code is RejectCode.SCHEMA_VIOLATION
    vendor = tree(("event_type", "x-" + word.lower() + ".thing"), ("payload", {"a": 1}))
    assert (reject(vendor).code, reject(vendor).pointer) == (RejectCode.SCHEMA_VIOLATION, "/event_type")
    in_payload = tree(("event_type", "x-acme.thing"), ("payload", {"the_" + word: 1}))
    assert reject(in_payload).code is RejectCode.SCHEMA_VIOLATION


def test_extension_events() -> None:
    event = accept(tree(("event_type", "x-acme.build_step"), ("payload", {"step": "lint", "n": 2}))).event
    assert event.payload.model_dump() == {"step": "lint", "n": 2}
    for payload in ({}, {"a": {"b": {"c": {"d": [1]}}}}, {"big": ["y" * 500] * 17}, {"a": ""}):
        data = tree(("event_type", "x-acme.build_step"), ("payload", payload))
        assert reject(data).code is RejectCode.SCHEMA_VIOLATION
    assert reject(tree(("event_type", "x-acme.Bad"))).code is RejectCode.UNKNOWN_EVENT_TYPE


def test_extension_strings_get_the_text_tier() -> None:
    for value in (BEARER, "password" + "=x", "--token abc"):
        assert reject(tree(("extensions", {"x-acme": {"v": value}}))).code is RejectCode.SECRET_DETECTED
    assert reject(tree(("extensions", {"x-acme": {"v": [SK]}}))).pointer == "/extensions"


@pytest.mark.parametrize("secret", [GH, GH_PAT, SLACK, AWS, GOOGLE, JWT, SK, PEM, URL])
def test_every_secret_is_dropped_wherever_it_appears(secret: str) -> None:
    for data in (
        tree(("extensions", {"x-acme": {"v": secret[:500]}})),
        tree(("event_type", "x-acme.e"), ("payload", {"v": secret[:500]})),
        tree(("payload.initiator", secret)),
    ):
        assert reject(data).code is RejectCode.SECRET_DETECTED
