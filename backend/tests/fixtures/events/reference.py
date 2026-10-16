"""Deterministic generator of the SYNTHETIC multi-agent reference trace v1 (ADR-0008 §18).

A Coordinator runs the "orders feature" with Backend, Frontend, Testing and
Security Reviewer agents. Every event is built from the scenario below,
validated, put in canonical order and written as canonical JSONL. Regenerate
(then review the diff and update the pinned digest in the test)::

    cd backend && .venv/bin/python -m tests.fixtures.events.reference
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from observatory.events import Event, canonical_json, canonical_order
from tests.fixtures.events.mappers import WORKSPACE, accept, entity_id, uuid7

PROVIDER: Final = "synthetic-reference"
TRACE: Final = Path(__file__).parent / "reference-trace-v1.jsonl"
DIGEST: Final = Path(__file__).parent / "reference-trace-v1.sha256"
_START: Final = datetime(2026, 3, 2, 9, 0, 0, tzinfo=UTC)
_STEP: Final = timedelta(seconds=10)


def q(native: str) -> str:
    """A provider-qualified entity id (§4)."""
    return entity_id(PROVIDER, native)


def _ts(instant: datetime) -> str:
    return f"{instant:%Y-%m-%dT%H:%M:%S}.{instant.microsecond:06d}Z"


class _Trace:
    """Builds events in scenario order: one stream per agent, one correlation id for the feature."""

    def __init__(self) -> None:
        self._rng = random.Random(20260302)  # noqa: S311 (seeded synthetic ids, not cryptography)
        self._seq: dict[str, int] = {}
        self.events: list[Event] = []
        self.ids: dict[str, str] = {}

    def add(
        self,
        label: str,
        agent: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        caused_by: str | None = None,
        self_report: bool = False,
        streamed: bool = True,
        timed: bool = True,
    ) -> None:
        occurred = _START + _STEP * len(self.events)
        scope = {"workspace_id": WORKSPACE, "session_id": q("ref-session-1")}
        if not self_report:
            scope["agent_id"] = q(agent)
        causality = {"correlation_id": q("orders-feature")}
        if caused_by is not None:
            causality["causation_id"] = self.ids[caused_by]
        event_id = uuid7(self._rng, int(occurred.timestamp() * 1000))
        tree = {
            "spec_version": "1.0",
            "event_id": event_id,
            "event_type": event_type,
            "scope": scope,
            "time": {"observed_at": _ts(occurred + timedelta(milliseconds=500))},
            "source": {"provider": PROVIDER, "adapter": {"name": f"{PROVIDER}-mapper", "version": "1.0.0"}},
            "causality": causality,
            "payload": payload,
        }
        if timed:  # otherwise the source gave no time and observed_at orders the event (§6)
            tree["time"]["occurred_at"] = _ts(occurred)
        if streamed:
            seq = self._seq.get(agent, 0)
            self._seq[agent] = seq + 1
            tree["source"] |= {"stream_id": q(f"stream-{agent}"), "seq": seq}
        self.events.append(accept(tree))
        self.ids[label] = event_id

    def tool(self, label: str, agent: str, call: str, name: str, kind: str, **fields: Any) -> None:
        """A tool call: started, then finished (caused by the start)."""
        outcome = fields.pop("outcome", "succeeded")
        finish: dict[str, Any] = {
            "call_id": q(call),
            "outcome": outcome,
            "duration_ms": fields.pop("duration_ms", 900),
        }
        if "exit_code" in fields:
            finish["exit_code"] = fields.pop("exit_code")
        self.add(
            f"{label}.start",
            agent,
            "tool.call_started",
            {"call_id": q(call), "tool_name": name, "kind": kind, **fields},
        )
        self.add(f"{label}.end", agent, "tool.call_finished", finish, caused_by=f"{label}.start")


def _scenario(t: _Trace) -> None:
    t.add(
        "session", "coordinator", "session.started", {"session_id": q("ref-session-1"), "initiator": "human"}
    )
    t.add(
        "spawn.coordinator",
        "coordinator",
        "agent.spawned",
        {"agent_id": q("coordinator"), "role": "Coordinator", "model": "synthetic-model-1"},
        self_report=True,
    )
    for agent, role in (
        ("backend", "Backend"),
        ("frontend", "Frontend"),
        ("testing", "Testing"),
        ("security", "Security Reviewer"),
    ):
        t.add(
            f"spawn.{agent}",
            "coordinator",
            "agent.spawned",
            {
                "agent_id": q(agent),
                "parent_agent_id": q("coordinator"),
                "role": role,
                "model": "synthetic-model-1",
            },
        )
    # The task DAG: api <- ui <- tests <- review.
    t.add(
        "task.api", "coordinator", "task.created", {"task_id": q("task-api"), "title": "Build the orders API"}
    )
    t.add(
        "task.ui",
        "coordinator",
        "task.created",
        {"task_id": q("task-ui"), "title": "Build the orders page", "depends_on": [q("task-api")]},
    )
    t.add(
        "task.tests",
        "coordinator",
        "task.created",
        {
            "task_id": q("task-tests"),
            "title": "Test the orders feature",
            "depends_on": sorted([q("task-api"), q("task-ui")]),
        },
    )
    t.add(
        "task.review",
        "coordinator",
        "task.created",
        {
            "task_id": q("task-review"),
            "title": "Security review of the orders API",
            "parent_task_id": q("task-api"),
        },
    )
    t.add(
        "dep.review",
        "coordinator",
        "task.dependency_added",
        {"task_id": q("task-review"), "depends_on_task_id": q("task-tests")},
    )
    for task, agent in (("task-api", "backend"), ("task-ui", "frontend"), ("task-tests", "testing")):
        t.add(
            f"assign.{task}",
            "coordinator",
            "task.assigned",
            {"task_id": q(task), "assignee_agent_id": q(agent)},
        )
    # Backend: write, search, rename.
    t.add(
        "api.progress", "backend", "task.status_changed", {"task_id": q("task-api"), "status": "in_progress"}
    )
    t.tool("b1", "backend", "call-b1", "Write", "file_write", target_path="src/orders.py")
    t.add(
        "b1.file",
        "backend",
        "file.changed",
        {"path": "src/orders.py", "change": "created", "call_id": q("call-b1"), "lines_added": 40},
        caused_by="b1.end",
    )
    t.tool("b2", "backend", "call-b2", "Grep", "search", query="def create_order")
    t.tool(
        "b3",
        "backend",
        "call-b3",
        "Bash",
        "command",
        command="git mv src/orders.py src/orders_api.py",
        exit_code=0,
    )
    t.add(
        "b3.file",
        "backend",
        "file.changed",
        {
            "path": "src/orders_api.py",
            "change": "renamed",
            "previous_path": "src/orders.py",
            "call_id": q("call-b3"),
        },
        caused_by="b3.end",
    )
    t.add(
        "b.usage",
        "backend",
        "usage.recorded",
        {
            "usage": {
                "input_tokens": 1300,
                "cached_input_tokens": 800,
                "output_tokens": 300,
                "reported_cost": {"amount": "0.0123", "currency": "USD"},
            },
            "accounting": "delta",
            "unit": "model_call",
            "model": "synthetic-model-1",
        },
    )
    # Frontend.
    t.add(
        "ui.progress", "frontend", "task.status_changed", {"task_id": q("task-ui"), "status": "in_progress"}
    )
    t.tool("f1", "frontend", "call-f1", "Write", "file_write", target_path="web/src/OrdersPage.tsx")
    t.add(
        "f1.file",
        "frontend",
        "file.changed",
        {"path": "web/src/OrdersPage.tsx", "change": "created", "call_id": q("call-f1"), "lines_added": 85},
        caused_by="f1.end",
    )
    # Testing: a failing run, an error, then a handoff to Backend.
    t.add(
        "tests.progress",
        "testing",
        "task.status_changed",
        {"task_id": q("task-tests"), "status": "in_progress"},
    )
    t.tool(
        "t1",
        "testing",
        "call-t1",
        "Bash",
        "command",
        command="pytest -q tests/test_orders.py",
        outcome="failed",
        exit_code=1,
    )
    t.add(
        "t1.run",
        "testing",
        "test.run_completed",
        {
            "run_id": q("run-1"),
            "outcome": "failed",
            "call_id": q("call-t1"),
            "framework": "pytest",
            "passed": 11,
            "failed": 1,
            "skipped": 0,
            "errored": 0,
            "duration_ms": 4200,
        },
        caused_by="t1.end",
    )
    t.add(
        "t1.error",
        "testing",
        "error.reported",
        {
            "error_code": "test_failure",
            "severity": "error",
            "message": "1 test failed in tests/test_orders.py",
            "call_id": q("call-t1"),
        },
        caused_by="t1.run",
    )
    t.add(
        "handoff.msg",
        "testing",
        "message.sent",
        {
            "message_id": q("msg-1"),
            "intent": "handoff",
            "to_agent_ids": [q("backend")],
            "size_bytes": 512,
        },
    )
    t.add(
        "handoff.assign",
        "coordinator",
        "task.assigned",
        {
            "task_id": q("task-tests"),
            "assignee_agent_id": q("backend"),
            "previous_assignee_agent_id": q("testing"),
        },
        caused_by="handoff.msg",
    )
    # Backend fixes, then retries the failed run.
    t.tool("b4", "backend", "call-b4", "Write", "file_write", target_path="src/orders_api.py")
    t.add(
        "b4.file",
        "backend",
        "file.changed",
        {
            "path": "src/orders_api.py",
            "change": "modified",
            "call_id": q("call-b4"),
            "lines_added": 3,
            "lines_removed": 1,
        },
        caused_by="b4.end",
    )
    t.tool(
        "b5",
        "backend",
        "call-b5",
        "Bash",
        "command",
        command="pytest -q tests/test_orders.py",
        attempt=2,
        retry_of_call_id=q("call-t1"),
        exit_code=0,
    )
    t.add(
        "b5.run",
        "backend",
        "test.run_completed",
        {
            "run_id": q("run-2"),
            "outcome": "passed",
            "call_id": q("call-b5"),
            "framework": "pytest",
            "passed": 12,
            "failed": 0,
            "skipped": 0,
            "errored": 0,
            "duration_ms": 4100,
        },
        caused_by="b5.end",
    )
    # Security review: changes requested, fixed, approved.
    t.add(
        "assign.review",
        "coordinator",
        "task.assigned",
        {"task_id": q("task-review"), "assignee_agent_id": q("security")},
    )
    t.add(
        "review.1",
        "security",
        "review.verdict_recorded",
        {
            "review_id": q("rev-1"),
            "verdict": "request_changes",
            "subject_task_id": q("task-api"),
            "findings": 2,
            "blocking_findings": 1,
        },
    )
    t.tool("b6", "backend", "call-b6", "Write", "file_write", target_path="src/orders_api.py")
    t.add(
        "b6.file",
        "backend",
        "file.changed",
        {
            "path": "src/orders_api.py",
            "change": "modified",
            "call_id": q("call-b6"),
            "lines_added": 6,
            "lines_removed": 2,
        },
        caused_by="b6.end",
    )
    t.add(
        "review.2",
        "security",
        "review.verdict_recorded",
        {
            "review_id": q("rev-2"),
            "verdict": "approve",
            "subject_task_id": q("task-api"),
            "findings": 0,
            "blocking_findings": 0,
        },
        caused_by="b6.file",
    )
    t.add(
        "api.done",
        "backend",
        "task.status_changed",
        {
            "task_id": q("task-api"),
            "status": "completed",
            "evidence_event_ids": sorted([t.ids["b5.run"], t.ids["b6.file"], t.ids["review.2"]]),
        },
    )
    # The dependants complete only after the task they depend on.
    t.add(
        "ui.done",
        "frontend",
        "task.status_changed",
        {"task_id": q("task-ui"), "status": "completed", "evidence_event_ids": [t.ids["f1.file"]]},
    )
    t.add(
        "tests.done",
        "backend",
        "task.status_changed",
        {
            "task_id": q("task-tests"),
            "status": "completed",
            "evidence_event_ids": sorted([t.ids["b5.run"]]),
        },
    )
    t.add(
        "review.done",
        "security",
        "task.status_changed",
        {
            "task_id": q("task-review"),
            "status": "completed",
            "evidence_event_ids": [t.ids["review.2"]],
        },
    )
    # Usage totals, termination, end.
    t.add(
        "b.total",
        "backend",
        "usage.recorded",
        {
            "usage": {"input_tokens": 5200, "cached_input_tokens": 3100, "output_tokens": 1400},
            "accounting": "cumulative",
            "unit": "agent",
            "unit_id": q("backend"),
            "model": "synthetic-model-1",
        },
    )
    for agent in ("backend", "frontend", "testing", "security"):
        t.add(f"stop.{agent}", agent, "agent.terminated", {"agent_id": q(agent), "reason": "completed"})
    # Reported by a billing exporter: no stream, no source time (ordered by observed_at, §6).
    t.add(
        "session.total",
        "coordinator",
        "usage.recorded",
        {
            "usage": {
                "input_tokens": 20400,
                "cached_input_tokens": 11800,
                "output_tokens": 5300,
                "reported_cost": {"amount": "0.2041", "currency": "USD"},
            },
            "accounting": "cumulative",
            "unit": "session",
            "unit_id": q("ref-session-1"),
        },
        streamed=False,
        timed=False,
    )
    t.add(
        "session.end",
        "coordinator",
        "session.ended",
        {"session_id": q("ref-session-1"), "outcome": "completed"},
    )
    t.add(
        "stop.coordinator",
        "coordinator",
        "agent.terminated",
        {"agent_id": q("coordinator"), "reason": "completed"},
    )


def build_trace() -> list[Event]:
    """The reference events in canonical order (which is also scenario order)."""
    trace = _Trace()
    _scenario(trace)
    return canonical_order(trace.events)


def render(events: list[Event]) -> bytes:
    """Canonical JSONL: one canonical event per line, each line ending in LF."""
    return b"".join(canonical_json(event) + b"\n" for event in events)


def digest_line(data: bytes) -> str:
    return f"{hashlib.sha256(data).hexdigest()}  {TRACE.name}\n"


def main() -> None:
    data = render(build_trace())
    TRACE.write_bytes(data)
    DIGEST.write_text(digest_line(data), encoding="utf-8")


if __name__ == "__main__":
    main()
