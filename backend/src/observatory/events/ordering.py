"""Stream keys, canonical order and duplicate classification (ADR-0008 §§5, 7, 15)."""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from enum import StrEnum

from observatory.events.codec import content_fingerprint, fingerprint
from observatory.events.envelope import Event, revalidate

StreamKey = tuple[str, str, str, str]


class DuplicateKind(StrEnum):
    """How an incoming event relates to a stored one (§15), in order of precedence."""

    EXACT_DUPLICATE = "exact_duplicate"
    REDELIVERY = "redelivery"
    CONFLICT = "conflict"
    SEQUENCE_CONFLICT = "sequence_conflict"
    DISTINCT = "distinct"


def _key(event: Event) -> StreamKey | None:
    source = event.source
    if source.stream_id is None:
        return None
    return (event.scope.workspace_id, source.provider, source.adapter.name, source.stream_id)


def stream_key(event: Event) -> StreamKey | None:
    """``(workspace_id, provider, adapter name, stream_id)``, or ``None`` for an event without a stream."""
    return _key(revalidate(event))


def _effective_time(event: Event) -> str:
    return event.time.occurred_at or event.time.observed_at  # canonical strings order as instants


def _one_workspace(events: Iterable[Event]) -> None:
    if len({e.scope.workspace_id for e in events}) > 1:
        raise ValueError("events from more than one workspace")


def canonical_order(events: Iterable[Event]) -> list[Event]:
    """Deterministic replay order of one workspace's events with unique ids (§7)."""
    given = list(events)
    checked = [revalidate(e) for e in given]
    _one_workspace(checked)
    if len({e.event_id for e in checked}) != len(checked):
        raise ValueError("duplicate event_id: classify duplicates first")
    groups: dict[StreamKey, list[tuple[int, str, int]]] = {}
    for index, event in enumerate(checked):
        key = _key(event)
        seq = event.source.seq if key is not None and event.source.seq is not None else -1
        group = key if key is not None else (event.scope.workspace_id, "", "", event.event_id)
        groups.setdefault(group, []).append((seq, event.event_id, index))
    heads: list[tuple[str, StreamKey, int, str, int]] = []
    for group, members in groups.items():
        members.sort(reverse=True)  # pop() takes the smallest (seq, event_id)
        seq, event_id, index = members.pop()
        heads.append((_effective_time(checked[index]), group, seq, event_id, index))
    heapq.heapify(heads)
    ordered: list[Event] = []
    while heads:
        _time, group, _seq, _event_id, index = heapq.heappop(heads)
        ordered.append(given[index])
        members = groups[group]
        if members:
            seq, event_id, index = members.pop()
            heapq.heappush(heads, (_effective_time(checked[index]), group, seq, event_id, index))
    return ordered


def classify_duplicate(existing: Event, incoming: Event) -> DuplicateKind:
    """The first matching kind, in the precedence of §15; both events must share a workspace."""
    old, new = revalidate(existing), revalidate(incoming)
    _one_workspace((old, new))
    if old.event_id == new.event_id:
        if fingerprint(existing) == fingerprint(incoming):
            return DuplicateKind.EXACT_DUPLICATE
        if content_fingerprint(existing) == content_fingerprint(incoming):
            return DuplicateKind.REDELIVERY
        return DuplicateKind.CONFLICT
    old_key = _key(old)
    if old_key is not None and old_key == _key(new) and old.source.seq == new.source.seq:
        return DuplicateKind.SEQUENCE_CONFLICT
    return DuplicateKind.DISTINCT
