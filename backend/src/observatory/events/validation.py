"""Validation entry points, rejection records and recorded events (ADR-0008 §§6, 12, 14).

``parse_event`` and ``validate_event`` accept new events and always use the
current secret rules. ``load_recorded`` only loads a stored event under the
rules version recorded with it; it never produces an ``Accepted``.
"""

from __future__ import annotations

import typing
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

from pydantic import ValidationError

from observatory.events.codec import (
    UTF8_BOM,
    content_fingerprint,
    exceeds_depth,
    fingerprint,
    parse_json,
    sha256_hex,
)
from observatory.events.codes import Disposition, EventRejection, RejectCode, WarningCode
from observatory.events.envelope import Adapter, Event, RecordedEvent
from observatory.events.ids import (
    ID_PATTERN,
    MAX_SAFE_INT,
    SLUG_PATTERN,
    SPEC_VERSION_PATTERN,
    VERSION_PATTERN,
    WORKSPACE_ID_PATTERN,
    matches,
    parse_timestamp,
    uuid_version,
)
from observatory.events.payloads import EXTENSION_TYPE
from observatory.events.taxonomy import PAYLOADS
from observatory.events.tree import MAX_BYTES, MAX_DEPTH, canonical_text, inspect_tree

_SKEW: Final = timedelta(minutes=5)
_LATE: Final = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class Accepted:
    """An accepted event with both fingerprints and its (unstored) warnings."""

    event: Event
    fingerprint: str
    content_fingerprint: str
    warnings: tuple[WarningCode, ...]


@dataclass(frozen=True, slots=True)
class Rejected:
    """A drop or quarantine record (§12, C2). Never holds raw bytes or any unchecked value."""

    code: RejectCode
    pointer: str
    disposition: Disposition
    raw_length: int
    raw_sha256: str | None = None
    workspace_id: str | None = None
    event_id: str | None = None
    event_type: str | None = None
    spec_version: str | None = None
    provider: str | None = None
    adapter: Adapter | None = None
    stream_id: str | None = None
    seq: int | None = None


def _drop(code: RejectCode, raw_length: int, pointer: str = "") -> Rejected:
    return Rejected(code=code, pointer=pointer, disposition=Disposition.DROP, raw_length=raw_length)


def _get(tree: Mapping[str, Any], *path: str) -> object:
    node: object = tree
    for key in path:
        if type(node) is not dict:
            return None
        node = typing.cast(dict[str, object], node).get(key)
    return node


def _quarantine(rejection: EventRejection, tree: Mapping[str, Any], raw: bytes) -> Rejected:
    """A quarantine record: the digest plus those identity fields that pass their own rule (C2)."""

    def kept(value: object, pattern: str) -> str | None:
        return typing.cast(str, value) if matches(pattern, value) else None

    event_type = tree.get("event_type")
    known_type = type(event_type) is str and (
        any(event_type in types for types in PAYLOADS.values())
        or EXTENSION_TYPE.fullmatch(event_type) is not None
    )
    name, version = _get(tree, "source", "adapter", "name"), _get(tree, "source", "adapter", "version")
    seq = _get(tree, "source", "seq")
    return Rejected(
        code=rejection.code,
        pointer=rejection.pointer,
        disposition=Disposition.QUARANTINE,
        raw_length=len(raw),
        raw_sha256=sha256_hex(raw),
        workspace_id=kept(_get(tree, "scope", "workspace_id"), WORKSPACE_ID_PATTERN),
        event_id=typing.cast(str, tree.get("event_id")) if uuid_version(tree.get("event_id")) else None,
        event_type=typing.cast(str, event_type) if known_type else None,
        spec_version=kept(tree.get("spec_version"), SPEC_VERSION_PATTERN),
        provider=kept(_get(tree, "source", "provider"), SLUG_PATTERN),
        adapter=(
            Adapter(name=typing.cast(str, name), version=typing.cast(str, version))
            if matches(SLUG_PATTERN, name) and matches(VERSION_PATTERN, version)
            else None
        ),
        stream_id=kept(_get(tree, "source", "stream_id"), ID_PATTERN),
        seq=seq if type(seq) is int and 0 <= seq <= MAX_SAFE_INT else None,
    )


