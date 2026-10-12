"""Exact types only: construction runs checks 9-15, forged instances are refused (ADR-0008 §12; AC6, C4)."""

from __future__ import annotations

import copy
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from observatory.events import (
    Adapter,
    Event,
    EventRejection,
    EventTime,
    RejectCode,
    Scope,
    Source,
    canonical_json,
    canonical_order,
    classify_duplicate,
    content_fingerprint,
    fingerprint,
    stream_key,
)
from observatory.events.envelope import _Stamp
from observatory.events.taxonomy import SessionStarted
from tests.unit.events.factory import EVENT_ID, OTHER_ID, SK, build, tree

PURE: dict[str, Callable[[Event], object]] = {
    "canonical_json": canonical_json,
    "fingerprint": fingerprint,
    "content_fingerprint": content_fingerprint,
    "stream_key": stream_key,
    "canonical_order": lambda e: canonical_order([e]),
    "classify_existing": lambda e: classify_duplicate(e, build()),
    "classify_incoming": lambda e: classify_duplicate(build(), e),
}


def _code(exc: ValidationError) -> RejectCode:
    cause = exc.errors()[0]["ctx"]["error"]
    assert isinstance(cause, EventRejection)
    return cause.code


def _kwargs(**changes: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "spec_version": "1.0",
        "event_id": EVENT_ID,
        "event_type": "session.started",
        "scope": Scope(workspace_id="ws-1", session_id="sess-1"),
        "time": EventTime(observed_at="2026-03-01T10:00:01Z"),
        "source": Source(provider="claude-code", adapter=Adapter(name="cc-adapter", version="1.2.3")),
        "payload": SessionStarted(session_id="sess-1"),
    }
    kwargs.update(changes)
    return kwargs


def test_constructor_runs_the_checks() -> None:
    event = Event(**_kwargs())  # type: ignore[arg-type]
    assert event.time.observed_at == "2026-03-01T10:00:01.000000Z"
    assert canonical_json(event) == canonical_json(Event.model_validate(event.model_dump(exclude_none=True)))
    cases = {
        RejectCode.SECRET_DETECTED: _kwargs(payload=SessionStarted(session_id="claude-code:" + SK[:60])),
        RejectCode.FORBIDDEN_CHARACTER: _kwargs(scope={"workspace_id": "ws-1", "task_id": "a" + chr(0x7F)}),
        RejectCode.UNSUPPORTED_VERSION: _kwargs(spec_version="1.1"),
        RejectCode.UNKNOWN_EVENT_TYPE: _kwargs(event_type="nope"),
        RejectCode.SCHEMA_VIOLATION: _kwargs(causality={}),
        RejectCode.INVALID_REFERENCE: _kwargs(causality={"causation_id": EVENT_ID}),
    }
    for code, kwargs in cases.items():
        with pytest.raises(ValidationError) as info:
            Event(**kwargs)  # type: ignore[arg-type]
        assert _code(info.value) is code


class _Scope(Scope):
    pass


def test_constructor_refuses_foreign_types() -> None:
    for kwargs in (
        _kwargs(scope=_Scope(workspace_id="ws-1")),
        _kwargs(source={"provider": "claude-code", "adapter": object()}),
        _kwargs(extensions={"x-acme": {"a": 1.5}}),
    ):
        with pytest.raises(ValidationError) as info:
            Event(**kwargs)  # type: ignore[arg-type]
        assert _code(info.value) is RejectCode.INVALID_JSON
    deep: dict[str, object] = {}
    node = deep
    for _ in range(20):
        node["a"] = {}
        node = node["a"]  # type: ignore[assignment]
    with pytest.raises(ValidationError) as info:
        Event(**_kwargs(extensions={"x-acme": deep}))  # type: ignore[arg-type]
    assert _code(info.value) is RejectCode.TOO_DEEP


class _Event(Event):
    pass


def test_subclasses_cannot_be_validated() -> None:
    with pytest.raises(ValidationError):
        _Event.model_validate(tree())


def _forgeries() -> dict[str, Event]:
    valid = build()
    constructed = Event.model_construct(**valid.__dict__)
    bad_scope = build()
    object.__setattr__(bad_scope, "scope", Scope.model_construct(workspace_id="NOT VALID"))
    bad_payload = build()
    object.__setattr__(bad_payload.payload, "session_id", "claude-code:" + SK[:60])
    other_content = build()
    object.__setattr__(other_content, "event_id", OTHER_ID)
    swapped_stamp = build(("event_id", OTHER_ID))
    object.__setattr__(swapped_stamp, "__pydantic_private__", build().__pydantic_private__)
    copied = build()
    object.__setattr__(copied, "__pydantic_private__", {"_stamp": 1})
    stripped = build()
    object.__setattr__(stripped, "__pydantic_private__", None)
    foreign_value = build()
    object.__setattr__(foreign_value, "extensions", {"x-acme": {"a": 1.5}})
    return {
        "model_construct": constructed,
        "mutated scope": bad_scope,
        "mutated payload": bad_payload,
        "mutated id": other_content,
        "stamp from another event": swapped_stamp,
        "stamp is not a stamp": copied,
        "no private state": stripped,
        "foreign value": foreign_value,
    }


@pytest.mark.parametrize("function", PURE)
def test_pure_functions_refuse_subclasses_and_forgeries(function: str) -> None:
    call = PURE[function]
    subclass = _Event.model_construct(**build().__dict__)
    subclass._stamp = build()._stamp
    with pytest.raises(TypeError):
        call(subclass)
    with pytest.raises(TypeError):
        call(tree())  # type: ignore[arg-type]
    for name, forged in _forgeries().items():
        with pytest.raises(ValueError, match="event"):
            call(forged)
        del name


def test_reviewer_a_forged_rules_versions_fail_closed() -> None:
    event = build()
    stamp = event.__pydantic_private__["_stamp"]  # type: ignore[index]
    for forged in (
        _Stamp(version=stamp.version, recorded=True, mac=stamp.mac),  # claims the recorded path
        _Stamp(version=0, recorded=False, mac=stamp.mac),
        _Stamp(version=stamp.version, recorded=False, mac=b"\0" * 32),
    ):
        tampered = build()
        tampered._stamp = forged
        with pytest.raises(ValueError, match="event"):
            canonical_json(tampered)


def test_copies_keep_a_valid_stamp_and_equality_ignores_it() -> None:
    event = build()
    for duplicate in (copy.copy(event), copy.deepcopy(event), event.model_copy()):
        assert canonical_json(duplicate) == canonical_json(event)
    changed = event.model_copy(update={"event_id": OTHER_ID})
    with pytest.raises(ValueError, match="event"):
        canonical_json(changed)
    unstamped = Event.model_construct(**event.__dict__)
    assert unstamped == event  # the stamp is not part of the event (C4)
    assert hash(unstamped) == hash(event)
    assert event != build(("event_id", OTHER_ID))
    assert (event == "x") is False


def test_mixed_workspaces_are_refused() -> None:
    other = build(("event_id", OTHER_ID), ("scope.workspace_id", "ws-2"))
    with pytest.raises(ValueError, match="workspace"):
        canonical_order([build(), other])
    with pytest.raises(ValueError, match="workspace"):
        classify_duplicate(build(), other)
