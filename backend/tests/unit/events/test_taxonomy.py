"""The 16 payload types and their cross-field, scope and self-reference rules (ADR-0008 §§8, 9; AO-P2-004).

Each type has a full and a minimal valid case and adversarial invalid cases:
unknown fields (message-content smuggling), kind gating, oversized arrays,
unsorted or duplicate id sets, self references and required scope.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

import pytest

from observatory.events import Accepted, RejectCode, Rejected, parse_event
from observatory.events.currency import ISO_4217_CURRENCIES
from observatory.events.taxonomy import CORE_FAMILIES, PAYLOADS
from tests.unit.events.factory import DELETE, EVENT_ID, OTHER_ID, SK, accept, raw, reject, tree

SCHEMA, REFERENCE = RejectCode.SCHEMA_VIOLATION, RejectCode.INVALID_REFERENCE
NO_AGENT = ("scope.agent_id", DELETE)
USAGE = {"input_tokens": 1200, "output_tokens": 345, "cached_input_tokens": 800, "reasoning_tokens": 12}
COST = {"amount": "0.012", "currency": "USD"}

FULL: dict[str, dict[str, Any]] = {
    "session.started": {"session_id": "sess-1", "initiator": "agent"},
    "session.ended": {"session_id": "sess-1", "outcome": "completed"},
    "agent.spawned": {
        "agent_id": "claude-code:agent-2",
        "parent_agent_id": "claude-code:agent-1",
        "role": "Backend",
        "display_name": "Backend Engineer",
        "model": "claude-opus-5",
    },
    "agent.terminated": {"agent_id": "claude-code:agent-2", "reason": "timeout"},
    "task.created": {
        "task_id": "task-2",
        "title": "Build the API",
        "parent_task_id": "task-1",
        "depends_on": ["task-0", "task-1"],
    },
    "task.assigned": {"task_id": "task-2", "assignee_agent_id": "a-2", "previous_assignee_agent_id": "a-1"},
    "task.status_changed": {
        "task_id": "task-2",
        "status": "completed",
        "reason_code": "done",
        "evidence_event_ids": sorted([EVENT_ID, OTHER_ID]),
    },
    "task.dependency_added": {"task_id": "task-2", "depends_on_task_id": "task-1"},
    "tool.call_started": {
        "call_id": "call-2",
        "tool_name": "Bash",
        "kind": "command",
        "attempt": 2,
        "retry_of_call_id": "call-1",
        "command": "pytest -q tests/unit",
    },
    "tool.call_finished": {
        "call_id": "call-2",
        "outcome": "failed",
        "duration_ms": 1200,
        "exit_code": -(2**31),
        "error_code": "nonzero_exit",
    },
    "file.changed": {
        "path": "src/api.py",
        "change": "renamed",
        "previous_path": "src/app.py",
        "call_id": "call-2",
        "lines_added": 3,
        "lines_removed": 0,
    },
    "test.run_completed": {
        "run_id": "run-1",
        "outcome": "failed",
        "call_id": "call-2",
        "framework": "pytest",
        "passed": 10,
        "failed": 1,
        "skipped": 0,
        "errored": 0,
        "duration_ms": 2_592_000_000,
    },
    "review.verdict_recorded": {
        "review_id": "rev-1",
        "verdict": "request_changes",
        "subject_task_id": "task-2",
        "findings": 3,
        "blocking_findings": 1,
    },
    "message.sent": {
        "message_id": "msg-2",
        "intent": "handoff",
        "to_agent_ids": ["a-2", "a-3"],
        "channel_id": "ch-1",
        "in_reply_to_message_id": "msg-1",
        "size_bytes": 120,
    },
    "error.reported": {
        "error_code": "rate_limited",
        "severity": "error",
        "message": "Rate limit reached",
        "call_id": "call-2",
    },
    "usage.recorded": {
        "usage": {**USAGE, "total_tokens": 1545, "reported_cost": dict(COST), "estimated_cost": dict(COST)},
        "accounting": "cumulative",
        "unit": "session",
        "unit_id": "sess-1",
        "model": "claude-opus-5",
        "call_id": "call-2",
        "pricing_ref": "ao-prices/2026-01",
    },
}

MINIMAL: dict[str, dict[str, Any]] = {
    "session.started": {"session_id": "sess-1"},
    "session.ended": {"session_id": "sess-1", "outcome": "unknown"},
    "agent.spawned": {"agent_id": "claude-code:agent-2"},
    "agent.terminated": {"agent_id": "claude-code:agent-2", "reason": "unknown"},
    "task.created": {"task_id": "task-2"},
    "task.assigned": {"task_id": "task-2", "assignee_agent_id": "a-2"},
    "task.status_changed": {"task_id": "task-2", "status": "blocked"},
    "task.dependency_added": {"task_id": "task-2", "depends_on_task_id": "task-1"},
    "tool.call_started": {"call_id": "call-2", "tool_name": "Read", "kind": "other"},
    "tool.call_finished": {"call_id": "call-2", "outcome": "succeeded"},
    "file.changed": {"path": "src/api.py", "change": "deleted"},
    "test.run_completed": {"run_id": "run-1", "outcome": "passed"},
    "review.verdict_recorded": {"review_id": "rev-1", "verdict": "comment"},
    "message.sent": {"message_id": "msg-2", "intent": "broadcast", "channel_id": "ch-1"},
    "error.reported": {"error_code": "e", "severity": "fatal"},
    "usage.recorded": {"usage": {"output_tokens": 0}, "accounting": "delta", "unit": "turn"},
}


def event(event_type: str, payload: dict[str, Any], *changes: tuple[str, object]) -> dict[str, Any]:
    return tree(("event_type", event_type), ("payload", payload), *changes)


def changed(event_type: str, **fields: object) -> dict[str, Any]:
    """``FULL[event_type]`` with fields replaced (``DELETE`` removes one)."""
    payload = copy.deepcopy(FULL[event_type])
    for name, value in fields.items():
        if value is DELETE:
            payload.pop(name, None)
        else:
            payload[name] = value
    return payload


def test_exactly_the_sixteen_types() -> None:
    assert set(PAYLOADS) == {"1.0"}
    assert set(PAYLOADS["1.0"]) == set(FULL) == set(MINIMAL)
    assert len(FULL) == 16
    assert {"session", "agent", "task", "tool", "file", "test", "review", "message", "error", "usage"} == set(
        CORE_FAMILIES
    )
    for model in PAYLOADS["1.0"].values():
        config = model.model_config
        assert (config.get("extra"), config.get("strict"), config.get("frozen")) == ("forbid", True, True)


@pytest.mark.parametrize("event_type", sorted(FULL))
def test_valid_payloads(event_type: str) -> None:
    for payload in (FULL[event_type], MINIMAL[event_type]):
        data = event(event_type, payload)
        accepted = accept(data)
        assert type(accepted.event.payload) is PAYLOADS["1.0"][event_type]
        assert json.loads(raw(accepted.event.model_dump(exclude_none=True)))["payload"] == payload
        assert isinstance(parse_event(raw(data)), Accepted)


@pytest.mark.parametrize("event_type", sorted(FULL))
@pytest.mark.parametrize(
    "smuggled", ["content", "prompt", "messages", "body", "stdout", "output", "zz_extra"]
)
def test_unknown_fields_are_schema_violations(event_type: str, smuggled: str) -> None:
    rejected = reject(event(event_type, {**FULL[event_type], smuggled: "x"}))
    assert (rejected.code, rejected.pointer) == (SCHEMA, "/payload")
    assert smuggled not in repr(rejected)


@pytest.mark.parametrize("event_type", sorted(FULL))
def test_required_fields_and_nulls(event_type: str) -> None:
    for name in MINIMAL[event_type]:
        payload = {k: v for k, v in MINIMAL[event_type].items() if k != name}
        # message.sent without its only recipient fails the recipient rule instead
        expected = "to_agent_ids" if (event_type, name) == ("message.sent", "channel_id") else name
        assert (reject(event(event_type, payload)).pointer, name) == (f"/payload/{expected}", name)
    for name in FULL[event_type]:
        nulled = parse_event(raw(event(event_type, {**FULL[event_type], name: None})))
        assert isinstance(nulled, Rejected)
        assert (nulled.code, nulled.pointer) == (SCHEMA, f"/payload/{name}")


@dataclass(frozen=True)
class Case:
    """One invalid payload and the rejection it must produce."""

    name: str
    event_type: str
    payload: dict[str, Any]
    pointer: str
    code: RejectCode = SCHEMA
    changes: tuple[tuple[str, object], ...] = ()


INVALID: list[Case] = [
    # session.*: required scope
    Case(
        name="session scope differs",
        event_type="session.ended",
        payload=changed("session.ended"),
        pointer="/scope/session_id",
        changes=(("scope.session_id", "sess-2"),),
    ),
    Case(
        name="session scope missing",
        event_type="session.started",
        payload=changed("session.started"),
        pointer="/scope/session_id",
        changes=(("scope.session_id", DELETE),),
    ),
    Case(
        name="initiator enum",
        event_type="session.started",
        payload=changed("session.started", initiator="robot"),
        pointer="/payload/initiator",
    ),
    Case(
        name="outcome enum",
        event_type="session.ended",
        payload=changed("session.ended", outcome="done"),
        pointer="/payload/outcome",
    ),
    # agent.*
    Case(
        name="own parent",
        event_type="agent.spawned",
        payload=changed("agent.spawned", parent_agent_id="claude-code:agent-2"),
        pointer="/payload/parent_agent_id",
        code=REFERENCE,
    ),
    Case(
        name="self spawn",
        event_type="agent.spawned",
        payload=changed("agent.spawned", parent_agent_id=DELETE),
        pointer="/payload/agent_id",
        code=REFERENCE,
        changes=(("scope.agent_id", "claude-code:agent-2"),),
    ),
    Case(
        name="role too long",
        event_type="agent.spawned",
        payload=changed("agent.spawned", role="r" * 65),
        pointer="/payload/role",
    ),
    Case(
        name="role multi-line",
        event_type="agent.spawned",
        payload=changed("agent.spawned", role="a\nb"),
        pointer="/payload/role",
    ),
    Case(
        name="model with space",
        event_type="agent.spawned",
        payload=changed("agent.spawned", model="claude opus"),
        pointer="/payload/model",
    ),
    Case(
        name="reason enum",
        event_type="agent.terminated",
        payload=changed("agent.terminated", reason="exploded"),
        pointer="/payload/reason",
    ),
    # task.*
    Case(
        name="unsorted set",
        event_type="task.created",
        payload=changed("task.created", depends_on=["task-1", "task-0"]),
        pointer="/payload/depends_on",
    ),
    Case(
        name="duplicate set",
        event_type="task.created",
        payload=changed("task.created", depends_on=["task-0", "task-0"]),
        pointer="/payload/depends_on",
    ),
    Case(
        name="empty set",
        event_type="task.created",
        payload=changed("task.created", depends_on=[]),
        pointer="/payload/depends_on",
    ),
    Case(
        name="oversized set",
        event_type="task.created",
        payload=changed("task.created", depends_on=[f"t{i:03d}" for i in range(65)]),
        pointer="/payload/depends_on",
    ),
    Case(
        name="bad set member",
        event_type="task.created",
        payload=changed("task.created", depends_on=["a b"]),
        pointer="/payload/depends_on/0",
    ),
    Case(
        name="own dependency",
        event_type="task.created",
        payload=changed("task.created", depends_on=["task-0", "task-2"]),
        pointer="/payload/depends_on/1",
        code=REFERENCE,
    ),
    Case(
        name="own parent task",
        event_type="task.created",
        payload=changed("task.created", parent_task_id="task-2"),
        pointer="/payload/parent_task_id",
        code=REFERENCE,
    ),
    Case(
        name="title too long",
        event_type="task.created",
        payload=changed("task.created", title="t" * 201),
        pointer="/payload/title",
    ),
    Case(
        name="handoff to self",
        event_type="task.assigned",
        payload=changed("task.assigned", previous_assignee_agent_id="a-2"),
        pointer="/payload/previous_assignee_agent_id",
        code=REFERENCE,
    ),
    Case(
        name="blockers when not blocked",
        event_type="task.status_changed",
        payload=changed(
            "task.status_changed",
            status="in_progress",
            evidence_event_ids=DELETE,
            blocked_by_task_ids=["t-1"],
        ),
        pointer="/payload/blocked_by_task_ids",
    ),
    Case(
        name="evidence when pending",
        event_type="task.status_changed",
        payload=changed("task.status_changed", status="pending"),
        pointer="/payload/evidence_event_ids",
    ),
    Case(
        name="both gates: smallest pointer",
        event_type="task.status_changed",
        payload=changed("task.status_changed", status="cancelled", blocked_by_task_ids=["t-1"]),
        pointer="/payload/blocked_by_task_ids",
    ),
    Case(
        name="blocked by itself",
        event_type="task.status_changed",
        payload=changed(
            "task.status_changed", status="blocked", evidence_event_ids=DELETE, blocked_by_task_ids=["task-2"]
        ),
        pointer="/payload/blocked_by_task_ids/0",
        code=REFERENCE,
    ),
    Case(
        name="evidence not a uuid",
        event_type="task.status_changed",
        payload=changed("task.status_changed", evidence_event_ids=["e-1"]),
        pointer="/payload/evidence_event_ids/0",
    ),
    Case(
        name="too much evidence",
        event_type="task.status_changed",
        payload=changed(
            "task.status_changed",
            evidence_event_ids=[f"{i:08x}-0000-4000-8000-000000000000" for i in range(33)],
        ),
        pointer="/payload/evidence_event_ids",
    ),
    Case(
        name="depends on itself",
        event_type="task.dependency_added",
        payload=changed("task.dependency_added", depends_on_task_id="task-2"),
        pointer="/payload/depends_on_task_id",
        code=REFERENCE,
    ),
    # tool.*
    Case(
        name="tool without agent",
        event_type="tool.call_started",
        payload=changed("tool.call_started"),
        pointer="/scope/agent_id",
        changes=(NO_AGENT,),
    ),
    Case(
        name="finish without agent",
        event_type="tool.call_finished",
        payload=changed("tool.call_finished"),
        pointer="/scope/agent_id",
        changes=(NO_AGENT,),
    ),
    Case(
        name="command on search",
        event_type="tool.call_started",
        payload=changed("tool.call_started", kind="search"),
        pointer="/payload/command",
    ),
    Case(
        name="query on command",
        event_type="tool.call_started",
        payload=changed("tool.call_started", query="needle"),
        pointer="/payload/query",
    ),
    Case(
        name="path on web",
        event_type="tool.call_started",
        payload=changed("tool.call_started", kind="web", command=DELETE, target_path="a.py"),
        pointer="/payload/target_path",
    ),
    Case(
        name="retry without attempt",
        event_type="tool.call_started",
        payload=changed("tool.call_started", attempt=DELETE),
        pointer="/payload/retry_of_call_id",
    ),
    Case(
        name="two gates: smallest pointer",
        event_type="tool.call_started",
        payload=changed("tool.call_started", kind="other", attempt=DELETE),
        pointer="/payload/command",
    ),
    Case(
        name="attempt 1",
        event_type="tool.call_started",
        payload=changed("tool.call_started", attempt=1),
        pointer="/payload/attempt",
    ),
    Case(
        name="attempt 1001",
        event_type="tool.call_started",
        payload=changed("tool.call_started", attempt=1001),
        pointer="/payload/attempt",
    ),
    Case(
        name="retry of itself",
        event_type="tool.call_started",
        payload=changed("tool.call_started", retry_of_call_id="call-2"),
        pointer="/payload/retry_of_call_id",
        code=REFERENCE,
    ),
    Case(
        name="heredoc command",
        event_type="tool.call_started",
        payload=changed("tool.call_started", command="cat <<EOF\nbody"),
        pointer="/payload/command",
    ),
    Case(
        name="command too long",
        event_type="tool.call_started",
        payload=changed("tool.call_started", command="c" * 1025),
        pointer="/payload/command",
    ),
    Case(
        name="absolute target",
        event_type="tool.call_started",
        payload=changed("tool.call_started", kind="file_read", command=DELETE, target_path="/etc/hosts"),
        pointer="/payload/target_path",
    ),
    Case(
        name="exit code > int32",
        event_type="tool.call_finished",
        payload=changed("tool.call_finished", exit_code=2**31),
        pointer="/payload/exit_code",
    ),
    Case(
        name="duration > 30 days",
        event_type="tool.call_finished",
        payload=changed("tool.call_finished", duration_ms=2_592_000_001),
        pointer="/payload/duration_ms",
    ),
    Case(
        name="bool exit code",
        event_type="tool.call_finished",
        payload=changed("tool.call_finished", exit_code=True),
        pointer="/payload/exit_code",
    ),
    # file.changed
    Case(
        name="rename without previous",
        event_type="file.changed",
        payload=changed("file.changed", previous_path=DELETE),
        pointer="/payload/previous_path",
    ),
    Case(
        name="previous without rename",
        event_type="file.changed",
        payload=changed("file.changed", change="modified"),
        pointer="/payload/previous_path",
    ),
    Case(
        name="rename onto itself",
        event_type="file.changed",
        payload=changed("file.changed", previous_path="src/api.py"),
        pointer="/payload/previous_path",
        code=REFERENCE,
    ),
    Case(
        name="file call without agent",
        event_type="file.changed",
        payload=changed("file.changed"),
        pointer="/scope/agent_id",
        changes=(NO_AGENT,),
    ),
    Case(
        name="count too large",
        event_type="file.changed",
        payload=changed("file.changed", lines_added=10**9 + 1),
        pointer="/payload/lines_added",
    ),
    Case(
        name="traversal",
        event_type="file.changed",
        payload=changed("file.changed", path="src/../../x"),
        pointer="/payload/path",
    ),
    # test, review
    Case(
        name="negative count",
        event_type="test.run_completed",
        payload=changed("test.run_completed", passed=-1),
        pointer="/payload/passed",
    ),
    Case(
        name="framework not a code",
        event_type="test.run_completed",
        payload=changed("test.run_completed", framework="PyTest"),
        pointer="/payload/framework",
    ),
    Case(
        name="verdict enum",
        event_type="review.verdict_recorded",
        payload=changed("review.verdict_recorded", verdict="lgtm"),
        pointer="/payload/verdict",
    ),
    Case(
        name="findings as string",
        event_type="review.verdict_recorded",
        payload=changed("review.verdict_recorded", findings="3"),
        pointer="/payload/findings",
    ),
    # message, error
    Case(
        name="no recipient",
        event_type="message.sent",
        payload=changed("message.sent", to_agent_ids=DELETE, channel_id=DELETE),
        pointer="/payload/to_agent_ids",
    ),
    Case(
        name="unsorted recipients",
        event_type="message.sent",
        payload=changed("message.sent", to_agent_ids=["a-3", "a-2"]),
        pointer="/payload/to_agent_ids",
    ),
    Case(
        name="reply to itself",
        event_type="message.sent",
        payload=changed("message.sent", in_reply_to_message_id="msg-2"),
        pointer="/payload/in_reply_to_message_id",
        code=REFERENCE,
    ),
    Case(
        name="severity enum",
        event_type="error.reported",
        payload=changed("error.reported", severity="panic"),
        pointer="/payload/severity",
    ),
    Case(
        name="message too long",
        event_type="error.reported",
        payload=changed("error.reported", message="m" * 513),
        pointer="/payload/message",
    ),
    # usage.recorded (§9)
    Case(
        name="cumulative without unit_id",
        event_type="usage.recorded",
        payload=changed("usage.recorded", unit_id=DELETE),
        pointer="/payload/unit_id",
    ),
    Case(
        name="pricing_ref without estimate",
        event_type="usage.recorded",
        payload=changed("usage.recorded", usage=USAGE),
        pointer="/payload/pricing_ref",
    ),
    Case(
        name="estimate without pricing_ref",
        event_type="usage.recorded",
        payload=changed("usage.recorded", pricing_ref=DELETE),
        pointer="/payload/pricing_ref",
    ),
    Case(
        name="x-prefixed currency",
        event_type="usage.recorded",
        payload=changed(
            "usage.recorded", usage={**USAGE, "estimated_cost": {"amount": "1", "currency": "XAU"}}
        ),
        pointer="/payload/usage/estimated_cost/currency",
    ),
    Case(
        name="withdrawn currency",
        event_type="usage.recorded",
        payload=changed(
            "usage.recorded",
            usage={**USAGE, "reported_cost": {"amount": "1", "currency": "HRK"}},
            pricing_ref=DELETE,
        ),
        pointer="/payload/usage/reported_cost/currency",
    ),
    Case(
        name="not a currency",
        event_type="usage.recorded",
        payload=changed(
            "usage.recorded",
            usage={**USAGE, "reported_cost": {"amount": "1", "currency": "BTC"}},
            pricing_ref=DELETE,
        ),
        pointer="/payload/usage/reported_cost/currency",
    ),
    Case(
        name="session unit mismatch",
        event_type="usage.recorded",
        payload=changed("usage.recorded", unit_id="sess-9"),
        pointer="/payload/unit_id",
    ),
    Case(
        name="agent unit mismatch",
        event_type="usage.recorded",
        payload=changed("usage.recorded", unit="agent"),
        pointer="/payload/unit_id",
    ),
    Case(
        name="agent unit without scope agent",
        event_type="usage.recorded",
        payload=changed("usage.recorded", unit="agent", unit_id="claude-code:agent-1", call_id=DELETE),
        pointer="/payload/unit_id",
        changes=(NO_AGENT,),
    ),
    Case(
        name="usage call without agent",
        event_type="usage.recorded",
        payload=changed("usage.recorded", unit="turn"),
        pointer="/scope/agent_id",
        changes=(NO_AGENT,),
    ),
    Case(
        name="empty usage",
        event_type="usage.recorded",
        payload=changed("usage.recorded", usage={}, pricing_ref=DELETE),
        pointer="/payload/usage",
    ),
    Case(
        name="cached above input",
        event_type="usage.recorded",
        payload=changed(
            "usage.recorded", usage={"input_tokens": 1, "cached_input_tokens": 2}, pricing_ref=DELETE
        ),
        pointer="/payload/usage",
    ),
    Case(
        name="usage extra field",
        event_type="usage.recorded",
        payload=changed("usage.recorded", usage={**USAGE, "cost": 1}, pricing_ref=DELETE),
        pointer="/payload/usage",
    ),
    Case(
        name="money as number",
        event_type="usage.recorded",
        payload=changed(
            "usage.recorded",
            usage={**USAGE, "reported_cost": {"amount": 1, "currency": "USD"}},
            pricing_ref=DELETE,
        ),
        pointer="/payload/usage/reported_cost/amount",
    ),
    Case(
        name="accounting enum",
        event_type="usage.recorded",
        payload=changed("usage.recorded", accounting="total"),
        pointer="/payload/accounting",
    ),
]


@pytest.mark.parametrize("case", INVALID, ids=[c.name for c in INVALID])
def test_invalid_payloads(case: Case) -> None:
    data = event(case.event_type, case.payload, *case.changes)
    for rejected in (reject(data), parse_event(raw(data))):
        assert isinstance(rejected, Rejected)
        assert (rejected.code, rejected.pointer) == (case.code, case.pointer)
        assert rejected.raw_sha256 is not None  # quarantine: the secret scan passed


def test_rules_that_hold_in_both_directions() -> None:
    blocked = changed(
        "task.status_changed", status="blocked", evidence_event_ids=DELETE, blocked_by_task_ids=["t-1"]
    )
    assert accept(event("task.status_changed", blocked))
    failed = changed("task.status_changed", status="failed")
    assert accept(event("task.status_changed", failed))
    for kind, field, value in (("search", "query", "needle"), ("file_write", "target_path", "src/a.py")):
        payload = changed("tool.call_started", kind=kind, command=DELETE, **{field: value})
        assert accept(event("tool.call_started", payload))
    assert accept(event("message.sent", changed("message.sent", channel_id=DELETE)))
    delta = changed("usage.recorded", accounting="delta", unit="model_call", unit_id=DELETE)
    assert accept(event("usage.recorded", delta))
    agent_unit = changed("usage.recorded", unit="agent", unit_id="claude-code:agent-1")
    assert accept(event("usage.recorded", agent_unit))
    assert accept(event("file.changed", changed("file.changed", call_id=DELETE), NO_AGENT))
    assert accept(event("agent.spawned", FULL["agent.spawned"], NO_AGENT))  # a self-report omits the spawner


def test_smallest_pointer_spans_envelope_and_payload() -> None:
    no_recipient = changed("message.sent", to_agent_ids=DELETE, channel_id=DELETE)
    assert (
        reject(event("message.sent", no_recipient, ("scope.task_id", "a b"))).pointer
        == "/payload/to_agent_ids"
    )
    assert reject(
        event("tool.call_started", FULL["tool.call_started"], NO_AGENT, ("source.seq", "1"))
    ).pointer == ("/scope/agent_id")
    assert reject(event("tool.call_started", changed("tool.call_started", attempt=0), NO_AGENT)).pointer == (
        "/payload/attempt"
    )


def test_currency_allowlist_is_pinned() -> None:
    assert len(ISO_4217_CURRENCIES) == 164
    assert {"USD", "EUR", "JPY", "GBP", "CHF", "ZWG", "SLE", "VED"} <= ISO_4217_CURRENCIES
    # C16: X-prefixed national and regional currencies are allowed; non-currency X codes are not.
    assert {c for c in ISO_4217_CURRENCIES if c.startswith("X")} == {"XAF", "XCD", "XCG", "XOF", "XPF"}
    non_currency = {"XAG", "XAU", "XBA", "XBB", "XBC", "XBD", "XDR", "XPD", "XPT", "XSU", "XTS", "XUA", "XXX"}
    assert not non_currency & ISO_4217_CURRENCIES
    assert not {"HRK", "ZWL", "ANG", "SLL", "CUC", "BGN", "BTC", "VEF"} & ISO_4217_CURRENCIES
    assert all(len(c) == 3 and c.isascii() and c.isupper() for c in ISO_4217_CURRENCIES)


# --- the usage token exemption, end to end (§10.3) ----------------------------------------------


def test_token_count_keys_are_exempt_only_as_integers_in_usage() -> None:
    usage = {**USAGE, "total_tokens": 1545}
    body = raw(event("usage.recorded", changed("usage.recorded", usage=usage, pricing_ref=DELETE)))
    assert isinstance(parse_event(body), Accepted)
    for bad_usage in ({"input_tokens": "5"}, {"input_tokens": SK}, {"output_tokens": [1]}):
        data = event("usage.recorded", changed("usage.recorded", usage=bad_usage, pricing_ref=DELETE))
        assert reject(data).code is RejectCode.SECRET_DETECTED
    money = {**USAGE, "reported_cost": {"amount": SK, "currency": "USD"}}
    leaked = event("usage.recorded", changed("usage.recorded", usage=money, pricing_ref=DELETE))
    assert reject(leaked).code is RejectCode.SECRET_DETECTED
    elsewhere = event("error.reported", {**FULL["error.reported"], "input_tokens": 5})
    assert reject(elsewhere).code is RejectCode.SECRET_DETECTED


# --- extension event types (§11) -------------------------------------------------------------------


@pytest.mark.parametrize("family", sorted(CORE_FAMILIES))
def test_core_family_is_never_a_vendor(family: str) -> None:
    rejected = reject(event(f"x-{family}.thing", {"a": 1}))
    assert (rejected.code, rejected.pointer) == (SCHEMA, "/event_type")
    assert accept(event(f"x-{family}co.thing", {"a": 1}))


def test_extension_types_and_unknown_types() -> None:
    assert accept(event("x-acme.deploy_step", {"step": "lint", "ok": True, "n": [1, 2]}))
    assert reject(event("x-acme.deploy_step", {"stdout": "x"})).code is SCHEMA
    assert reject(
        event("x-acme.deploy_step", {"a": "b" * 500, **{f"k{i}": "v" * 500 for i in range(16)}})
    ).code is (SCHEMA)
    assert reject(event("x-promptco.thing", {"a": 1})).pointer == "/event_type"
    for unknown in ("agent.paused", "session", "tool.call_started.v2", "Session.started"):
        assert reject(event(unknown, {"a": 1})).code is RejectCode.UNKNOWN_EVENT_TYPE


@pytest.mark.parametrize("currency", ["XAF", "XCD", "XCG", "XOF", "XPF"])
def test_regional_x_currencies_are_accepted(currency: str) -> None:
    usage = {**USAGE, "reported_cost": {"amount": "12.5", "currency": currency}}
    assert accept(event("usage.recorded", changed("usage.recorded", usage=usage, pricing_ref=DELETE)))
