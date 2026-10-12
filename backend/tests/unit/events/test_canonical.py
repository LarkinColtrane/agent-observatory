"""Canonical JSON, fingerprints and derived event ids (ADR-0008 §§4, 13, 14; AO-P2-003 AC2)."""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from typing import Any

import pytest

from observatory.events import (
    Accepted,
    canonical_json,
    content_fingerprint,
    derive_event_id,
    fingerprint,
    parse_event,
)
from observatory.events.tree import canonical_text
from tests.unit.events.factory import DELETE, WS, accept, build, raw, tree, uuid7

GOLDEN = (
    '{"event_id":"0190a8f2-6b1c-7d3e-8f4a-123456789abc","event_type":"session.started",'
    '"payload":{"initiator":"human","session_id":"sess-1"},'
    '"scope":{"agent_id":"claude-code:agent-1","session_id":"sess-1","workspace_id":"ws-1"},'
    '"source":{"adapter":{"name":"cc-adapter","version":"1.2.3"},"provider":"claude-code",'
    '"seq":0,"stream_id":"stream-a"},"spec_version":"1.0",'
    '"time":{"observed_at":"2026-03-01T10:00:01.000000Z","occurred_at":"2026-03-01T10:00:00.500000Z"}}'
)


def test_canonical_json_golden() -> None:
    event = build()
    assert canonical_json(event) == GOLDEN.encode("utf-8")
    assert fingerprint(event) == "sha256:" + hashlib.sha256(GOLDEN.encode("utf-8")).hexdigest()


def test_whitespace_order_and_escapes_do_not_matter() -> None:
    pretty = json.dumps(tree(), indent=4, ensure_ascii=True).encode("ascii")
    reordered = raw(dict(reversed(list(tree().items()))))
    escaped = raw(tree()).replace(b'"sess-1"', b'"\\u0073ess-1"').replace(b"/", b"\\/")
    for body in (pretty, reordered, escaped):
        result = parse_event(body)
        assert isinstance(result, Accepted)
        assert canonical_json(result.event) == GOLDEN.encode("utf-8")


def test_canonical_text_escapes_like_rfc_8785() -> None:
    value = 'q"b\\s\x08f\x0cn\nr\rt\t' + chr(0x1F) + chr(0x7F) + chr(0xE9) + chr(0x2603) + chr(0x1F600) + "/"
    expected = (
        '"q\\"b\\\\s\\bf\\fn\\nr\\rt\\t\\u001f' + chr(0x7F) + chr(0xE9) + chr(0x2603) + chr(0x1F600) + '/"'
    )
    assert canonical_text(value) == expected
    assert canonical_text({"b": 1, "a": [True, False, -5], "B": {}}) == '{"B":{},"a":[true,false,-5],"b":1}'


def test_only_present_fields_are_serialised() -> None:
    event = build(("time.occurred_at", DELETE))
    assert b"occurred_at" not in canonical_json(event)
    assert b"null" not in canonical_json(event)
    assert b"causality" not in canonical_json(event)


FRACTIONS = ["Z", ".1Z", ".123Z", ".123456Z"]


def _random_tree(rng: random.Random) -> dict[str, Any]:
    text = "".join(
        rng.choice(["a", '"', "\\", "/", chr(0xE9), chr(0x4E2D), chr(0x1F600), "<b>", " "]) for _ in range(9)
    )
    changes: list[tuple[str, object]] = [
        ("event_id", uuid7(rng)),
        ("source.seq", rng.randint(0, 2**53 - 1)),
        ("time.observed_at", f"20{rng.randint(10, 99)}-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}"
         f"T0{rng.randint(0, 9)}:{rng.randint(10, 59)}:{rng.randint(10, 59)}" + rng.choice(FRACTIONS)),
        ("extensions", {"x-acme": {"note": "n" + text.strip(), "n": rng.randint(-1000, 1000),
                                   "f": rng.random() < 0.5}}),
    ]  # fmt: skip
    if rng.random() < 0.5:
        changes.append(("time.occurred_at", DELETE))
    if rng.random() < 0.5:
        changes.append(("causality", {"correlation_id": "corr-" + str(rng.randint(0, 99))}))
    return tree(*changes)


