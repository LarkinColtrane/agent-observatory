"""Recorded events and secret-rules versions (ADR-0008 §§12, 14; AO-P2-003 AC8, C4).

A rules patch (version N+1) must never make replay of an event accepted under
N fail, and accepting a new event can never name an older rules version.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from observatory.events import (
    Accepted,
    Event,
    RecordedEvent,
    RejectCode,
    Rejected,
    canonical_json,
    fingerprint,
    load_recorded,
    parse_event,
    validate_event,
)
from observatory.events import text as text_module
from observatory.events.envelope import event_tree
from tests.unit.events.factory import build, tree

MARKER = "zz-v2-" + "marker"


def _record(event: Event, version: int = 1, **changes: object) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event": event_tree(event),
        "fingerprint": fingerprint(event),
        "ingested_at": "2026-03-01T10:00:02Z",
        "ingest_seq": 17,
        "secret_rules_version": version,
    }
    record.update(changes)
    return record


def test_load_recorded_round_trip() -> None:
    event = build()
    loaded = load_recorded(_record(event, policy_id="default-policy"))
    assert isinstance(loaded, RecordedEvent)
    assert not isinstance(loaded, Accepted)
    assert loaded.event == event
    assert loaded.ingested_at == "2026-03-01T10:00:02.000000Z"
    assert (loaded.ingest_seq, loaded.secret_rules_version, loaded.policy_id) == (17, 1, "default-policy")
    assert canonical_json(loaded.event) == canonical_json(event)
    assert RecordedEvent.model_validate({**_record(event), "event": event}).event == event


@pytest.mark.parametrize(
    "changes",
    [
        {"secret_rules_version": 0},
        {"secret_rules_version": 2},
        {"secret_rules_version": "1"},
        {"secret_rules_version": True},
        {"secret_rules_version": None},
        {"fingerprint": "sha256:" + "0" * 64},
        {"fingerprint": "md5:x"},
        {"ingest_seq": -1},
        {"ingested_at": "2026-03-01"},
        {"policy_id": "Bad Policy"},
        {"extra": 1},
    ],
)
def test_load_recorded_rejects_bad_records(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="recorded event"):
        load_recorded(_record(build(), **changes))
    record = _record(build())
    del record["secret_rules_version"]
    with pytest.raises(ValueError, match="recorded event"):
        load_recorded(record)
    with pytest.raises(TypeError):
        load_recorded([("event", 1)])  # type: ignore[arg-type]


@pytest.fixture
def rules_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Release a synthetic rules patch (version 2) that adds one detector."""

    def marker(text: str) -> str:
        return text.replace(MARKER, "[REDACTED]")

    v1 = text_module.RULES_V1
    v2 = dataclasses.replace(v1, version=2, credential=(*v1.credential, marker))
    monkeypatch.setattr(text_module, "SECRET_RULES", text_module._Rules({1: v1, 2: v2}))
    monkeypatch.setattr(text_module, "SECRET_RULES_VERSION", 2)


def test_event_accepted_under_n_replays_under_n_plus_1(monkeypatch: pytest.MonkeyPatch) -> None:
    event = build(("scope.task_id", MARKER))
    record = _record(event)
    before = canonical_json(event)
    v1 = text_module.RULES_V1
    v2 = dataclasses.replace(v1, version=2, credential=(*v1.credential, lambda s: s.replace(MARKER, "[R]")))
    monkeypatch.setattr(text_module, "SECRET_RULES", text_module._Rules({1: v1, 2: v2}))
    monkeypatch.setattr(text_module, "SECRET_RULES_VERSION", 2)

    loaded = load_recorded(record)  # the recorded-version path
    assert canonical_json(loaded.event) == before
    assert fingerprint(loaded.event) == record["fingerprint"]

    # Accepting a new event always uses rules 2 and cannot name rules 1.
    for result in (validate_event(record["event"]), parse_event(before)):
        assert isinstance(result, Rejected)
        assert result.code is RejectCode.SECRET_DETECTED
    with pytest.raises(ValueError, match="secret_detected"):
        Event.model_validate(record["event"])
    with pytest.raises(ValueError, match="recorded event"):
        load_recorded({**record, "secret_rules_version": 2})
    # The loaded event cannot be smuggled back through an acceptance path.
    assert isinstance(validate_event(event_tree(loaded.event)), Rejected)
    # An event stamped under rules 1 outside the recorded path now fails closed (Reviewer A).
    with pytest.raises(ValueError, match="other than the current"):
        canonical_json(event)


@pytest.mark.usefixtures("rules_v2")
def test_recorded_stamp_cannot_be_moved_to_another_event() -> None:
    clean = build()
    loaded = load_recorded(_record(clean)).event  # stamped as recorded under rules 1
    other = Event.model_validate(tree(("scope.task_id", "t-9")))  # stamped under rules 2
    object.__setattr__(other, "__pydantic_private__", dict(loaded.__pydantic_private__ or {}))
    with pytest.raises(ValueError, match="altered"):
        canonical_json(other)
    assert canonical_json(loaded) == canonical_json(clean.model_copy())  # same content, valid stamps


@pytest.mark.usefixtures("rules_v2")
def test_current_rules_still_accept_clean_events() -> None:
    result = validate_event(tree())
    assert isinstance(result, Accepted)
    assert load_recorded(_record(result.event, version=2)).event == result.event
    assert load_recorded(_record(result.event, version=1)).secret_rules_version == 1
