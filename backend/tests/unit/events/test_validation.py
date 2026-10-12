"""Validation pipeline: every rejection code, its order and disposition, and the records (ADR-0008 §12).

AC1 (codes, order, dispositions), AC5 (no echo, no digest on drop records,
scan before quarantine), C2 (quarantine metadata), C3 and C8 (validate_event).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from observatory.events import (
    Accepted,
    Adapter,
    Disposition,
    Event,
    RejectCode,
    Rejected,
    WarningCode,
    parse_event,
    validate_event,
)
from observatory.events import envelope as envelope_module
from observatory.events.tree import format_pointer
from tests.unit.events.factory import (
    DELETE,
    EVENT_ID,
    PEM,
    SK,
    URL,
    accept,
    base_tree,
    raw,
    reject,
    tree,
)

DROP, QUARANTINE = Disposition.DROP, Disposition.QUARANTINE
V8_ID = "0190a8f2-6b1c-8d3e-8f4a-123456789abc"


def _parse(data: bytes) -> Rejected:
    result = parse_event(data)
    assert isinstance(result, Rejected), result
    return result


# --- AC1: each code with its disposition -------------------------------------------------

PARSE_CASES: list[tuple[str, bytes, RejectCode, Disposition]] = [
    ("too_large", b"{" + b" " * (64 * 1024) + b"}", RejectCode.TOO_LARGE, DROP),
    ("bom", b"\xef\xbb\xbf" + raw(base_tree()), RejectCode.INVALID_ENCODING, DROP),
    ("bad utf-8", b'{"a":"\xff"}', RejectCode.INVALID_ENCODING, DROP),
    ("encoded surrogate", b'{"a":"\xed\xa0\x80"}', RejectCode.INVALID_ENCODING, DROP),
    ("overlong", b'{"a":"\xc0\xaf"}', RejectCode.INVALID_ENCODING, DROP),
    ("too deep", b"[" * 17 + b"]" * 17, RejectCode.TOO_DEEP, DROP),
    ("syntax", b'{"a":}', RejectCode.INVALID_JSON, DROP),
    ("trailing comma", b'{"a":1,}', RejectCode.INVALID_JSON, DROP),
    ("two documents", b"{}{}", RejectCode.INVALID_JSON, DROP),
    ("raw control", b'{"a":"\x01"}', RejectCode.INVALID_JSON, DROP),
    ("duplicate", b'{"a":1,"a":2}', RejectCode.DUPLICATE_KEY, DROP),
    ("escaped duplicate", b'{"a":1,"\\u0061":2}', RejectCode.DUPLICATE_KEY, DROP),
    ("fraction", b'{"a":1.0}', RejectCode.FLOAT_NOT_ALLOWED, DROP),
    ("exponent", b'{"a":1e5}', RejectCode.FLOAT_NOT_ALLOWED, DROP),
    ("nan", b'{"a":NaN}', RejectCode.FLOAT_NOT_ALLOWED, DROP),
    ("infinity", b'{"a":-Infinity}', RejectCode.FLOAT_NOT_ALLOWED, DROP),
    ("17 digits", b'{"a":10000000000000000}', RejectCode.INTEGER_OUT_OF_RANGE, DROP),
    ("huge", b'{"a":' + b"9" * 5000 + b"}", RejectCode.INTEGER_OUT_OF_RANGE, DROP),
    ("2^53", b'{"a":9007199254740992}', RejectCode.INTEGER_OUT_OF_RANGE, DROP),
    ("-2^53", b'{"a":-9007199254740992}', RejectCode.INTEGER_OUT_OF_RANGE, DROP),
    ("minus zero", b'{"a":-0}', RejectCode.INTEGER_OUT_OF_RANGE, DROP),
    ("array", b"[]", RejectCode.NOT_AN_OBJECT, DROP),
    ("string", b'"x"', RejectCode.NOT_AN_OBJECT, DROP),
]


@pytest.mark.parametrize(
    ("name", "data", "code", "disposition"), PARSE_CASES, ids=[c[0] for c in PARSE_CASES]
)
def test_pre_scan_codes(name: str, data: bytes, code: RejectCode, disposition: Disposition) -> None:
    del name
    rejected = _parse(data)
    assert (rejected.code, rejected.disposition) == (code, disposition)
    assert rejected.raw_length == len(data)
    assert rejected.raw_sha256 is None


def test_limits_are_inclusive() -> None:
    assert parse_event(b"[" * 16 + b"]" * 16) == _parse(b"[" * 16 + b"]" * 16)
    assert _parse(b"[" * 16 + b"]" * 16).code is RejectCode.NOT_AN_OBJECT
    assert _parse(b'{"a":9007199254740991}').code is not RejectCode.INTEGER_OUT_OF_RANGE
    assert _parse(b'{"a":-9007199254740991}').code is not RejectCode.INTEGER_OUT_OF_RANGE
    padded = raw(base_tree())
    padded += b" " * (64 * 1024 - len(padded))
    assert isinstance(parse_event(padded), Accepted)
    assert _parse(padded + b" ").code is RejectCode.TOO_LARGE


def test_depth_prescan_ignores_brackets_in_strings() -> None:
    data = tree(("payload.initiator", "[" * 40))
    assert _parse(raw(data)).code is RejectCode.SCHEMA_VIOLATION
    assert _parse(b'{"a":"\\"' + b"[" * 20 + b'"}').code is not RejectCode.TOO_DEEP


EVENT_CASES: list[tuple[str, dict[str, Any], RejectCode, Disposition, str]] = [
    ("secret value", tree(("payload.session_id", SK)), RejectCode.SECRET_DETECTED, DROP, "/payload"),
    ("secret key", tree(("scope.api_key", "x")), RejectCode.SECRET_DETECTED, DROP, "/scope"),
    ("forbidden", tree(("scope.session_id", "a" + chr(0x200B) + "b")), RejectCode.FORBIDDEN_CHARACTER,
     QUARANTINE, "/scope/session_id"),
    ("forbidden key", tree(("scope.a\tb", "x")), RejectCode.FORBIDDEN_CHARACTER, QUARANTINE, "/scope"),
    ("newer minor", tree(("spec_version", "1.1")), RejectCode.UNSUPPORTED_VERSION, QUARANTINE,
     "/spec_version"),
    ("major", tree(("spec_version", "2.0")), RejectCode.UNSUPPORTED_VERSION, QUARANTINE, "/spec_version"),
    ("missing version", tree(("spec_version", DELETE)), RejectCode.UNSUPPORTED_VERSION, QUARANTINE,
     "/spec_version"),
    ("integer version", tree(("spec_version", 1)), RejectCode.UNSUPPORTED_VERSION, QUARANTINE,
     "/spec_version"),
    ("unknown type", tree(("event_type", "session.paused")), RejectCode.UNKNOWN_EVENT_TYPE, QUARANTINE,
     "/event_type"),
    ("bad extension type", tree(("event_type", "x-Acme.thing")), RejectCode.UNKNOWN_EVENT_TYPE, QUARANTINE,
     "/event_type"),
    ("missing type", tree(("event_type", DELETE)), RejectCode.UNKNOWN_EVENT_TYPE, QUARANTINE, "/event_type"),
    ("unknown field", tree(("scope.zz_unknown", "x")), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/scope"),
    ("bool seq", tree(("source.seq", True)), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/source/seq"),
    ("string seq", tree(("source.seq", "1")), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/source/seq"),
    ("negative seq", tree(("source.seq", -1)), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/source/seq"),
    ("seq alone", tree(("source.stream_id", DELETE)), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/source"),
    ("empty causality", tree(("causality", {})), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/causality"),
    ("empty extensions", tree(("extensions", {})), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/extensions"),
    ("bad timestamp", tree(("time.observed_at", "2026-03-01T10:00:01+00:00")), RejectCode.SCHEMA_VIOLATION,
     QUARANTINE, "/time/observed_at"),
    ("payload field", tree(("payload.zz", 1)), RejectCode.SCHEMA_VIOLATION, QUARANTINE, "/payload"),
    ("bare v8", tree(("event_id", V8_ID)), RejectCode.INVALID_REFERENCE, QUARANTINE, "/event_id"),
    ("underived", tree(("source.provider_event_id", "native-1")), RejectCode.INVALID_REFERENCE, QUARANTINE,
     "/event_id"),
    ("self cause", tree(("causality", {"causation_id": EVENT_ID})), RejectCode.INVALID_REFERENCE, QUARANTINE,
     "/causality/causation_id"),
]  # fmt: skip


@pytest.mark.parametrize(
    ("name", "data", "code", "disposition", "pointer"), EVENT_CASES, ids=[c[0] for c in EVENT_CASES]
)
def test_event_codes(
    name: str, data: dict[str, Any], code: RejectCode, disposition: Disposition, pointer: str
) -> None:
    del name
    for rejected in (_parse(raw(data)), reject(data)):
        assert (rejected.code, rejected.disposition, rejected.pointer) == (code, disposition, pointer)
        assert (rejected.raw_sha256 is None) == (disposition is DROP)


def test_canonical_size_check_is_quarantine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(envelope_module, "MAX_BYTES", 200)
    rejected = reject(base_tree())
    assert (rejected.code, rejected.disposition, rejected.pointer) == (RejectCode.TOO_LARGE, QUARANTINE, "")


def test_unexpected_exception_is_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_event: Event) -> None:
        raise RuntimeError(SK)

    monkeypatch.setattr(envelope_module, "_check_references", boom)
    for rejected in (_parse(raw(base_tree())), reject(base_tree())):
        assert (rejected.code, rejected.disposition, rejected.raw_sha256) == (
            RejectCode.INTERNAL_ERROR,
            DROP,
            None,
        )
        assert SK not in repr(rejected)
    not_bytes: Any = "{}"
    assert _parse(not_bytes).code is RejectCode.INTERNAL_ERROR


# --- AC1: the fixed order --------------------------------------------------------------------

ORDER_CASES: list[tuple[str, bytes, RejectCode]] = [
    ("size before encoding", b"\xff" * (64 * 1024 + 1), RejectCode.TOO_LARGE),
    ("encoding before depth", b"\xef\xbb\xbf" + b"[" * 20, RejectCode.INVALID_ENCODING),
    ("depth before syntax", b"[" * 17 + b"x", RejectCode.TOO_DEEP),
    ("syntax before duplicate", b'{"a":1,"a":2,}', RejectCode.INVALID_JSON),
    ("syntax after a float", b'{"a":1.5,"b":}', RejectCode.INVALID_JSON),
    ("duplicate before float", b'{"f":1.5,"a":1,"a":2}', RejectCode.DUPLICATE_KEY),
    ("float before integer", b'{"i":-0,"f":1.5}', RejectCode.FLOAT_NOT_ALLOWED),
    ("integer before object", b"[-0]", RejectCode.INTEGER_OUT_OF_RANGE),
]


@pytest.mark.parametrize(("name", "data", "code"), ORDER_CASES, ids=[c[0] for c in ORDER_CASES])
def test_parse_order(name: str, data: bytes, code: RejectCode) -> None:
    del name
    assert _parse(data).code is code


def test_event_check_order() -> None:
    every_failure = tree(
        ("payload.session_id", SK),  # 9
        ("scope.session_id", "a" + chr(0x202E) + "b"),  # 10
        ("spec_version", "9.9"),  # 11
        ("event_type", "nope"),  # 12
        ("scope.zz", 1),  # 13
        ("event_id", V8_ID),  # 14
    )
    expected = [
        RejectCode.SECRET_DETECTED,
        RejectCode.FORBIDDEN_CHARACTER,
        RejectCode.UNSUPPORTED_VERSION,
        RejectCode.UNKNOWN_EVENT_TYPE,
        RejectCode.SCHEMA_VIOLATION,
        RejectCode.INVALID_REFERENCE,
    ]
    fixes = [
        ("payload.session_id", "sess-1"),
        ("scope.session_id", "sess-1"),
        ("spec_version", "1.0"),
        ("event_type", "session.started"),
        ("scope.zz", DELETE),
        ("event_id", EVENT_ID),
    ]
    data = every_failure
    for code, fix in zip(expected, fixes, strict=True):
        assert reject(data).code is code
        data = tree(*[f for f in fixes[: fixes.index(fix) + 1]], *_remaining(every_failure, fixes, fix))
    assert isinstance(validate_event(data), Accepted)


def _remaining(
    broken: dict[str, Any], fixes: list[tuple[str, object]], done: tuple[str, object]
) -> list[tuple[str, object]]:
    later = fixes[fixes.index(done) + 1 :]
    out: list[tuple[str, object]] = []
    for path, _good in later:
        node: Any = broken
        for key in path.split("."):
            node = node[key]
        out.append((path, node))
    return out


def test_smallest_schema_pointer_wins() -> None:
    data = tree(("source.seq", "1"), ("scope.task_id", 5), ("payload.initiator", "robot"))
    assert reject(data).pointer == "/payload/initiator"
    data = tree(("source.seq", "1"), ("scope.task_id", 5))
    assert reject(data).pointer == "/scope/task_id"
    data = tree(("time.observed_at", 1), ("source.seq", "1"))
    assert reject(data).pointer == "/source/seq"


def test_long_pointer_is_cut_at_a_segment_boundary() -> None:
    pointer = format_pointer(tuple(["segment-" + str(i) for i in range(40)]))
    assert len(pointer) <= 256
    assert pointer.endswith("/…")
    assert format_pointer(("a/b", "c~d", 3)) == "/a~1b/c~0d/3"


def test_warnings_are_reported_not_stored() -> None:
    skewed = accept(tree(("time.occurred_at", "2026-03-01T10:05:02Z")))
    assert skewed.warnings == (WarningCode.OCCURRED_AFTER_OBSERVED,)
    assert accept(tree(("time.occurred_at", "2026-03-01T10:05:01Z"))).warnings == ()
    late = accept(tree(("time.occurred_at", "2026-01-01T00:00:00Z")))
    assert late.warnings == (WarningCode.LATE_OBSERVATION,)
    assert accept(tree(("time.occurred_at", DELETE))).warnings == ()
    assert "warning" not in json.dumps(late.event.model_dump())


# --- AC5: no echo, no digest on drop ------------------------------------------------------------

SECRET_EVENTS = [
    tree(("payload.session_id", SK)),
    tree(("scope.agent_id", "claude-code:" + SK)),
    tree(("extensions", {"x-acme": {"note": "see " + URL}})),
    tree(("scope.password", "hunter")),
    tree(("source.provider_event_id", PEM)),
    tree((SK, 1)),
]


@pytest.mark.parametrize("data", SECRET_EVENTS)
def test_secret_rejections_echo_nothing(data: dict[str, Any]) -> None:
    for rejected in (_parse(raw(data)), reject(data)):
        assert rejected.code is RejectCode.SECRET_DETECTED
        assert rejected.disposition is DROP
        assert rejected.raw_sha256 is None
        fields = dataclasses.asdict(rejected)
        assert {k for k, v in fields.items() if v is not None} == {
            "code",
            "pointer",
            "disposition",
            "raw_length",
        }
        for needle in (SK, URL.split("@")[0], "hunter", "password", "PRIVATE", "pa/ss"):
            assert needle not in repr(rejected)


def test_unknown_keys_are_never_echoed() -> None:
    key = "zz" + "unknownkey" + "zz"
    for data in (tree(("scope." + key, 1)), tree(("payload." + key, 1)), tree((key, 1))):
        rejected = reject(data)
        assert rejected.code is RejectCode.SCHEMA_VIOLATION
        assert key not in repr(rejected)
        assert rejected.pointer in {"", "/scope", "/payload"}


def test_scan_runs_before_every_quarantine_check() -> None:
    data = tree(
        ("scope.task_id", "a\u0000b"),
        ("spec_version", "7.0"),
        ("event_type", "nope"),
        ("source.seq", "x"),
        ("extensions", {"x-acme": {"key": "Bearer " + "z" * 30}}),
    )
    rejected = reject(data)
    assert (rejected.code, rejected.disposition, rejected.raw_sha256) == (
        RejectCode.SECRET_DETECTED,
        DROP,
        None,
    )


def test_construction_errors_echo_nothing() -> None:
    with pytest.raises(ValueError, match="secret_detected") as info:
        Event.model_validate(tree(("payload.session_id", SK)))
    assert SK not in str(info.value)


# --- C2: quarantine records ---------------------------------------------------------------------


def test_quarantine_record_keeps_only_valid_identity_fields() -> None:
    data = tree(("spec_version", "1.7"), ("source.provider_event_id", "native-1"))
    body = raw(data)
    rejected = _parse(body)
    assert rejected.code is RejectCode.UNSUPPORTED_VERSION
    assert rejected.raw_sha256 == "sha256:" + hashlib.sha256(body).hexdigest()
    assert rejected.raw_length == len(body)
    assert (rejected.workspace_id, rejected.event_id, rejected.event_type) == (
        "ws-1",
        EVENT_ID,
        "session.started",
    )
    assert (rejected.spec_version, rejected.provider, rejected.stream_id, rejected.seq) == (
        "1.7",
        "claude-code",
        "stream-a",
        0,
    )
    assert rejected.adapter == Adapter(name="cc-adapter", version="1.2.3")
    kept = dataclasses.asdict(rejected)
    assert "native-1" not in repr(kept)


def test_quarantine_record_omits_invalid_fields() -> None:
    data = tree(
        ("spec_version", "01.0"),
        ("scope.workspace_id", "WS"),
        ("event_type", "Session"),
        ("source.adapter.version", "v1"),
        ("source.provider", "P"),
        ("source.stream_id", "a b"),
        ("source.seq", -1),
        ("event_id", EVENT_ID.upper()),
    )
    rejected = reject(data)
    assert rejected.disposition is QUARANTINE
    assert [rejected.workspace_id, rejected.event_id, rejected.event_type, rejected.spec_version] == [
        None
    ] * 4
    assert [rejected.provider, rejected.adapter, rejected.stream_id, rejected.seq] == [None] * 4
    weird: dict[str, Any] = tree(("spec_version", "2.0"))
    weird["source"] = "not an object"
    assert reject(weird).adapter is None
    assert reject(tree(("spec_version", "2.0"), ("event_type", "x-acme.ping"))).event_type == "x-acme.ping"


# --- C3 and C8: validate_event ---------------------------------------------------------------------


class _Str(str):
    __slots__ = ()


class _Dict(dict[str, Any]):
    pass


def _cyclic() -> dict[str, Any]:
    data = base_tree()
    data["scope"]["self"] = data
    return data


def _shared() -> dict[str, Any]:
    leaf: list[object] = []
    data = base_tree()
    data["extensions"] = {"x-acme": {"a": leaf, "b": leaf}}
    return data


NOT_PLAIN = {
    "float": tree(("source.seq", 1.0)),
    "none at top": None,
    "tuple": tree(("extensions", {"x-acme": {"a": (1,)}})),
    "str subclass": tree(("payload.session_id", _Str("sess-1"))),
    "dict subclass": _Dict(base_tree()),
    "bytes": tree(("payload.session_id", b"sess-1")),
    "non-str key": {1: "x"},
    "cycle": _cyclic(),
    "shared container": _shared(),
}


@pytest.mark.parametrize("name", NOT_PLAIN)
def test_validate_event_needs_exact_plain_trees(name: str) -> None:
    rejected = reject(NOT_PLAIN[name])
    assert (rejected.code, rejected.disposition, rejected.raw_length) == (RejectCode.INVALID_JSON, DROP, 0)


def test_validate_event_null_is_invalid_json_but_parsed_null_is_schema() -> None:
    data = tree(("scope.task_id", None))
    parsed = _parse(raw(data))
    assert (parsed.code, parsed.pointer) == (RejectCode.SCHEMA_VIOLATION, "/scope/task_id")
    assert validate_event({"a": None}).code is RejectCode.INVALID_JSON  # type: ignore[union-attr]


def test_validate_event_prechecks() -> None:
    deep: list[object] = []
    node = deep
    for _ in range(16):
        child: list[object] = []
        node.append(child)
        node = child
    assert reject({"a": deep}).code is RejectCode.TOO_DEEP
    big = tree(("scope.zz", "y" * (64 * 1024)))
    assert (reject(big).code, reject(big).disposition) == (RejectCode.TOO_LARGE, DROP)  # C8
    assert reject(big).raw_length > 64 * 1024
    assert reject(tree(("source.seq", 2**53))).code is RejectCode.INTEGER_OUT_OF_RANGE
    assert reject(tree(("source.seq", 10**5000))).code is RejectCode.INTEGER_OUT_OF_RANGE
    assert reject(tree(("source.seq", -(10**20)))).raw_length == len(raw(tree(("source.seq", -(10**20)))))
    assert reject([]).code is RejectCode.NOT_AN_OBJECT


def test_validate_event_raw_is_the_plain_serialisation() -> None:
    data = tree(("spec_version", "1.5"), ("scope.session_id", 'é"\\'))
    expected = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    rejected = reject(data)
    assert b"10:00:01Z" in expected  # timestamps are not normalised in raw
    assert rejected.raw_length == len(expected)
    assert rejected.raw_sha256 == "sha256:" + hashlib.sha256(expected).hexdigest()


def test_lone_surrogate_is_forbidden_not_a_crash() -> None:
    data = tree(("payload.session_id", "a\ud800"))
    assert reject(data).code is RejectCode.FORBIDDEN_CHARACTER
    assert _parse(b'{"x":"\\ud800"}').code is RejectCode.FORBIDDEN_CHARACTER