def test_round_trip_is_a_fixed_point() -> None:
    rng = random.Random(4242)  # noqa: S311 (seeded test data, not cryptography)
    for _ in range(150):
        event = accept(_random_tree(rng)).event
        first = canonical_json(event)
        again = parse_event(first)
        assert isinstance(again, Accepted)
        assert canonical_json(again.event) == first
        assert again.fingerprint == fingerprint(event) == "sha256:" + hashlib.sha256(first).hexdigest()
        assert again.event == event


def test_content_fingerprint_ignores_only_observation_fields() -> None:
    event = build()
    reobserved = build(
        ("time.observed_at", "2026-03-02T00:00:00Z"),
        ("source.adapter", {"name": "other-adapter", "version": "9.0.0"}),
        ("source.stream_id", "stream-b"),
        ("source.seq", 7),
    )
    assert fingerprint(event) != fingerprint(reobserved)
    assert content_fingerprint(event) == content_fingerprint(reobserved)
    for changed in (
        build(("payload.initiator", "agent")),
        build(("time.occurred_at", "2026-03-01T10:00:00.6Z")),
        build(("source.provider", "other-provider")),
        build(("scope.task_id", "t-1")),
    ):
        assert content_fingerprint(changed) != content_fingerprint(event)
    expected = tree()
    del expected["time"]["observed_at"]
    for key in ("adapter", "stream_id", "seq"):
        del expected["source"][key]
    expected["time"]["occurred_at"] = "2026-03-01T10:00:00.500000Z"
    digest = hashlib.sha256(canonical_text(expected).encode("utf-8")).hexdigest()
    assert content_fingerprint(event) == "sha256:" + digest


# --- derived event ids (§4) ---------------------------------------------------------------------------


def _reference_derivation(workspace_id: str, provider: str, provider_event_id: str) -> str:
    material = b"ao-event-id/v1\0" + "\0".join((workspace_id, provider, provider_event_id)).encode()
    value = int.from_bytes(hashlib.sha256(material).digest()[:16], "big")
    value = (value & ~(0xF << 76)) | (0x8 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)
    return str(uuid.UUID(int=value))


def test_derive_event_id_matches_the_contract() -> None:
    derived = derive_event_id(WS, "claude-code", "sess-9/msg_01")
    assert derived == _reference_derivation(WS, "claude-code", "sess-9/msg_01")
    parsed = uuid.UUID(derived)
    assert (parsed.version, parsed.variant) == (8, uuid.RFC_4122)
    assert derived == derived.lower()
    assert derive_event_id(WS, "claude-code", "sess-9/msg_01") == derived
    assert derive_event_id("ws-2", "claude-code", "sess-9/msg_01") != derived
    assert derive_event_id(WS, "codex", "sess-9/msg_01") != derived
    assert derive_event_id(WS, "claude-code", "sess-8/msg_01") != derived


@pytest.mark.parametrize(
    ("workspace_id", "provider", "provider_event_id"),
    [
        ("WS", "claude-code", "x"),
        ("ws-1", "Claude", "x"),
        ("ws-1", "claude-code", ""),
        ("ws-1", "claude-code", "a\0b"),
        ("ws\0", "claude-code", "x"),
        ("ws-1", "claude-code", "a b"),
        ("ws-1", "claude-code", "x" * 257),
        ("ws-1", "claude-code", chr(0xE9)),
    ],
)
def test_derive_event_id_validates_its_arguments(
    workspace_id: str, provider: str, provider_event_id: str
) -> None:
    with pytest.raises(ValueError, match="derive_event_id"):
        derive_event_id(workspace_id, provider, provider_event_id)


def test_events_with_provider_ids_carry_the_derived_id() -> None:
    derived = derive_event_id(WS, "claude-code", "native-1")
    event = build(("event_id", derived), ("source.provider_event_id", "native-1"))
    assert event.event_id == derived
    assert build(("event_id", "4b1d6c1e-2f3a-4b5c-9d6e-7f8091a2b3c4")).event_id.startswith("4b1d")
