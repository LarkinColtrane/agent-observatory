"""The 16 core payload models and the registry the envelope dispatches on (ADR-0008 §§8, 9).

Every payload is closed, strict and frozen; an absent optional field means
"not reported". Cross-field rules raise one error at the smallest violated
field (check 13). Required-scope rules are checked against the event's scope
(check 13), and self references are ``invalid_reference`` (check 14).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Final, Literal, Self

from pydantic import model_validator

from observatory.core.telemetry import UsageMetrics
from observatory.events.currency import ISO_4217_CURRENCIES
from observatory.events.ids import (
    Attempt,
    Code,
    Count,
    DurationMs,
    Id,
    IdSet64,
    Int32,
    ModelName,
    ProviderRef,
    RelPath,
    Text64,
    Text128,
    Text200,
    Text512,
    Text1024,
    ToolName,
    UuidSet32,
)
from observatory.events.payloads import EventPayload, check_rules
from observatory.events.tree import Pointer

if TYPE_CHECKING:
    from observatory.events.envelope import Event

_SCOPE_AGENT: Final[Pointer] = ("scope", "agent_id")


def _members(field: str, values: tuple[str, ...] | None, item: str) -> list[Pointer]:
    """Pointers to each occurrence of ``item`` in an id set (a self reference)."""
    return [("payload", field, i) for i, value in enumerate(values or ()) if value == item]


def _equal(field: str, value: object, other: object) -> list[Pointer]:
    return [("payload", field)] if value is not None and value == other else []


# --- session -----------------------------------------------------------------------------


class _SessionPayload(EventPayload):
    session_id: Id

    def scope_errors(self, scope: Mapping[str, object]) -> tuple[Pointer, ...]:
        """``session.*`` needs ``scope.session_id`` equal to the payload's."""
        return () if scope.get("session_id") == self.session_id else (("scope", "session_id"),)


class SessionStarted(_SessionPayload):
    """``session.started``."""

    initiator: Literal["human", "agent", "schedule", "system"] | None = None


class SessionEnded(_SessionPayload):
    """``session.ended``."""

    outcome: Literal["completed", "failed", "cancelled", "unknown"]


# --- agent ----------------------------------------------------------------------------------


class AgentSpawned(EventPayload):
    """``agent.spawned``: the scope agent is the spawner, ``parent_agent_id`` the hierarchy owner."""

    agent_id: Id
    parent_agent_id: Id | None = None
    role: Text64 | None = None
    display_name: Text128 | None = None
    model: ModelName | None = None

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        found = _equal("parent_agent_id", self.parent_agent_id, self.agent_id)
        found += _equal("agent_id", self.agent_id, event.scope.agent_id)
        return tuple(found)


class AgentTerminated(EventPayload):
    """``agent.terminated``."""

    agent_id: Id
    reason: Literal["completed", "failed", "cancelled", "killed", "timeout", "unknown"]


# --- task -------------------------------------------------------------------------------------


class TaskCreated(EventPayload):
    """``task.created``: subtask = parent, DAG edges = ``depends_on``."""

    task_id: Id
    title: Text200 | None = None
    parent_task_id: Id | None = None
    depends_on: IdSet64 | None = None

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        del event
        found = _equal("parent_task_id", self.parent_task_id, self.task_id)
        return tuple(found + _members("depends_on", self.depends_on, self.task_id))


class TaskAssigned(EventPayload):
    """``task.assigned``: a handoff has a previous assignee; the assigner is the scope agent."""

    task_id: Id
    assignee_agent_id: Id
    previous_assignee_agent_id: Id | None = None

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        del event
        return tuple(
            _equal("previous_assignee_agent_id", self.previous_assignee_agent_id, self.assignee_agent_id)
        )