def warnings_for(event: Event) -> tuple[WarningCode, ...]:
    """Clock skew and delay (§6); never stored in the event."""
    if event.time.occurred_at is None:
        return ()
    occurred = parse_timestamp(event.time.occurred_at)
    observed = parse_timestamp(event.time.observed_at)
    found: list[WarningCode] = []
    if occurred - observed > _SKEW:
        found.append(WarningCode.OCCURRED_AFTER_OBSERVED)
    if observed - occurred > _LATE:
        found.append(WarningCode.LATE_OBSERVATION)
    return tuple(found)


def _finish(tree: dict[str, Any], raw: bytes) -> Accepted | Rejected:
    """Checks 9-15 under the current rules: construct the event, or record why not."""
    try:
        event = Event.model_validate(tree)  # always the current rules: only RecordedEvent names another
    except ValidationError as exc:
        errors = exc.errors()
        cause = errors[0].get("ctx", {}).get("error") if len(errors) == 1 else None
        if not isinstance(cause, EventRejection):
            return _drop(RejectCode.INTERNAL_ERROR, len(raw))
        if cause.disposition is Disposition.DROP:
            return _drop(cause.code, len(raw), cause.pointer)
        return _quarantine(cause, tree, raw)
    return Accepted(
        event=event,
        fingerprint=fingerprint(event),
        content_fingerprint=content_fingerprint(event),
        warnings=warnings_for(event),
    )


def parse_event(raw: bytes) -> Accepted | Rejected:  # noqa: PLR0911 (one return per ordered check)
    """Validate raw bytes in the fixed order of §12, always under the current secret rules."""
    length = len(raw) if isinstance(raw, bytes) else 0
    try:
        if not isinstance(raw, bytes):
            return _drop(RejectCode.INTERNAL_ERROR, 0)
        if length > MAX_BYTES:
            return _drop(RejectCode.TOO_LARGE, length)
        if raw.startswith(UTF8_BOM):
            return _drop(RejectCode.INVALID_ENCODING, length)
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError:
            return _drop(RejectCode.INVALID_ENCODING, length)
        if exceeds_depth(text):
            return _drop(RejectCode.TOO_DEEP, length)
        tree = parse_json(text)
        if isinstance(tree, RejectCode):
            return _drop(tree, length)
        if type(tree) is not dict:
            return _drop(RejectCode.NOT_AN_OBJECT, length)
        return _finish(typing.cast(dict[str, Any], tree), raw)
    except Exception:  # never re-raised: an exception could carry values
        return _drop(RejectCode.INTERNAL_ERROR, length)


def validate_event(data: object) -> Accepted | Rejected:  # noqa: PLR0911 (one return per ordered check)
    """Validate a plain tree (exact built-in types), always under the current secret rules.

    "Raw" is the plain serialisation of the input tree: sorted keys, compact, UTF-8, timestamps as
    given (C3); its length is 0 when the tree cannot be serialised.
    """
    try:
        report = inspect_tree(data)
        if not report.plain:
            return _drop(RejectCode.INVALID_JSON, 0)
        if report.depth > MAX_DEPTH:
            return _drop(RejectCode.TOO_DEEP, report.size)
        if report.size > MAX_BYTES:
            return _drop(RejectCode.TOO_LARGE, report.size)  # C8: before the scan, so drop
        if not report.safe_integers:
            return _drop(RejectCode.INTEGER_OUT_OF_RANGE, report.size)
        if type(data) is not dict:
            return _drop(RejectCode.NOT_AN_OBJECT, report.size)
        tree = typing.cast(dict[str, Any], data)
        raw = canonical_text(tree).encode("utf-8", "surrogatepass")
        if len(raw) != report.size:  # pragma: no cover - the two serialisations always agree
            return _drop(RejectCode.INTERNAL_ERROR, report.size)
        return _finish(tree, raw)
    except Exception:  # never re-raised: an exception could carry values
        return _drop(RejectCode.INTERNAL_ERROR, 0)


# --- recorded events (§14) -------------------------------------------------------------


def load_recorded(record: Mapping[str, object]) -> RecordedEvent:
    """Load a stored event under ``record["secret_rules_version"]``; never an acceptance path."""
    if not isinstance(record, Mapping):
        raise TypeError("a recorded event is a mapping")
    try:
        return RecordedEvent.model_validate(dict(record))
    except ValidationError:
        raise ValueError("recorded event failed validation") from None
