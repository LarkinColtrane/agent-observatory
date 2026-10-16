"""Universal agent event protocol v1 (ADR-0008 §17).

Depends only on ``observatory.core``, Pydantic and the standard library.
"""

from observatory.events.codec import canonical_json, content_fingerprint, fingerprint
from observatory.events.codes import Disposition, EventRejection, RejectCode, WarningCode
from observatory.events.envelope import (
    SPEC_VERSION,
    SUPPORTED_VERSIONS,
    Adapter,
    Causality,
    Event,
    EventTime,
    RecordedEvent,
    Scope,
    Source,
)
from observatory.events.ids import derive_event_id
from observatory.events.ordering import DuplicateKind, canonical_order, classify_duplicate, stream_key
from observatory.events.payloads import EventPayload, ExtensionPayload
from observatory.events.taxonomy import (
    AgentSpawned,
    AgentTerminated,
    ErrorReported,
    FileChanged,
    MessageSent,
    ReviewVerdictRecorded,
    SessionEnded,
    SessionStarted,
    TaskAssigned,
    TaskCreated,
    TaskDependencyAdded,
    TaskStatusChanged,
    TestRunCompleted,
    ToolCallFinished,
    ToolCallStarted,
    UsageRecorded,
)
from observatory.events.text import SECRET_RULES, SECRET_RULES_VERSION, RuleSet, sanitize_text
from observatory.events.validation import (
    Accepted,
    Rejected,
    load_recorded,
    parse_event,
    validate_event,
)

__all__ = [
    "SECRET_RULES",
    "SECRET_RULES_VERSION",
    "SPEC_VERSION",
    "SUPPORTED_VERSIONS",
    "Accepted",
    "Adapter",
    "AgentSpawned",
    "AgentTerminated",
    "Causality",
    "Disposition",
    "DuplicateKind",
    "ErrorReported",
    "Event",
    "EventPayload",
    "EventRejection",
    "EventTime",
    "ExtensionPayload",
    "FileChanged",
    "MessageSent",
    "RecordedEvent",
    "RejectCode",
    "Rejected",
    "ReviewVerdictRecorded",
    "RuleSet",
    "Scope",
    "SessionEnded",
    "SessionStarted",
    "Source",
    "TaskAssigned",
    "TaskCreated",
    "TaskDependencyAdded",
    "TaskStatusChanged",
    "TestRunCompleted",
    "ToolCallFinished",
    "ToolCallStarted",
    "UsageRecorded",
    "WarningCode",
    "canonical_json",
    "canonical_order",
    "classify_duplicate",
    "content_fingerprint",
    "derive_event_id",
    "fingerprint",
    "load_recorded",
    "parse_event",
    "sanitize_text",
    "stream_key",
    "validate_event",
]
