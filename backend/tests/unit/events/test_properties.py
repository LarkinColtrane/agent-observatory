"""Seeded, bounded property tests over the reference trace (ADR-0008 §§4, 7, 13-15; AO-P2-005 AC3).

Every generator is ``random.Random(seed)``; each property runs at most a few hundred cases.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from observatory.events import (
    Accepted,
    DuplicateKind,
    Event,
    canonical_json,
    canonical_order,
    classify_duplicate,
    content_fingerprint,
    derive_event_id,
    fingerprint,
    parse_event,
    validate_event,
)
from tests.fixtures.events import mappers
from tests.fixtures.events.reference import TRACE


@pytest.fixture(scope="module")
def trace() -> list[Event]:
    parsed = [parse_event(line) for line in TRACE.read_bytes().splitlines()]
    return [p.event for p in parsed if isinstance(p, Accepted)]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 (seeded test data, not cryptography)


def _tree(event: Event) -> dict[str, Any]:
    tree: dict[str, Any] = json.loads(canonical_json(event))
    return tree


def _rebuild(tree: dict[str, Any]) -> Event:
    result = validate_event(tree)
    assert isinstance(result, Accepted), result
    return result.event


def _shuffled_json(value: Any, rng: random.Random) -> Any:
    """The same JSON value with object members in a random order."""
    if isinstance(value, dict):
        items = list(value.items())
        rng.shuffle(items)
        return {k: _shuffled_json(v, rng) for k, v in items}
    if isinstance(value, list):
        return [_shuffled_json(v, rng) for v in value]
    return value


def test_order_is_invariant_under_permutation(trace: list[Event]) -> None:
    rng = _rng(1)
    position = {e.event_id: i for i, e in enumerate(trace)}
    for _ in range(60):
        subset = rng.sample(trace, rng.randint(1, len(trace)))
        ordered = canonical_order(subset)
        assert [position[e.event_id] for e in ordered] == sorted(position[e.event_id] for e in subset)


def test_parse_canonical_parse_round_trip(trace: list[Event]) -> None:
    rng = _rng(2)
    for _ in range(200):
        event = rng.choice(trace)
        text = json.dumps(
            _shuffled_json(_tree(event), rng),
            indent=rng.choice([None, 0, 2]),
            ensure_ascii=rng.random() < 0.5,
            separators=rng.choice([(",", ":"), (", ", ": ")]),
        )
        again = parse_event(text.encode("utf-8"))
        assert isinstance(again, Accepted)
        assert canonical_json(again.event) == canonical_json(event)
        assert parse_event(canonical_json(again.event)) == parse_event(canonical_json(event))


def test_fingerprints_are_stable(trace: list[Event]) -> None:
    rng = _rng(3)
    for _ in range(200):
        event = rng.choice(trace)
        rebuilt = _rebuild(_shuffled_json(_tree(event), rng))
        assert fingerprint(rebuilt) == fingerprint(event)
        assert content_fingerprint(rebuilt) == content_fingerprint(event)


def _iso(rng: random.Random) -> str:
    return f"2026-0{rng.randint(4, 9)}-{rng.randint(10, 28)}T{rng.randint(10, 23)}:{rng.randint(10, 59)}:00Z"


def test_reobserved_events_are_redeliveries(trace: list[Event]) -> None:
    rng = _rng(4)
    for _ in range(200):
        event = rng.choice(trace)
        tree = _tree(event)
        changes = rng.sample(["observed_at", "adapter", "seq"], rng.randint(1, 3))
        if event.source.seq is None and changes == ["seq"]:
            changes = ["observed_at"]  # a stream-less event has no seq to change
        if "observed_at" in changes:
            tree["time"]["observed_at"] = _iso(rng)
        if "adapter" in changes:
            tree["source"]["adapter"]["version"] = f"1.{rng.randint(1, 99)}.0"
        if "seq" in changes and event.source.seq is not None:  # a stream-less event has no slot
            tree["source"]["seq"] = event.source.seq + rng.randint(1, 1000)
        assert classify_duplicate(event, _rebuild(tree)) is DuplicateKind.REDELIVERY


def test_mutated_content_is_a_conflict(trace: list[Event]) -> None:
    rng = _rng(5)
    for _ in range(200):
        event = rng.choice(trace)
        tree = _tree(event)
        mutation = rng.choice(["task", "occurred", "correlation"])
        if mutation == "task":
            tree["scope"]["task_id"] = f"synthetic-reference:task-{rng.randint(100, 999)}"
        elif mutation == "occurred":
            tree["time"]["occurred_at"] = (
                tree["time"]["occurred_at"][:-4] + f"{rng.randint(1, 999):03d}" + "Z"
            )
        else:
            tree["causality"]["correlation_id"] = f"synthetic-reference:corr-{rng.randint(1, 99)}"
        mutated = _rebuild(tree)
        assert canonical_json(mutated) != canonical_json(event)
        assert classify_duplicate(event, mutated) is DuplicateKind.CONFLICT


def test_same_native_id_in_two_sessions_gives_two_event_ids() -> None:
    rng = _rng(6)
    for _ in range(200):
        native = f"msg_{rng.getrandbits(48):012x}"
        first, second = rng.sample(["sess-a", "sess-b", "run-1", "conv-9", "s.0", "s:1"], 2)
        a = derive_event_id("synthetic-ws", "synthetic-transcript", f"{first}/{native}")
        b = derive_event_id("synthetic-ws", "synthetic-transcript", f"{second}/{native}")
        assert a != b
    entries = mappers.load_a()
    for session in ("sess-x", "sess-y"):
        renamed = [{**entry, "sessionId": session} for entry in entries]
        ids = {e.event_id for e in mappers.map_transcript(renamed)}
        assert not ids & {e.event_id for e in mappers.map_transcript(entries)}
