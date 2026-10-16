"""The event envelope and checks 9-15 (ADR-0008 §§2, 4, 5, 10, 12).

Constructing an ``Event`` in any way runs checks 9-15 in order; the first
failure raises ``EventRejection`` (wrapped by Pydantic in a ``ValidationError``).
Validation is strict whatever ``strict=`` a caller passes, and the JSON and
string entry points raise: JSON is accepted only by ``parse_event`` (C22).

Each instance privately carries a stamp of the rules version it was validated
under, bound to its canonical bytes by an HMAC under a per-process key (C4).
An older rules version can be named only while ``RecordedEvent`` (so
``load_recorded``) validates a stored row (C23). The stamp is not part of the
event, and an ``Event`` object is valid only in the process that validated it:
events cross process, cache and queue boundaries only as canonical bytes,
re-read with ``parse_event`` or ``load_recorded`` (C24).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import typing
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cache
from types import MappingProxyType
from typing import Annotated, Any, Final, NoReturn, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    ModelWrapValidatorHandler,
    PrivateAttr,
    SerializeAsAny,
    StringConstraints,
    ValidationError,
    model_validator,
)
from pydantic_core import ErrorDetails

from observatory.core.telemetry import Money, UsageMetrics
from observatory.events.codes import Disposition, EventRejection, RejectCode
from observatory.events.ids import (
    ID_PATTERN,
    MAX_SAFE_INT,
    Code,
    EventUuid,
    Id,
    ProviderRef,
    Seq,
    Slug,
    Timestamp,
    Version,
    WorkspaceId,
    canonical_timestamp,
    derive_event_id,
    matches,
    uuid_version,
)
from observatory.events.payloads import (
    CROSS_FIELD,
    EXTENSION_TYPE,
    STRICT,
    USAGE_TOKEN_KEYS,
    EventPayload,
    ExtensionPayload,
    check_extensions,
    denied_name,
)
from observatory.events.taxonomy import CORE_FAMILIES, PAYLOADS
from observatory.events.text import (
    FORBIDDEN,
    FORBIDDEN_IN_KEY,
    RuleSet,
    current_rules_version,
    is_rel_path,
    rules_for,
)
from observatory.events.tree import (
    MAX_BYTES,
    MAX_DEPTH,
    Pointer,
    Segment,
    Shape,
    canonical_text,
    format_pointer,
    known_prefix,
    model_shape,
    pointer_order,
    walk,
)

SPEC_VERSION: Final = "1.0"
SUPPORTED_VERSIONS: Final = frozenset({SPEC_VERSION})

_DROP: Final = Disposition.DROP
_QUARANTINE: Final = Disposition.QUARANTINE


class Scope(BaseModel):
    """Who acted and where (§2)."""

    model_config = STRICT

    workspace_id: WorkspaceId
    session_id: Id | None = None
    agent_id: Id | None = None
    task_id: Id | None = None


class EventTime(BaseModel):
    """Source and emitter times (§6); timestamps are kept in canonical form."""

    model_config = STRICT

    occurred_at: Timestamp | None = None
    observed_at: Timestamp


class Adapter(BaseModel):
    """The emitting adapter or SDK."""

    model_config = STRICT

    name: Slug
    version: Version


class Source(BaseModel):
    """Provenance and stream position (§§2, 7)."""

    model_config = STRICT

    provider: Slug
    adapter: Adapter
    stream_id: Id | None = None
    seq: Seq | None = None
    provider_event_id: ProviderRef | None = None

    @model_validator(mode="after")
    def _stream_needs_seq(self) -> Self:
        if (self.stream_id is None) != (self.seq is None):
            raise ValueError("stream_id and seq come together")
        return self


class Causality(BaseModel):
    """Correlation and direct cause; present only when it holds something."""

    model_config = STRICT

    correlation_id: Id | None = None
    causation_id: EventUuid | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.correlation_id is None and self.causation_id is None:
            raise ValueError("causality must not be empty")
        return self


Extensions = Annotated[dict[str, Any], AfterValidator(check_extensions)]


@dataclass(frozen=True, slots=True)
class _Stamp:
    version: int
    recorded: bool
    mac: bytes


_STAMP_KEY: Final = secrets.token_bytes(32)
#: Proves that the recorded-rules override was set by this module's ``RecordedEvent`` validator (C23).
_LOAD_TOKEN: Final = object()
#: ``(token, version)`` while a stored row is validated; anything else means the current rules version.
_RECORDED_RULES: ContextVar[object] = ContextVar("observatory_recorded_rules", default=None)


def _mac(version: int, recorded: bool, canonical: bytes) -> bytes:
    header = f"{version}:{int(recorded)}:".encode("ascii")
    return hmac.new(_STAMP_KEY, header + canonical, hashlib.sha256).digest()


@contextmanager
def _recorded_rules(version: int | None) -> Iterator[None]:
    """Validate under a recorded rules version (``None``: current). Private to this module (C23)."""
    if version is not None:
        rules_for(version)  # unknown -> ValueError
    token = _RECORDED_RULES.set((_LOAD_TOKEN, version) if version is not None else None)
    try:
        yield
    finally:
        _RECORDED_RULES.reset(token)


def _recorded_version() -> int | None:
    """The recorded rules version, honoured only when this module set it (C23)."""
    override = _RECORDED_RULES.get()
    if type(override) is tuple and len(override) == 2 and override[0] is _LOAD_TOKEN:
        version: int = override[1]
        return version
    return None


class Event(BaseModel):
    """One emitted event (§2). Every instance has passed checks 9-15."""

    model_config = STRICT

    spec_version: str
    event_id: EventUuid
    event_type: str
    scope: Scope
    time: EventTime
    source: Source
    causality: Causality | None = None
    payload: SerializeAsAny[EventPayload]
    extensions: Extensions | None = None

    _stamp: _Stamp | None = PrivateAttr(default=None)

    @model_validator(mode="wrap")
    @classmethod
    def _protocol_checks(cls, data: Any, handler: ModelWrapValidatorHandler[Event]) -> Event:
        recorded = _recorded_version()
        rules = rules_for(current_rules_version() if recorded is None else recorded)
        tree = to_tree(data)
        if type(tree) is not dict:
            raise EventRejection(RejectCode.NOT_AN_OBJECT, "", _DROP)
        payload_model = _payload_model(tree)
        shape = event_shape(payload_model)
        _check_secrets(tree, shape, rules)
        _check_characters(tree, shape)
        version = tree.get("spec_version")
        if type(version) is not str or version not in SUPPORTED_VERSIONS:
            raise EventRejection(RejectCode.UNSUPPORTED_VERSION, "/spec_version", _QUARANTINE)
        if payload_model is None:
            raise EventRejection(RejectCode.UNKNOWN_EVENT_TYPE, "/event_type", _QUARANTINE)
        event = _check_schema(tree, shape, payload_model, handler)
        _check_exact(tree, event, shape)
        _check_references(event)
        canonical = canonical_text(to_tree(event)).encode("utf-8")
        if len(canonical) > MAX_BYTES:
            raise EventRejection(RejectCode.TOO_LARGE, "", _QUARANTINE)
        event._stamp = _Stamp(
            rules.version, recorded is not None, _mac(rules.version, recorded is not None, canonical)
        )
        return event

    @classmethod
    def model_validate(cls, obj: Any, *, strict: bool | None = None, **kwargs: Any) -> Self:
        """Strict validation whatever ``strict`` says (C22)."""
        del strict
        return super().model_validate(obj, strict=True, **kwargs)

    @classmethod
    def model_validate_json(cls, *args: Any, **kwargs: Any) -> NoReturn:
        """Refused: JSON bypasses the bounded parser; use ``parse_event`` (C22)."""
        del args, kwargs
        raise TypeError(
            "Event.model_validate_json is not an acceptance path; use observatory.events.parse_event"
        )

    @classmethod
    def model_validate_strings(cls, *args: Any, **kwargs: Any) -> NoReturn:
        """Refused: string coercion is never accepted; use ``parse_event`` (C22)."""
        del args, kwargs
        raise TypeError(
            "Event.model_validate_strings is not an acceptance path; use observatory.events.parse_event"
        )

    def __eq__(self, other: object) -> bool:
        """Equal fields; the private rules stamp is not part of the event (C4)."""
        if type(other) is not Event:
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __hash__(self) -> int:
        return hash(self.event_id)


# --- trees ----------------------------------------------------------------------------


@cache
def _model_types() -> frozenset[type[BaseModel]]:
    models: set[type[BaseModel]] = {model for types in PAYLOADS.values() for model in types.values()}
    models.update(
        (Event, Scope, EventTime, Adapter, Source, Causality, ExtensionPayload, UsageMetrics, Money)
    )
    return frozenset(models)


def to_tree(value: object) -> object:
    """A plain JSON tree of ``value``: exact protocol models become objects of their present fields."""
    return _to_tree(value, 1, set())


def _to_tree(value: object, depth: int, seen: set[int]) -> object:
    kind = type(value)
    if kind in (str, int, bool) or value is None:
        return value
    if depth > MAX_DEPTH:
        raise EventRejection(RejectCode.TOO_DEEP, "", _DROP)
    if id(value) in seen:
        raise EventRejection(RejectCode.INVALID_JSON, "", _DROP)
    seen.add(id(value))
    if kind is dict:
        items = typing.cast(dict[object, object], value).items()
        if any(type(k) is not str for k, _ in items):
            raise EventRejection(RejectCode.INVALID_JSON, "", _DROP)
        return {k: _to_tree(v, depth + 1, seen) for k, v in items}
    if kind is list or kind is tuple:
        return [_to_tree(v, depth + 1, seen) for v in typing.cast(list[object], value)]
    if kind in _model_types():
        model = typing.cast(BaseModel, value)
        fields = {k: v for k, v in model.__dict__.items() if v is not None}
        fields.update(model.__pydantic_extra__ or {})
        return {k: _to_tree(v, depth + 1, seen) for k, v in fields.items()}
    raise EventRejection(RejectCode.INVALID_JSON, "", _DROP)


def event_tree(event: Event) -> dict[str, Any]:
    """The plain tree of an event (canonical timestamps, only the fields present)."""
    return typing.cast(dict[str, Any], to_tree(event))


# --- checks 9-14 ------------------------------------------------------------------------


def _payload_model(tree: dict[str, Any]) -> type[EventPayload] | None:
    version, event_type = tree.get("spec_version"), tree.get("event_type")
    if type(version) is not str or type(event_type) is not str or version not in SUPPORTED_VERSIONS:
        return None
    known = PAYLOADS[version].get(event_type)
    if known is not None:
        return known
    return ExtensionPayload if EXTENSION_TYPE.fullmatch(event_type) else None


@cache
def event_shape(payload_model: type[EventPayload] | None) -> Shape:
    """The envelope shape with the payload shape of ``payload_model`` (free if unknown)."""
    base = model_shape(Event)
    payload = model_shape(payload_model) if payload_model is not None else Shape("free")
    return Shape("model", MappingProxyType({**base.fields, "payload": payload}))


def _reject_at(code: RejectCode, pointers: list[Pointer], disposition: Disposition) -> None:
    if pointers:
        raise EventRejection(code, format_pointer(min(pointers, key=pointer_order)), disposition)


def _skips_text_tier(shape: Shape, value: str) -> bool:
    """C1: only a valid Id or RelPath at its own position skips the text tier."""
    return (shape.kind == "id" and matches(ID_PATTERN, value)) or (
        shape.kind == "path" and is_rel_path(value)
    )


def _check_secrets(tree: dict[str, Any], shape: Shape, rules: RuleSet) -> None:
    """Check 9: credential tier on every key and string, text tier per C1, secret-named keys."""
    usage_event = tree.get("event_type") == "usage.recorded"
    hits: list[Pointer] = []
    for entry in walk(tree, shape):
        if isinstance(entry.key, str):
            exempt = (
                usage_event
                and entry.container_path == ("payload", "usage")
                and entry.key in USAGE_TOKEN_KEYS
                and type(entry.value) is int
            )
            if rules.key_hit(entry.key, name_test=not exempt):
                hits.append(entry.container_pointer)
        value = entry.value
        if type(value) is str and rules.string_hit(value, text_tier=not _skips_text_tier(entry.shape, value)):
            hits.append(entry.container_pointer)
    _reject_at(RejectCode.SECRET_DETECTED, hits, _DROP)


def _check_characters(tree: dict[str, Any], shape: Shape) -> None:
    """Check 10: forbidden characters in any key (TAB and LF included) or string."""
    found: list[Pointer] = []
    for entry in walk(tree, shape):
        if isinstance(entry.key, str) and FORBIDDEN_IN_KEY.search(entry.key):
            found.append(entry.container_pointer)
        if type(entry.value) is str and FORBIDDEN.search(entry.value):
            found.append(entry.pointer)
    _reject_at(RejectCode.FORBIDDEN_CHARACTER, found, _QUARANTINE)


def _error_path(prefix: Pointer, error: ErrorDetails) -> Pointer:
    """The schema path of a Pydantic error; a cross-field error names its field in ``ctx``."""
    path = (*prefix, *error["loc"])
    if error["type"] == CROSS_FIELD:
        path = (*path, *error.get("ctx", {}).get("at", ()))
    return path


def _bad_vendor(event_type: str) -> bool:
    """§11: a vendor name is never denylisted and never a core family name."""
    match = EXTENSION_TYPE.fullmatch(event_type)
    return match is not None and (denied_name(match["vendor"]) or match["vendor"][2:] in CORE_FAMILIES)


def _check_schema(
    tree: dict[str, Any],
    shape: Shape,
    payload_model: type[EventPayload],
    handler: ModelWrapValidatorHandler[Event],
) -> Event:
    """Check 13: no nulls, envelope and payload models, cross-field and required-scope rules."""
    errors = [entry.pointer for entry in walk(tree, shape) if entry.value is None]
    if _bad_vendor(tree["event_type"]):
        errors.append(("event_type",))
    working = dict(tree)
    if "payload" in tree:
        try:
            payload = payload_model.model_validate(tree["payload"])
        except ValidationError as exc:
            errors.extend(known_prefix(_error_path(("payload",), e), shape) for e in exc.errors())
            payload = EventPayload()
        scope = tree.get("scope")
        if type(scope) is dict:
            errors.extend(known_prefix(p, shape) for p in payload.scope_errors(scope))
        working["payload"] = payload
    event: Event | None = None
    try:
        event = handler(working)
    except ValidationError as exc:
        errors.extend(known_prefix(_error_path((), e), shape) for e in exc.errors())
    _reject_at(RejectCode.SCHEMA_VIOLATION, errors, _QUARANTINE)
    if event is None:  # pragma: no cover - a failed handler always reports an error
        raise EventRejection(RejectCode.SCHEMA_VIOLATION, "", _QUARANTINE)
    return event


def _first_difference(given: object, built: object, path: Pointer) -> Pointer | None:
    """The first path where ``built`` differs from ``given`` in type or value (no coercion, C22)."""
    if type(given) is not type(built):
        return path
    children: list[tuple[Segment, object, object]]
    if type(given) is dict:
        given_map, built_map = typing.cast(dict[str, object], given), typing.cast(dict[str, object], built)
        if given_map.keys() != built_map.keys():
            return path
        children = [(key, value, built_map[key]) for key, value in given_map.items()]
    elif type(given) is list:
        given_list, built_list = typing.cast(list[object], given), typing.cast(list[object], built)
        if len(given_list) != len(built_list):
            return path
        children = [(index, *pair) for index, pair in enumerate(zip(given_list, built_list, strict=True))]
    else:
        return None if given == built else path
    for key, value, other in children:
        found = _first_difference(value, other, (*path, key))
        if found is not None:
            return found
    return None


def _check_exact(tree: dict[str, Any], event: Event, shape: Shape) -> None:
    """Check 13 (C22): the event holds exactly the given values; only timestamp fractions are normalised."""
    expected = dict(tree)
    time = tree.get("time")
    if type(time) is dict:
        expected["time"] = {k: canonical_timestamp(v) for k, v in typing.cast(dict[str, str], time).items()}
    difference = _first_difference(expected, to_tree(event), ())
    if difference is not None:
        raise EventRejection(
            RejectCode.SCHEMA_VIOLATION, format_pointer(known_prefix(difference, shape)), _QUARANTINE
        )


def _check_references(event: Event) -> None:
    """Check 14: derived event ids, v8 only when derived, self references (§§4, 8)."""
    found: list[Pointer] = []
    source = event.source
    if source.provider_event_id is not None:
        derived = derive_event_id(event.scope.workspace_id, source.provider, source.provider_event_id)
        if event.event_id != derived:
            found.append(("event_id",))
    elif uuid_version(event.event_id) == 8:
        found.append(("event_id",))
    if event.causality is not None and event.causality.causation_id == event.event_id:
        found.append(("causality", "causation_id"))
    found.extend(event.payload.reference_errors(event))
    _reject_at(RejectCode.INVALID_REFERENCE, found, _QUARANTINE)


# --- re-validation (C4) -------------------------------------------------------------------


def revalidate(event: object) -> Event:
    """A freshly validated copy of an exact, untampered ``Event``, under the rules it carries.

    A subclass is a ``TypeError``. A forged instance (``model_construct``, mutation, a
    copied or altered stamp) or one that fails re-validation is a ``ValueError``.
    """
    if type(event) is not Event:
        raise TypeError("an exact Event is required")
    private = event.__pydantic_private__ or {}
    stamp = private.get("_stamp")
    if type(stamp) is not _Stamp:
        raise ValueError("event was not built by validation")
    try:
        tree = event_tree(event)
        canonical = canonical_text(tree).encode("utf-8")
    except (EventRejection, TypeError, ValueError):
        raise ValueError("event is not a valid tree") from None
    if not hmac.compare_digest(stamp.mac, _mac(stamp.version, stamp.recorded, canonical)):
        raise ValueError("event was altered after validation")
    if not stamp.recorded and stamp.version != current_rules_version():
        raise ValueError("event stamp names a rules version other than the current one")
    try:
        with _recorded_rules(stamp.version if stamp.recorded else None):
            return Event.model_validate(tree)
    except ValidationError:
        raise ValueError("event failed re-validation") from None


# --- recorded events (§14, C23) ---------------------------------------------------------------

_RECORD_TYPES: Final[Mapping[str, type]] = MappingProxyType(
    {"fingerprint": str, "ingested_at": str, "ingest_seq": int, "secret_rules_version": int, "policy_id": str}
)


def _fingerprint(event: Event) -> str:
    return (
        "sha256:" + hashlib.sha256(canonical_text(event_tree(revalidate(event))).encode("utf-8")).hexdigest()
    )


class RecordedEvent(BaseModel):
    """An accepted event as ingestion stores it, validated under its recorded rules version.

    Validating one is the only way to name an older rules version (C23); ``load_recorded``
    calls it on rows read from the event store, never on incoming events.
    """

    model_config = STRICT

    event: Event
    fingerprint: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
    ingested_at: Timestamp
    ingest_seq: Annotated[int, Field(ge=0, le=MAX_SAFE_INT)]
    secret_rules_version: Annotated[int, Field(ge=1)]
    policy_id: Code | None = None

    @model_validator(mode="wrap")
    @classmethod
    def _under_recorded_rules(
        cls, data: Any, handler: ModelWrapValidatorHandler[RecordedEvent]
    ) -> RecordedEvent:
        if type(data) is not dict:
            raise ValueError("a recorded event is a mapping")
        version = data.get("secret_rules_version")
        rules_for(version)  # an unknown version is a ValueError
        if any(name in data and type(data[name]) is not kind for name, kind in _RECORD_TYPES.items()):
            raise ValueError("recorded event fields have exact types")  # no coercion (C22)
        if type(data.get("event")) is Event:
            data = {**data, "event": event_tree(data["event"])}
        with _recorded_rules(typing.cast(int, version)):
            record = handler(data)
        if _fingerprint(record.event) != record.fingerprint:
            raise ValueError("fingerprint does not match the event")
        return record

    @classmethod
    def model_validate(cls, obj: Any, *, strict: bool | None = None, **kwargs: Any) -> Self:
        """Strict validation whatever ``strict`` says (C22)."""
        del strict
        return super().model_validate(obj, strict=True, **kwargs)

    @classmethod
    def model_validate_json(cls, *args: Any, **kwargs: Any) -> NoReturn:
        """Refused: use ``load_recorded`` on a decoded row."""
        del args, kwargs
        raise TypeError("RecordedEvent.model_validate_json is refused; use observatory.events.load_recorded")

    @classmethod
    def model_validate_strings(cls, *args: Any, **kwargs: Any) -> NoReturn:
        """Refused: use ``load_recorded`` on a decoded row."""
        del args, kwargs
        raise TypeError(
            "RecordedEvent.model_validate_strings is refused; use observatory.events.load_recorded"
        )
