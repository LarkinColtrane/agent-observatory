"""Three synthetic provider shapes map one scenario to the same projection (ADR-0008 §18; AO-P2-005 AC1, AC4).

Ids, time and provenance differ as §§4 and 6 require; the projection
(event_type, scope, payload), compared without the ``<provider>:`` qualification
of entity ids, is equal across shapes on what they share.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from observatory.events import (
    Accepted,
    DuplicateKind,
    Event,
    canonical_json,
    classify_duplicate,
    stream_key,
    validate_event,
)
from observatory.events.ids import uuid_version
from tests.fixtures.events import mappers
from tests.fixtures.events.mappers import (
    PROVIDER_A,
    PROVIDER_B,
    PROVIDER_C,
    command_text,
    entity_id,
    projection,
    unique,
)
from tests.unit.events.factory import SK

TYPES_A = {
    "session.started",
    "session.ended",
    "agent.spawned",
    "tool.call_started",
    "tool.call_finished",
    "file.changed",
    "usage.recorded",
}
TYPES_B = {
    "agent.spawned",
    "agent.terminated",
    "task.created",
    "task.assigned",
    "task.status_changed",
    "review.verdict_recorded",
}


@pytest.fixture(scope="module")
def shapes() -> dict[str, list[Event]]:
    return {
        "A": mappers.map_transcript(mappers.load_a()),
        "B": mappers.map_webhooks(mappers.load_b()),
        "C": mappers.map_agent(mappers.load_c()),
    }


def _projections(events: Any, types: set[str] | None = None) -> list[str]:
    return sorted(
        json.dumps(projection(e), sort_keys=True) for e in events if types is None or e.event_type in types
    )


def test_every_fixture_is_labelled_synthetic() -> None:
    directory = mappers.FIXTURES
    readme = (directory / "README.md").read_text(encoding="utf-8")
    assert "SYNTHETIC" in readme
    assert "no real data" in readme
    for path in sorted(directory.iterdir()):
        if path.suffix == ".jsonl" and path.name.startswith("synthetic-"):
            assert all(json.loads(line)["_synthetic"] is True for line in path.read_text().splitlines())
        elif path.suffix == ".json":
            assert path.name.startswith("synthetic-")
            assert json.loads(path.read_text())["_synthetic"] is True
        elif path.suffix == ".py":
            assert "SYNTHETIC" in path.read_text(encoding="utf-8") or path.name == "__init__.py"
    assert "**not** product adapters" in readme
    assert "**not** product adapters" in Path(mappers.__file__).read_text(encoding="utf-8")


def test_projection_is_equal_across_shapes(shapes: dict[str, list[Event]]) -> None:
    a, b, c = shapes["A"], list(unique(shapes["B"])), shapes["C"]
    shared_ac = _projections(a)
    shared_bc = _projections(b)
    assert shared_ac == _projections(c, TYPES_A)
    assert shared_bc == _projections(c, TYPES_B)
    assert len(shared_ac) == 10
    assert len(shared_bc) == 10  # a non-trivial overlap
    spawns = [_projections(events, {"agent.spawned"}) for events in (a, b, c)]
    assert spawns[0] == spawns[1] == spawns[2]
    assert len(spawns[0]) == 2  # common to all three
    assert {e.event_type for e in c} - TYPES_A - TYPES_B == {
        "test.run_completed",
        "error.reported",
        "message.sent",
    }


def test_ids_time_and_provenance_differ(shapes: dict[str, list[Event]]) -> None:
    a, b, c = shapes["A"], shapes["B"], shapes["C"]
    spawn = {
        name: next(e for e in events if e.event_type == "agent.spawned") for name, events in shapes.items()
    }
    assert len({e.event_id for e in spawn.values()}) == 3
    assert {e.source.provider for e in spawn.values()} == {PROVIDER_A, PROVIDER_B, PROVIDER_C}
    # A and B carry provider ids, so their event ids are derived UUIDv8s; C has none and uses UUIDv7s.
    assert all(uuid_version(e.event_id) == 8 and e.source.provider_event_id for e in [*a, *b])
    assert all(uuid_version(e.event_id) == 7 and e.source.provider_event_id is None for e in c)
    # A and B have source times (B's offsets converted to Z); C has none, so occurred_at stays absent.
    assert all(e.time.occurred_at is not None for e in [*a, *b])
    assert all(e.time.occurred_at is None for e in c)
    assert spawn["B"].time.occurred_at == "2026-03-02T09:00:05.000000Z"
    # A and C read in order and assign streams; B's webhooks are unordered and have none.
    assert [e.source.seq for e in a] == list(range(len(a)))
    assert [e.source.seq for e in c] == list(range(len(c)))
    assert all(stream_key(e) is None for e in b)


def test_shape_a_converts_usage_paths_and_commands(shapes: dict[str, list[Event]]) -> None:
    usage = next(e for e in shapes["A"] if e.event_type == "usage.recorded").payload
    tokens = usage.model_dump(exclude_none=True)["usage"]
    assert tokens == {
        "input_tokens": 1300,
        "cached_input_tokens": 800,
        "output_tokens": 300,
    }  # 400 + 800 + 100
    file_changed = next(e for e in shapes["A"] if e.event_type == "file.changed").payload.model_dump()
    assert (file_changed["path"], file_changed["lines_added"]) == ("src/orders.py", 40)
    started = [e.payload.model_dump() for e in shapes["A"] if e.event_type == "tool.call_started"]
    assert started[1]["command"] == "pytest -q tests/test_orders.py"  # first line only (§10.4)


def test_shape_b_redelivery_and_sanitising(shapes: dict[str, list[Event]]) -> None:
    b = shapes["B"]
    first, again = b[4], b[-1]
    assert first.event_id == again.event_id
    assert first.time.observed_at != again.time.observed_at
    assert classify_duplicate(first, again) is DuplicateKind.REDELIVERY
    title = next(e for e in b if e.event_type == "task.created" and "review" in str(e.payload.model_dump()))
    assert title.payload.model_dump()["title"] == "Security review (password=[REDACTED])"


def test_same_native_id_in_two_sessions_gives_two_event_ids() -> None:
    entries = mappers.load_a()
    other = copy.deepcopy(entries)
    for entry in other:
        entry["sessionId"] = "sess-2"
    first, second = mappers.map_transcript(entries), mappers.map_transcript(other)
    assert first[0].source.provider_event_id == "sess-1/tr-0001#start"
    assert not {e.event_id for e in first} & {e.event_id for e in second}
    assert [projection(e)["event_type"] for e in first] == [projection(e)["event_type"] for e in second]


def test_unmappable_fields_are_dropped_not_carried(shapes: dict[str, list[Event]]) -> None:
    dumped = json.dumps([e.model_dump(exclude_none=True) for events in shapes.values() for e in events])
    for raw_only in (
        "thinking",
        "Planning the orders",
        "costUSD",
        "service_tier",
        "requestId",
        "/home/synthetic",
        "line 1",
        "F....",
        "delivery_id",
        "synthetic-signature",
        "estimate_hours",
        "priority",
        "Looks good",
        "backend@synthetic",
        "traceback",
        "orders API is done",
    ):
        assert raw_only not in dumped, raw_only


# --- §4 entity ids and §10.4 commands -------------------------------------------------------------


def test_entity_ids_follow_section_4() -> None:
    assert entity_id("synthetic-x", "agent-1") == "synthetic-x:agent-1"
    hashed = entity_id("synthetic-x", "a b")
    assert hashed == "synthetic-x:h." + hashlib.sha256(b"a b").hexdigest()[:32]
    for native in ("h.0123", "x" * 117, "caf" + chr(0xE9), "a/b", "", SK):
        assert entity_id("synthetic-x", native).startswith("synthetic-x:h."), native
    assert entity_id("synthetic-x", "x" * 116) == "synthetic-x:" + "x" * 116  # 128 characters in all
    # Injective: a native that looks like another native's hash is hashed itself.
    looks_hashed = hashed.removeprefix("synthetic-x:")
    assert entity_id("synthetic-x", looks_hashed) != hashed


def test_command_pipeline() -> None:
    assert command_text("ls -la\nrm -rf build") == "ls -la"
    assert command_text("cat > notes.txt <<EOF") == "cat > notes.txt"
    assert command_text("mysql -u app -p" + "hunter") == "mysql -u app -p[REDACTED]"
    long = command_text("echo " + "y" * 2000 + " --password " + "z")
    assert len(long) <= 1024
    assert long.endswith(" [TRUNCATED]")
    cut_secret = command_text("x" * 1000 + " " + SK)
    assert SK[:20] not in cut_secret
    assert len(cut_secret) <= 1024


def test_projection_unqualifies_only_id_positions(shapes: dict[str, list[Event]]) -> None:
    """R-B-P2-006-12(a): free text that happens to start with the provider prefix is kept as is."""
    spawn = next(e for e in shapes["A"] if e.event_type == "agent.spawned")
    tree = json.loads(canonical_json(spawn))
    tree["payload"]["role"] = PROVIDER_A + ":role text"
    tree["event_id"] = "0190a8f2-6b1c-7d3e-8f4a-0000000000aa"
    del tree["source"]["provider_event_id"]
    result = validate_event(tree)
    assert isinstance(result, Accepted)
    projected = projection(result.event)
    assert projected["payload"]["role"] == PROVIDER_A + ":role text"
    assert projected["payload"]["agent_id"] == "backend"
    assert projected["scope"]["agent_id"] == "coordinator"