class TaskStatusChanged(EventPayload):
    """``task.status_changed``: blockers only when blocked, evidence only when completed or failed."""

    task_id: Id
    status: Literal["pending", "in_progress", "blocked", "completed", "failed", "cancelled"]
    blocked_by_task_ids: IdSet64 | None = None
    reason_code: Code | None = None
    evidence_event_ids: UuidSet32 | None = None

    @model_validator(mode="after")
    def _status_gates(self) -> Self:
        violations: list[Pointer] = []
        if self.blocked_by_task_ids is not None and self.status != "blocked":
            violations.append(("blocked_by_task_ids",))
        if self.evidence_event_ids is not None and self.status not in ("completed", "failed"):
            violations.append(("evidence_event_ids",))
        check_rules(violations)
        return self

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        del event
        return tuple(_members("blocked_by_task_ids", self.blocked_by_task_ids, self.task_id))


class TaskDependencyAdded(EventPayload):
    """``task.dependency_added``: a DAG edge added after creation."""

    task_id: Id
    depends_on_task_id: Id

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        del event
        return tuple(_equal("depends_on_task_id", self.depends_on_task_id, self.task_id))


# --- tool ---------------------------------------------------------------------------------------


class _ToolPayload(EventPayload):
    call_id: Id

    def scope_errors(self, scope: Mapping[str, object]) -> tuple[Pointer, ...]:
        """``tool.*`` needs ``scope.agent_id``."""
        return () if "agent_id" in scope else (_SCOPE_AGENT,)


#: Fields allowed only on some tool kinds (§8).
_KIND_FIELDS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "command": frozenset({"command"}),
        "query": frozenset({"search"}),
        "target_path": frozenset({"file_read", "file_write"}),
    }
)


class ToolCallStarted(_ToolPayload):
    """``tool.call_started``: a retry is a new call with ``attempt``."""

    tool_name: ToolName
    kind: Literal["command", "search", "file_read", "file_write", "web", "agent", "other"]
    attempt: Attempt | None = None
    retry_of_call_id: Id | None = None
    command: Text1024 | None = None
    query: Text512 | None = None
    target_path: RelPath | None = None

    @model_validator(mode="after")
    def _kind_gates(self) -> Self:
        violations: list[Pointer] = [
            (name,)
            for name, kinds in _KIND_FIELDS.items()
            if getattr(self, name) is not None and self.kind not in kinds
        ]
        if self.retry_of_call_id is not None and self.attempt is None:
            violations.append(("retry_of_call_id",))
        check_rules(violations)
        return self

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        del event
        return tuple(_equal("retry_of_call_id", self.retry_of_call_id, self.call_id))


class ToolCallFinished(_ToolPayload):
    """``tool.call_finished``."""

    outcome: Literal["succeeded", "failed", "cancelled", "timed_out"]
    duration_ms: DurationMs | None = None
    exit_code: Int32 | None = None
    error_code: Code | None = None


# --- file, test, review --------------------------------------------------------------------------


def _agent_for_call(call_id: str | None, scope: Mapping[str, object]) -> tuple[Pointer, ...]:
    """A ``call_id`` in ``file.changed`` or ``usage.recorded`` needs ``scope.agent_id``."""
    return (_SCOPE_AGENT,) if call_id is not None and "agent_id" not in scope else ()


class FileChanged(EventPayload):
    """``file.changed``: the effect, whatever tool or person caused it."""

    path: RelPath
    change: Literal["created", "modified", "deleted", "renamed"]
    previous_path: RelPath | None = None
    call_id: Id | None = None
    lines_added: Count | None = None
    lines_removed: Count | None = None

    @model_validator(mode="after")
    def _rename_gate(self) -> Self:
        check_rules(
            [("previous_path",)] if (self.previous_path is not None) != (self.change == "renamed") else []
        )
        return self

    def scope_errors(self, scope: Mapping[str, object]) -> tuple[Pointer, ...]:
        return _agent_for_call(self.call_id, scope)

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        del event
        return tuple(_equal("previous_path", self.previous_path, self.path))


class TestRunCompleted(EventPayload):
    """``test.run_completed``: results only, never test output."""

    __test__: ClassVar[bool] = False  # not a pytest test class

    run_id: Id
    outcome: Literal["passed", "failed", "errored", "cancelled"]
    call_id: Id | None = None
    framework: Code | None = None
    passed: Count | None = None
    failed: Count | None = None
    skipped: Count | None = None
    errored: Count | None = None
    duration_ms: DurationMs | None = None


