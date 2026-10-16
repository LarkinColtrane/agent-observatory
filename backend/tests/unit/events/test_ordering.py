"""Stream keys, canonical order and duplicate classification (ADR-0008 §§5, 7, 15; AC3, AC8)."""

from __future__ import annotations

import random

import pytest

from observatory.events import DuplicateKind, Event, canonical_order, classify_duplicate, stream_key
from tests.unit.events.factory import DELETE, EVENT_ID, OTHER_ID, build, uuid7

T = "2026-03-01T10:00:0{}Z"


def _event(
    event_id: str, stream: str | None, seq: int, second: int, *, occurred: bool = True, ws: str = "ws-1"
) -> Event:
    changes: list[tuple[str, object]] = [
        ("event_id", event_id),
        ("scope.workspace_id", ws),
        ("time.observed_at", T.format(9)),
        ("time.occurred_at", T.format(second) if occurred else DELETE),
    ]
    if stream is None:
        changes += [("source.stream_id", DELETE), ("source.seq", DELETE)]
    else:
        changes += [("source.stream_id", stream), ("source.seq", seq)]
    return build(*changes)


def test_stream_key() -> None:
    event = build()
    assert stream_key(event) == ("ws-1", "claude-code", "cc-adapter", "stream-a")
    assert stream_key(build(("source.stream_id", DELETE), ("source.seq", DELETE))) is None


def _scenario(rng: random.Random) -> list[Event]:
    events: list[Event] = []
    for stream in ("stream-a", "stream-b", "stream-c"):
        for seq in range(rng.randint(1, 5)):
            events.append(_event(uuid7(rng), stream, seq, rng.randint(0, 9), occurred=rng.random() < 0.8))
    for _ in range(rng.randint(0, 4)):
        events.append(_event(uuid7(rng), None, 0, rng.randint(0, 9), occurred=rng.random() < 0.8))
    return events


def test_canonical_order_is_independent_of_input_order() -> None:
    rng = random.Random(7)  # noqa: S311 (seeded test data, not cryptography)
    for _ in range(25):
        events = _scenario(rng)
        expected = [e.event_id for e in canonical_order(events)]
        for _ in range(8):
            shuffled = events[:]
            rng.shuffle(shuffled)
            assert [e.event_id for e in canonical_order(shuffled)] == expected
        positions: dict[str, list[int]] = {}
        for event in canonical_order(events):
            if event.source.stream_id is not None:
                positions.setdefault(event.source.stream_id, []).append(event.source.seq or 0)
        assert all(seqs == sorted(seqs) for seqs in positions.values())


def test_stream_order_beats_timestamps_and_streams_interleave_by_time() -> None:
    a0 = _event(uuid7(random.Random(1)), "stream-a", 0, 5)  # noqa: S311
    a1 = _event(uuid7(random.Random(2)), "stream-a", 1, 1)  # noqa: S311 (time goes backwards)
    b0 = _event(uuid7(random.Random(3)), "stream-b", 0, 3)  # noqa: S311
    loose = _event(uuid7(random.Random(4)), None, 0, 4)  # noqa: S311
    assert canonical_order([a1, loose, b0, a0]) == [b0, loose, a0, a1]


def test_ties_break_by_group_key_then_id() -> None:
    first, second = sorted([EVENT_ID, OTHER_ID])
    one = _event(second, None, 0, 1)
    two = _event(first, None, 0, 1)
    streamed = _event("0190a8f2-6b1c-7d3e-8f4a-000000000001", "stream-a", 0, 1)
    assert canonical_order([streamed, one, two]) == [two, one, streamed]  # "" sorts before any provider


def test_canonical_order_preconditions() -> None:
    assert canonical_order([]) == []
    with pytest.raises(ValueError, match="duplicate event_id"):
        canonical_order([build(), build(("time.observed_at", "2026-03-01T10:00:02Z"))])
    with pytest.raises(ValueError, match="workspace"):
        canonical_order([build(), build(("event_id", OTHER_ID), ("scope.workspace_id", "ws-2"))])


# --- duplicates (§15) -----------------------------------------------------------------------------


def test_duplicate_kinds_in_precedence() -> None:
    stored = build()
    assert classify_duplicate(stored, build()) is DuplicateKind.EXACT_DUPLICATE
    reobserved = build(
        ("time.observed_at", "2026-03-01T11:00:00Z"),
        ("source.adapter.version", "2.0.0"),
        ("source.stream_id", "stream-z"),
        ("source.seq", 41),
    )
    assert classify_duplicate(stored, reobserved) is DuplicateKind.REDELIVERY
    assert classify_duplicate(stored, build(("payload.initiator", "agent"))) is DuplicateKind.CONFLICT
    assert classify_duplicate(stored, build(("event_id", OTHER_ID))) is DuplicateKind.SEQUENCE_CONFLICT
    assert (
        classify_duplicate(stored, build(("event_id", OTHER_ID), ("source.seq", 1))) is DuplicateKind.DISTINCT
    )
    unstreamed = build(("event_id", OTHER_ID), ("source.stream_id", DELETE), ("source.seq", DELETE))
    assert classify_duplicate(stored, unstreamed) is DuplicateKind.DISTINCT
    assert classify_duplicate(unstreamed, unstreamed) is DuplicateKind.EXACT_DUPLICATE
    assert {kind.value for kind in DuplicateKind} == {
        "exact_duplicate",
        "redelivery",
        "conflict",
        "sequence_conflict",
        "distinct",
    }


def test_same_slot_never_hides_an_id_match() -> None:
    stored = build()
    # Same id, same stream slot, different content: a conflict, not a sequence conflict.
    assert classify_duplicate(stored, build(("scope.task_id", "t-1"))) is DuplicateKind.CONFLICT
    # Same id and content re-observed on the same slot: a redelivery, not a conflict.
    assert classify_duplicate(stored, build(("time.observed_at", "2026-03-01T10:00:05Z"))) is (
        DuplicateKind.REDELIVERY
    )


def test_classify_refuses_mixed_workspaces() -> None:
    with pytest.raises(ValueError, match="workspace"):
        classify_duplicate(build(), build(("scope.workspace_id", "ws-2")))
