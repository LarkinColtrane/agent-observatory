"""Adversarial suite through the bytes path (ADR-0008 §§3, 10, 12, 15; AO-P2-005 AC3).

Every rejection code, malicious identifiers, secrets in every free-text field,
usage telemetry attacks, out-of-order and duplicate delivery, and
serialization bombs. All secrets are synthetic and built by concatenation.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from observatory.events import (
    Accepted,
    Disposition,
    DuplicateKind,
    Event,
    RejectCode,
    Rejected,
    canonical_json,
    canonical_order,
    classify_duplicate,
    parse_event,
    stream_key,
)
from observatory.events import envelope as envelope_module
from tests.fixtures.events.mappers import entity_id
from tests.fixtures.events.reference import TRACE
from tests.unit.events.factory import BEARER, DELETE, EVENT_ID, GH, JWT, PEM, SK, URL, tree

SCHEMA, DETECTED = RejectCode.SCHEMA_VIOLATION, RejectCode.SECRET_DETECTED


def _bytes(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8", "surrogatepass")


def _parse(data: object) -> Accepted | Rejected:
    return parse_event(data if isinstance(data, bytes) else _bytes(data))


def _rejected(data: object) -> Rejected:
    result = _parse(data)
    assert isinstance(result, Rejected), result
    return result


def _typed(event_type: str, payload: dict[str, Any], *changes: tuple[str, object]) -> dict[str, Any]:
    return tree(("event_type", event_type), ("payload", payload), *changes)


# --- every rejection code, bytes path --------------------------------------------------------------

EVERY_CODE: dict[RejectCode, bytes | dict[str, Any]] = {
    RejectCode.TOO_LARGE: b"{}" + b" " * (64 * 1024),
    RejectCode.INVALID_ENCODING: b'{"a":"\xc3"}',
    RejectCode.TOO_DEEP: b'{"a":' + b"[" * 16 + b"]" * 16 + b"}",
    RejectCode.INVALID_JSON: b'{"a" 1}',
    RejectCode.DUPLICATE_KEY: b'{"spec_version":"1.0","spec_version":"1.0"}',
    RejectCode.FLOAT_NOT_ALLOWED: b'{"seq":1E2}',
    RejectCode.INTEGER_OUT_OF_RANGE: b'{"seq":-0}',
    RejectCode.NOT_AN_OBJECT: b"true",
    RejectCode.SECRET_DETECTED: tree(("payload.session_id", "x:" + SK)),
    RejectCode.FORBIDDEN_CHARACTER: tree(("scope.task_id", "t" + chr(0xFEFF))),
    RejectCode.UNSUPPORTED_VERSION: tree(("spec_version", "1.1")),
    RejectCode.UNKNOWN_EVENT_TYPE: tree(("event_type", "session.resumed")),
    RejectCode.SCHEMA_VIOLATION: tree(("payload.initiator", "nobody")),
    RejectCode.INVALID_REFERENCE: tree(("causality", {"causation_id": EVENT_ID})),
}


@pytest.mark.parametrize("code", list(EVERY_CODE), ids=str)
def test_every_rejection_code_through_bytes(code: RejectCode) -> None:
    rejected = _rejected(EVERY_CODE[code])
    assert rejected.code is code
    quarantined = code in {
        RejectCode.FORBIDDEN_CHARACTER,
        RejectCode.UNSUPPORTED_VERSION,
        RejectCode.UNKNOWN_EVENT_TYPE,
        RejectCode.SCHEMA_VIOLATION,
        RejectCode.INVALID_REFERENCE,
    }
    assert rejected.disposition is (Disposition.QUARANTINE if quarantined else Disposition.DROP)
    assert (rejected.raw_sha256 is not None) == quarantined


def test_remaining_codes_through_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(envelope_module, "MAX_BYTES", 300)  # canonical size, check 15
    late = _rejected(tree())
    assert (late.code, late.disposition) == (RejectCode.TOO_LARGE, Disposition.QUARANTINE)
    monkeypatch.undo()

    def explode(_event: Event) -> None:
        raise MemoryError

    monkeypatch.setattr(envelope_module, "_check_references", explode)
    assert _rejected(tree()).code is RejectCode.INTERNAL_ERROR
    assert {c for c in RejectCode} == {*EVERY_CODE, RejectCode.INTERNAL_ERROR}


# --- malicious identifiers -----------------------------------------------------------------------

MALICIOUS_IDS = {
    "oversized": "a" * 129,
    "unicode": "agent-" + chr(0x00E9),
    "nul": "agent" + chr(0) + "x",
    "path-like": "../../etc/passwd",
    "absolute": "/root",
    "confusable": "c" + chr(0x043E) + "ordinator",  # Cyrillic o
    "fullwidth": chr(0xFF41) + "gent",
    "spaces": "agent 1",
    "leading dot": ".hidden",
    "markup": "<img src=x>",
    "empty": "",
}
ID_FIELDS = ["scope.session_id", "scope.agent_id", "scope.task_id", "source.stream_id", "payload.session_id"]


@pytest.mark.parametrize("name", MALICIOUS_IDS)
@pytest.mark.parametrize("field", ID_FIELDS)
def test_malicious_identifiers(name: str, field: str) -> None:
    changes: list[tuple[str, object]] = [(field, MALICIOUS_IDS[name])]
    if field == "payload.session_id":
        changes.append(("scope.session_id", MALICIOUS_IDS[name]))
    rejected = _rejected(tree(*changes))
    expected = RejectCode.FORBIDDEN_CHARACTER if name == "nul" else SCHEMA
    assert rejected.code is expected
    assert MALICIOUS_IDS[name] not in repr(rejected) or not MALICIOUS_IDS[name]


@pytest.mark.parametrize("value", ["WS", "ws_1", "-ws", "w" * 64, "ws" + chr(0x2010) + "1"])
def test_malicious_workspaces_and_providers(value: str) -> None:
    assert _rejected(tree(("scope.workspace_id", value))).code is SCHEMA
    assert _rejected(tree(("source.provider", value))).code is SCHEMA


def test_h_prefix_collisions_are_prevented_by_hashing() -> None:
    hashed = entity_id("synthetic-x", "a b")
    forged = hashed.removeprefix("synthetic-x:")  # a provider native that mimics a hashed id
    assert entity_id("synthetic-x", forged) != hashed
    assert entity_id("synthetic-x", forged).startswith("synthetic-x:h.")
    # The protocol accepts an h. Id as an opaque Id; only adapters decide what it means.
    assert isinstance(_parse(tree(("scope.task_id", forged))), Accepted)


# --- secrets in every free-text field, key and value ---------------------------------------------

SECRETS = {
    "openai": SK,
    "github": GH,
    "jwt": JWT,
    "pem": PEM,
    "url": URL,
    "bearer": BEARER,
    "key=value": "password" + "=" + "x",
    "cli option": "--api-key " + "x",
    "mysql": "mysql -p" + "x",
}


def _carriers(secret: str) -> dict[str, dict[str, Any]]:
    short = secret[:120]
    return {
        "role": _typed("agent.spawned", {"agent_id": "a-2", "role": secret[:64]}),
        "display_name": _typed("agent.spawned", {"agent_id": "a-2", "display_name": short}),
        "title": _typed("task.created", {"task_id": "t-1", "title": short}),
        "command": _typed(
            "tool.call_started", {"call_id": "c-1", "tool_name": "Bash", "kind": "command", "command": secret}
        ),
        "query": _typed(
            "tool.call_started", {"call_id": "c-1", "tool_name": "Grep", "kind": "search", "query": short}
        ),
        "error message": _typed("error.reported", {"error_code": "e", "severity": "error", "message": short}),
        "extension value": tree(("extensions", {"x-acme": {"note": short}})),
        "extension list": tree(("extensions", {"x-acme": {"notes": ["ok", short]}})),
        "extension event": _typed("x-acme.note", {"text": short}),
        "tool name": _typed(
            "tool.call_started", {"call_id": "c-1", "tool_name": short.replace(" ", "_"), "kind": "other"}
        ),
        "provider_event_id": tree(("source.provider_event_id", short)),
        "unknown field": tree(("payload.zz", short)),
    }


@pytest.mark.parametrize("secret", SECRETS)
def test_secrets_in_every_free_text_field(secret: str) -> None:
    for carrier, data in _carriers(SECRETS[secret]).items():
        if carrier in {"tool name", "provider_event_id"} and " " in SECRETS[secret]:
            continue  # only space-free secrets fit these ASCII types; the others are covered elsewhere
        rejected = _rejected(data)
        assert (rejected.code, rejected.raw_sha256) == (DETECTED, None), (secret, carrier)
        assert SECRETS[secret][:12] not in repr(rejected)


@pytest.mark.parametrize(
    "key", ["password", "apiKey", "client_secret", "Authorization", "session_token", "dsn"]
)
def test_secret_named_keys_everywhere(key: str) -> None:
    for data in (
        tree(("extensions", {"x-acme": {key: 1}})),
        tree(("extensions", {"x-acme": {"nested": {key: "v"}}})),
        _typed("x-acme.event", {key: True}),
        tree(("payload." + key, "v")),
        tree(("scope." + key, "v")),
    ):
        assert _rejected(data).code is DETECTED


# --- usage telemetry attacks -------------------------------------------------------------------------


def _usage(usage: object, **extra: object) -> dict[str, Any]:
    return _typed("usage.recorded", {"usage": usage, "accounting": "delta", "unit": "turn", **extra})


USAGE_ATTACKS: dict[str, tuple[bytes | dict[str, Any], RejectCode]] = {
    "string number": (_usage({"input_tokens": "5"}), DETECTED),  # not an int: the key-name test applies
    "bool": (_usage({"output_tokens": True}), DETECTED),
    "float": (
        _bytes(_usage({"input_tokens": 5})).replace(b'"input_tokens": 5', b'"input_tokens": 5.0'),
        RejectCode.FLOAT_NOT_ALLOWED,
    ),
    "exponent": (
        _bytes(_usage({"input_tokens": 5})).replace(b'"input_tokens": 5', b'"input_tokens": 5e0'),
        RejectCode.FLOAT_NOT_ALLOWED,
    ),
    "negative": (_usage({"input_tokens": -1}), SCHEMA),
    "above 10^12": (_usage({"input_tokens": 10**12 + 1}), SCHEMA),
    "above 2^53": (_usage({"input_tokens": 2**53}), RejectCode.INTEGER_OUT_OF_RANGE),
    "cached > input": (_usage({"input_tokens": 1, "cached_input_tokens": 2}), SCHEMA),
    "reasoning > output": (_usage({"output_tokens": 1, "reasoning_tokens": 2}), SCHEMA),
    "empty": (_usage({}), SCHEMA),
    "forged currency": (
        _usage({"input_tokens": 1, "reported_cost": {"amount": "1", "currency": "XBT"}}),
        SCHEMA,
    ),
    "lowercase currency": (
        _usage({"input_tokens": 1, "reported_cost": {"amount": "1", "currency": "usd"}}),
        SCHEMA,
    ),
    "float money": (
        _bytes(_usage({"input_tokens": 1, "reported_cost": {"amount": 1, "currency": "USD"}})).replace(
            b'"amount": 1', b'"amount": 0.1'
        ),
        RejectCode.FLOAT_NOT_ALLOWED,
    ),
    "number money": (_usage({"input_tokens": 1, "reported_cost": {"amount": 1, "currency": "USD"}}), SCHEMA),
    "negative money": (
        _usage({"input_tokens": 1, "reported_cost": {"amount": "-1", "currency": "USD"}}),
        SCHEMA,
    ),
    "pricing_ref without estimate": (_usage({"input_tokens": 1}, pricing_ref="prices/v1"), SCHEMA),
    "estimate without pricing_ref": (
        _usage({"input_tokens": 1, "estimated_cost": {"amount": "1", "currency": "USD"}}),
        SCHEMA,
    ),
    "secret key in usage": (_usage({"input_tokens": 1, "access_token": 1}), DETECTED),
    "token key outside usage": (
        _typed("error.reported", {"error_code": "e", "severity": "error", "output_tokens": 1}),
        DETECTED,
    ),
    "token key in extensions": (tree(("extensions", {"x-acme": {"total_tokens": 1}})), DETECTED),
    "usage in another type": (_typed("x-acme.usage", {"usage": {"input_tokens": 1}}), DETECTED),
}


@pytest.mark.parametrize("attack", USAGE_ATTACKS)
def test_usage_telemetry_attacks(attack: str) -> None:
    data, code = USAGE_ATTACKS[attack]
    assert _rejected(data).code is code


# --- out-of-order and duplicate delivery -----------------------------------------------------------------


def test_out_of_order_and_duplicate_delivery() -> None:
    """A toy store: classify each delivery by event id and by stream slot, keep the first copy."""
    lines = TRACE.read_bytes().splitlines()
    rng = random.Random(15)  # noqa: S311 (seeded test data, not cryptography)
    deliveries = lines + rng.sample(lines, 20)
    rng.shuffle(deliveries)
    by_id: dict[str, Event] = {}
    by_slot: dict[tuple[tuple[str, str, str, str], int], Event] = {}
    kinds: list[DuplicateKind] = []
    for body in deliveries:
        result = parse_event(body)
        assert isinstance(result, Accepted)
        event = result.event
        key = stream_key(event)
        slot = (key, event.source.seq) if key is not None and event.source.seq is not None else None
        existing = by_id.get(event.event_id) or (by_slot.get(slot) if slot else None)
        kind = classify_duplicate(existing, event) if existing else DuplicateKind.DISTINCT
        kinds.append(kind)
        if kind is DuplicateKind.DISTINCT:
            by_id[event.event_id] = event
            if slot:
                by_slot[slot] = event
    assert kinds.count(DuplicateKind.EXACT_DUPLICATE) == 20
    assert set(kinds) == {DuplicateKind.DISTINCT, DuplicateKind.EXACT_DUPLICATE}
    assert [canonical_json(e) for e in canonical_order(by_id.values())] == lines


def test_slot_squatting_is_a_sequence_conflict() -> None:
    lines = TRACE.read_bytes().splitlines()
    original = parse_event(lines[5])
    assert isinstance(original, Accepted)
    tree_ = json.loads(lines[5])
    tree_["event_id"] = "0190a8f2-6b1c-7d3e-8f4a-0000000000ff"
    squatter = _parse(tree_)
    assert isinstance(squatter, Accepted)
    assert classify_duplicate(original.event, squatter.event) is DuplicateKind.SEQUENCE_CONFLICT


# --- serialization bombs --------------------------------------------------------------------------------


def test_serialization_bombs() -> None:
    assert _rejected(b"[" * 60000).code is RejectCode.TOO_DEEP
    assert _rejected(b'{"a":' + b"{" * 40000 + b"}" * 40000 + b"}").code is RejectCode.TOO_LARGE
    assert _rejected(b'{"a":' + b"[" * 20000 + b"]" * 20000 + b"}").code is RejectCode.TOO_DEEP
    assert _rejected(b'{"a":"' + b"[" * 60000 + b'"}').code is RejectCode.UNSUPPORTED_VERSION  # not too_deep
    assert _rejected(b'{"a":1' + b"0" * 60000 + b"}").code is RejectCode.INTEGER_OUT_OF_RANGE
    assert _rejected(b'{"a":1.' + b"0" * 60000 + b"}").code is RejectCode.FLOAT_NOT_ALLOWED
    many_keys = b"{" + b",".join(b'"k%d":1' % i for i in range(6000)) + b"}"
    assert _rejected(many_keys).code is RejectCode.UNSUPPORTED_VERSION
    escapes = b'{"a":"' + b"\\u0041" * 10000 + b'"}'
    assert len(escapes) < 64 * 1024
    assert _rejected(escapes).code is RejectCode.UNSUPPORTED_VERSION


def test_64_kib_edges() -> None:
    body = canonical_json(_valid())
    exact = body[:-1] + b" " * (64 * 1024 - len(body)) + b"}"
    assert len(exact) == 64 * 1024
    assert isinstance(parse_event(exact), Accepted)
    assert _rejected(exact[:-1] + b" }").code is RejectCode.TOO_LARGE
    padded = _parse(tree(("extensions", {"x-acme": {f"k{i}": "v" * 400 for i in range(12)}})))
    assert isinstance(padded, Rejected)
    assert padded.code is SCHEMA  # extensions over 4 KiB canonical


def _valid() -> Event:
    result = _parse(tree(("time.occurred_at", DELETE)))
    assert isinstance(result, Accepted)
    return result.event
