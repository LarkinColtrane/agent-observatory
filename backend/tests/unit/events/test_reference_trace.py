"""The versioned multi-agent reference trace (ADR-0008 §18; AO-P2-005 AC2).

Regenerate after an intended change, review the diff, then update ``PINNED``::

    cd backend && .venv/bin/python -m tests.fixtures.events.reference
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter

import pytest

from observatory.events import Accepted, Event, canonical_json, canonical_order, parse_event
from tests.fixtures.events.reference import DIGEST, TRACE, build_trace, digest_line, q, render

PINNED = "6443d5f78ac0397c46dd5e514c675f8a82bd2dac7253b06563bb74663d96dbd8"
AGENTS = {q(a) for a in ("coordinator", "backend", "frontend", "testing", "security")}


@pytest.fixture(scope="module")
def events() -> list[Event]:
    parsed = [parse_event(line) for line in TRACE.read_bytes().splitlines()]
    assert all(isinstance(p, Accepted) for p in parsed)
    return [p.event for p in parsed if isinstance(p, Accepted)]


def test_trace_is_byte_stable_and_pinned() -> None:
    data = TRACE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == PINNED
    assert DIGEST.read_text(encoding="utf-8") == digest_line(data) == f"{PINNED}  reference-trace-v1.jsonl\n"
    assert render(build_trace()) == data  # regenerating gives the same bytes
    assert data.endswith(b"\n")
    assert b"\r" not in data
    assert b"\n\n" not in data


def test_every_line_reparses_to_the_same_bytes(events: list[Event]) -> None:
    lines = TRACE.read_bytes().splitlines()
    assert [canonical_json(e) for e in events] == lines


def test_canonical_order_reproduces_the_file(events: list[Event]) -> None:
    rng = random.Random(58)  # noqa: S311 (seeded test data, not cryptography)
    for _ in range(20):
        shuffled = events[:]
        rng.shuffle(shuffled)
        assert [e.event_id for e in canonical_order(shuffled)] == [e.event_id for e in events]


def test_scenario_coverage(events: list[Event]) -> None:
    kinds = Counter(e.event_type for e in events)
    assert set(kinds) == {
        "session.started",
        "session.ended",
        "agent.spawned",
        "agent.terminated",
        "task.created",
        "task.assigned",
        "task.status_changed",
        "task.dependency_added",
        "tool.call_started",
        "tool.call_finished",
        "file.changed",
        "test.run_completed",
        "review.verdict_recorded",
        "message.sent",
        "error.reported",
        "usage.recorded",
    }
    payloads = [(e.event_type, e.payload.model_dump(exclude_none=True)) for e in events]
    spawned = {p["agent_id"] for t, p in payloads if t == "agent.spawned"}
    assert spawned == AGENTS
    assert {p.get("parent_agent_id") for t, p in payloads if t == "agent.spawned"} == {None, q("coordinator")}
    assert any(t == "task.assigned" and "previous_assignee_agent_id" in p for t, p in payloads)
    assert any(t == "message.sent" and p["intent"] == "handoff" for t, p in payloads)
    assert {p["kind"] for t, p in payloads if t == "tool.call_started"} >= {"command", "file_write", "search"}
    assert any(t == "file.changed" and p["change"] == "renamed" for t, p in payloads)
    runs = [p["outcome"] for t, p in payloads if t == "test.run_completed"]
    assert runs == ["failed", "passed"]
    retry = next(p for t, p in payloads if t == "tool.call_started" and "attempt" in p)
    assert (retry["attempt"], retry["retry_of_call_id"]) == (2, q("call-t1"))
    verdicts = [p["verdict"] for t, p in payloads if t == "review.verdict_recorded"]
    assert verdicts == ["request_changes", "approve"]
    usage = [p for t, p in payloads if t == "usage.recorded"]
    assert {u["accounting"] for u in usage} == {"delta", "cumulative"}
    assert all("unit_id" in u for u in usage if u["accounting"] == "cumulative")
    assert any("reported_cost" in u["usage"] for u in usage)
    assert sum(1 for t, p in payloads if t == "task.status_changed" and "evidence_event_ids" in p) >= 3
    assert kinds["error.reported"] == 1


def test_references_resolve_within_the_trace(events: list[Event]) -> None:
    """Test-only reference checks (P4 does these for real): every reference points backwards in the trace."""
    seen_events: set[str] = set()
    spawned: set[str] = set()
    tasks: dict[str, set[str]] = {}
    calls: set[str] = set()
    for event in events:
        payload = event.payload.model_dump(exclude_none=True)
        if event.causality is not None and event.causality.causation_id is not None:
            assert event.causality.causation_id in seen_events
        if event.scope.agent_id is not None and event.event_type != "session.started":
            assert event.scope.agent_id in spawned
        match event.event_type:
            case "agent.spawned":
                assert payload.get("parent_agent_id") in spawned | {None}  # parents are spawned first
                spawned.add(payload["agent_id"])
            case "task.created":
                assert set(payload.get("depends_on", ())) <= set(tasks)
                assert payload.get("parent_task_id") in set(tasks) | {None}
                tasks[payload["task_id"]] = set(payload.get("depends_on", ()))
            case "task.dependency_added":
                tasks[payload["task_id"]].add(payload["depends_on_task_id"])
            case "task.assigned":
                assert payload["task_id"] in tasks
                assert payload["assignee_agent_id"] in spawned
            case "task.status_changed":
                assert set(payload.get("evidence_event_ids", ())) <= seen_events
            case "tool.call_started":
                assert payload.get("retry_of_call_id") in calls | {None}
                calls.add(payload["call_id"])
            case "tool.call_finished" | "file.changed" | "test.run_completed" | "error.reported":
                assert payload.get("call_id") in calls | {None}
            case _:
                pass
        seen_events.add(event.event_id)
    _assert_acyclic(tasks)


def _assert_acyclic(graph: dict[str, set[str]]) -> None:
    remaining = {node: set(edges) for node, edges in graph.items()}
    while remaining:
        ready = [node for node, edges in remaining.items() if not edges & set(remaining)]
        assert ready, "the task graph has a cycle"
        for node in ready:
            del remaining[node]


def test_acyclicity_check_detects_a_cycle() -> None:
    with pytest.raises(AssertionError, match="cycle"):
        _assert_acyclic({"a": {"b"}, "b": {"a"}})