class ReviewVerdictRecorded(EventPayload):
    """``review.verdict_recorded``: the reviewer is the scope agent."""

    review_id: Id
    verdict: Literal["approve", "approve_with_notes", "request_changes", "reject", "comment"]
    subject_task_id: Id | None = None
    findings: Count | None = None
    blocking_findings: Count | None = None


# --- message, error ---------------------------------------------------------------------------------


class MessageSent(EventPayload):
    """``message.sent``: metadata only, never content; the sender is the scope agent."""

    message_id: Id
    intent: Literal["request", "response", "notification", "handoff", "broadcast"]
    to_agent_ids: IdSet64 | None = None
    channel_id: Id | None = None
    in_reply_to_message_id: Id | None = None
    size_bytes: Count | None = None

    @model_validator(mode="after")
    def _has_recipient(self) -> Self:
        check_rules([("to_agent_ids",)] if self.to_agent_ids is None and self.channel_id is None else [])
        return self

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        del event
        return tuple(_equal("in_reply_to_message_id", self.in_reply_to_message_id, self.message_id))


class ErrorReported(EventPayload):
    """``error.reported``: an error not expressed by a ``tool.call_finished`` outcome."""

    error_code: Code
    severity: Literal["warning", "error", "fatal"]
    message: Text512 | None = None
    call_id: Id | None = None


# --- usage (§9) ----------------------------------------------------------------------------------------


class UsageRecorded(EventPayload):
    """``usage.recorded``: ADR-0007 usage as a delta or a running total of one unit instance."""

    usage: UsageMetrics
    accounting: Literal["delta", "cumulative"]
    unit: Literal["model_call", "turn", "agent", "session"]
    unit_id: Id | None = None
    model: ModelName | None = None
    call_id: Id | None = None
    pricing_ref: ProviderRef | None = None

    @model_validator(mode="after")
    def _accounting_rules(self) -> Self:
        violations: list[Pointer] = []
        if self.accounting == "cumulative" and self.unit_id is None:
            violations.append(("unit_id",))
        if (self.pricing_ref is None) != (self.usage.estimated_cost is None):
            violations.append(("pricing_ref",))
        for name in ("reported_cost", "estimated_cost"):
            cost = getattr(self.usage, name)
            if cost is not None and cost.currency not in ISO_4217_CURRENCIES:
                violations.append(("usage", name, "currency"))
        check_rules(violations)
        return self

    def scope_errors(self, scope: Mapping[str, object]) -> tuple[Pointer, ...]:
        found = list(_agent_for_call(self.call_id, scope))
        owner = {"session": "session_id", "agent": "agent_id"}.get(self.unit)
        if owner is not None and self.unit_id is not None and scope.get(owner) != self.unit_id:
            found.append(("payload", "unit_id"))
        return tuple(found)


#: Payload models per declared ``spec_version`` and ``event_type``; the envelope dispatches on it.
PAYLOADS: Final[Mapping[str, Mapping[str, type[EventPayload]]]] = MappingProxyType(
    {
        "1.0": MappingProxyType(
            {
                "session.started": SessionStarted,
                "session.ended": SessionEnded,
                "agent.spawned": AgentSpawned,
                "agent.terminated": AgentTerminated,
                "task.created": TaskCreated,
                "task.assigned": TaskAssigned,
                "task.status_changed": TaskStatusChanged,
                "task.dependency_added": TaskDependencyAdded,
                "tool.call_started": ToolCallStarted,
                "tool.call_finished": ToolCallFinished,
                "file.changed": FileChanged,
                "test.run_completed": TestRunCompleted,
                "review.verdict_recorded": ReviewVerdictRecorded,
                "message.sent": MessageSent,
                "error.reported": ErrorReported,
                "usage.recorded": UsageRecorded,
            }
        )
    }
)
#: The core families; no extension vendor may be named after one.
CORE_FAMILIES: Final = frozenset(name.split(".")[0] for types in PAYLOADS.values() for name in types)
