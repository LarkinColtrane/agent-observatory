"""Stable rejection codes, dispositions and warnings (ADR-0008 §§6, 12)."""

from __future__ import annotations

from enum import StrEnum


class RejectCode(StrEnum):
    """Why an event was rejected; values are stable (§12)."""

    TOO_LARGE = "too_large"
    INVALID_ENCODING = "invalid_encoding"
    TOO_DEEP = "too_deep"
    INVALID_JSON = "invalid_json"
    DUPLICATE_KEY = "duplicate_key"
    FLOAT_NOT_ALLOWED = "float_not_allowed"
    INTEGER_OUT_OF_RANGE = "integer_out_of_range"
    NOT_AN_OBJECT = "not_an_object"
    SECRET_DETECTED = "secret_detected"  # noqa: S105 (a code name, not a secret)  # nosec B105
    FORBIDDEN_CHARACTER = "forbidden_character"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNKNOWN_EVENT_TYPE = "unknown_event_type"
    SCHEMA_VIOLATION = "schema_violation"
    INVALID_REFERENCE = "invalid_reference"
    INTERNAL_ERROR = "internal_error"


class Disposition(StrEnum):
    """What ingestion keeps of a rejected event: a drop record, or a quarantine record (§12)."""

    DROP = "drop"
    QUARANTINE = "quarantine"


class WarningCode(StrEnum):
    """Clock skew and delay, reported but never corrected (§6)."""

    OCCURRED_AFTER_OBSERVED = "occurred_after_observed"
    LATE_OBSERVATION = "late_observation"


class EventRejection(ValueError):
    """A failed protocol check. Carries only a code, a schema pointer and a disposition, never a value."""

    def __init__(self, code: RejectCode, pointer: str, disposition: Disposition) -> None:
        super().__init__(f"{code.value} at {pointer!r} ({disposition.value})")
        self.code = code
        self.pointer = pointer
        self.disposition = disposition
