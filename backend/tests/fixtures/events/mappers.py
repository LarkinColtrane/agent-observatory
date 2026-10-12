"""Test-only mappers from three SYNTHETIC provider shapes to ADR-0008 events.

These are **not** product adapters (P3 builds those). They live under
``tests/``, map only the synthetic fixtures next to them, and exist to show
that one shared scenario maps to the same projection from three shapes
(ADR-0008 §18). They follow §4 for ids (qualified native ids, derived event ids
for provider events, UUIDv7s otherwise), §6 for time (UTC ``Z``; absent stays
absent), §7 for streams and §10.4 for free text (``sanitize_text`` and the command
pipeline). Every event goes through ``validate_event``.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from observatory.events import (
    SECRET_RULES,
    SECRET_RULES_VERSION,
    Accepted,
    Event,
    derive_event_id,
    sanitize_text,
    validate_event,
)

FIXTURES: Final = Path(__file__).parent
WORKSPACE: Final = "synthetic-ws"
PROVIDER_A: Final = "synthetic-transcript"
PROVIDER_B: Final = "synthetic-orchestrator"
PROVIDER_C: Final = "synthetic-pyagent"
MAPPER_VERSION: Final = "1.0.0"
MAX_COMMAND: Final = 1024
_ID_ALPHABET: Final = re.compile(r"[A-Za-z0-9._:-]+")
_HEREDOC: Final = re.compile(r"<<-?\s*['\"]?[A-Za-z_]")


# --- §4 and §10.4 helpers ------------------------------------------------------------------


def entity_id(provider: str, native: str) -> str:
    """``<provider>:<native>``, or ``<provider>:h.<32 hex>`` when ``native`` cannot be used verbatim (§4)."""
    rules = SECRET_RULES[SECRET_RULES_VERSION]
    verbatim = (
        _ID_ALPHABET.fullmatch(native) is not None
        and len(native) <= 127 - len(provider)
        and not native.startswith("h.")
        and not rules.string_hit(native, text_tier=False)
    )
    if verbatim:
        return f"{provider}:{native}"
    return f"{provider}:h.{hashlib.sha256(native.encode('utf-8', 'surrogatepass')).hexdigest()[:32]}"


def command_text(raw: str) -> str:
    """§10.4: first line up to a heredoc marker; sanitise, cut with `` [TRUNCATED]``, repeat until stable."""
    line = raw.split("\n", 1)[0]
    heredoc = _HEREDOC.search(line)
    text = sanitize_text(line[: heredoc.start()].rstrip() if heredoc else line)
    while len(text) > MAX_COMMAND:
        text = sanitize_text(text[: MAX_COMMAND - len(" [TRUNCATED]")] + " [TRUNCATED]")
    return text


def utc(timestamp: str) -> str:
    """An ISO timestamp with any offset as protocol UTC (``Z``, 6 fraction digits)."""
    instant = datetime.fromisoformat(timestamp).astimezone(UTC)
    return f"{instant:%Y-%m-%dT%H:%M:%S}.{instant.microsecond:06d}Z"


class SyntheticClock:
    """A fixed, deterministic emitter clock: one tick per observation."""

    def __init__(self, start: str, step: timedelta = timedelta(milliseconds=250)) -> None:
        self._now = datetime.fromisoformat(start)
        self._step = step

    def tick(self) -> str:
        self._now += self._step
        return utc(self._now.isoformat())

    def millis(self) -> int:
        return int(self._now.timestamp() * 1000)


def uuid7(rng: random.Random, millis: int) -> str:
    """A UUIDv7 from a millisecond time and a seeded generator."""
    value = (millis & ((1 << 48) - 1)) << 80 | (0x7 << 76) | rng.getrandbits(12) << 64
    value |= (0b10 << 62) | rng.getrandbits(62)
    text = f"{value:032x}"
    return f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"


def accept(tree: dict[str, Any]) -> Event:
    result = validate_event(tree)
    if not isinstance(result, Accepted):
        raise AssertionError(f"mapper produced a rejected event: {result.code} at {result.pointer}")
    return result.event


def _envelope(
    provider: str,
    event_type: str,
    scope: dict[str, str],
    payload: dict[str, Any],
    *,
    event_id: str,
    observed_at: str,
    occurred_at: str | None = None,
    provider_event_id: str | None = None,
    stream: tuple[str, int] | None = None,
) -> dict[str, Any]:
    source: dict[str, Any] = {
        "provider": provider,
        "adapter": {"name": f"{provider}-mapper", "version": MAPPER_VERSION},
    }
    if stream is not None:
        source["stream_id"], source["seq"] = stream
    if provider_event_id is not None:
        source["provider_event_id"] = provider_event_id
    time = {"observed_at": observed_at} | ({"occurred_at": occurred_at} if occurred_at else {})
    return {
        "spec_version": "1.0",
        "event_id": event_id,
        "event_type": event_type,
        "scope": {"workspace_id": WORKSPACE, **scope},
        "time": time,
        "source": source,
        "payload": payload,
    }


def _jsonl(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if line]


def _json(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


# --- A: Claude/Codex-like transcript ------------------------------------------------------


def load_a() -> list[dict[str, Any]]:
    return _jsonl("synthetic-provider-a-transcript.jsonl")


def _relative(path: str, cwd: str) -> str:
    return path[len(cwd) + 1 :] if path.startswith(cwd + "/") else path


def _canonical_usage(raw: dict[str, Any]) -> dict[str, int]:
    """Anthropic-like counts (cache reads and writes outside ``input_tokens``) to ADR-0007 meanings."""
    cached = raw.get("cache_read_input_tokens", 0)
    total_input = raw["input_tokens"] + cached + raw.get("cache_creation_input_tokens", 0)
    return {"input_tokens": total_input, "cached_input_tokens": cached, "output_tokens": raw["output_tokens"]}


def map_transcript(
    entries: list[dict[str, Any]], *, observed_start: str = "2026-03-02T12:00:00Z"
) -> list[Event]:
    """Shape A, read in order: one stream per transcript; ids derived from qualified entry uuids."""
    clock = SyntheticClock(observed_start)
    cwd = next(e["cwd"] for e in entries if "cwd" in e)
    session_native = entries[0]["sessionId"]
    session = entity_id(PROVIDER_A, session_native)
    stream_id = entity_id(PROVIDER_A, f"transcript-{session_native}")
    tool_inputs: dict[str, tuple[str, dict[str, Any]]] = {}
    events: list[Event] = []

    def emit(entry: dict[str, Any], part: str, event_type: str, payload: dict[str, Any]) -> None:
        native_ref = f"{entry['sessionId']}/{entry['uuid']}#{part}"  # qualified by session (§4)
        scope = {"session_id": session, "agent_id": entity_id(PROVIDER_A, entry["agentId"])}
        tree = _envelope(
            PROVIDER_A,
            event_type,
            scope,
            payload,
            event_id=derive_event_id(WORKSPACE, PROVIDER_A, native_ref),
            provider_event_id=native_ref,
            occurred_at=utc(entry["timestamp"]),
            observed_at=clock.tick(),
            stream=(stream_id, len(events)),
        )
        events.append(accept(tree))

    for entry in entries:
        if entry["type"] == "system":
            if entry["subtype"] == "session_start":
                emit(
                    entry,
                    "start",
                    "session.started",
                    {"session_id": session, "initiator": entry["initiator"]},
                )
            else:
                emit(entry, "end", "session.ended", {"session_id": session, "outcome": entry["outcome"]})
            continue
        message = entry["message"]
        for index, block in enumerate(message["content"]):
            if block["type"] == "tool_use":
                tool_inputs[block["id"]] = (block["name"], block["input"])
                _emit_tool_use(entry, block, cwd, lambda t, p, i=index, e=entry: emit(e, str(i), t, p))
            elif block["type"] == "tool_result":
                name, tool_input = tool_inputs[block["tool_use_id"]]
                result = entry.get("toolUseResult", {})
                call_id = entity_id(PROVIDER_A, block["tool_use_id"])
                finished: dict[str, Any] = {
                    "call_id": call_id,
                    "outcome": "failed" if block["is_error"] else "succeeded",
                }
                if "exit_code" in result:
                    finished["exit_code"] = result["exit_code"]
                emit(entry, str(index), "tool.call_finished", finished)
                if name == "Write" and result.get("type") in ("create", "update"):
                    content = tool_input["content"]
                    emit(
                        entry,
                        f"{index}.file",
                        "file.changed",
                        {
                            "path": _relative(tool_input["file_path"], cwd),
                            "change": "created" if result["type"] == "create" else "modified",
                            "call_id": call_id,
                            "lines_added": content.count("\n") + (0 if content.endswith("\n") else 1),
                        },
                    )
        if "usage" in message:
            emit(
                entry,
                "usage",
                "usage.recorded",
                {
                    "usage": _canonical_usage(message["usage"]),
                    "accounting": "delta",
                    "unit": "model_call",
                    "model": message["model"],
                },
            )
    return events


def _emit_tool_use(entry: dict[str, Any], block: dict[str, Any], cwd: str, emit: Any) -> None:
    tool_input = block["input"]
    if block["name"] == "Task":  # a sub-agent spawn; the spawner is the scope agent
        emit(
            "agent.spawned",
            {
                "agent_id": entity_id(PROVIDER_A, tool_input["subagent_type"]),
                "parent_agent_id": entity_id(PROVIDER_A, entry["agentId"]),
                "role": sanitize_text(tool_input["description"]),
            },
        )
        return
    payload: dict[str, Any] = {"call_id": entity_id(PROVIDER_A, block["id"]), "tool_name": block["name"]}
    if block["name"] == "Bash":
        payload |= {"kind": "command", "command": command_text(tool_input["command"])}
    elif block["name"] == "Write":
        payload |= {"kind": "file_write", "target_path": _relative(tool_input["file_path"], cwd)}
    elif block["name"] == "Grep":
        payload |= {"kind": "search", "query": sanitize_text(tool_input["pattern"])}
    else:
        payload["kind"] = "other"
    emit("tool.call_started", payload)


# --- B: generic orchestrator webhooks ---------------------------------------------------------

_B_STATUS: Final = {
    "IN_PROGRESS": "in_progress",
    "DONE": "completed",
    "BLOCKED": "blocked",
    "TODO": "pending",
}
_B_VERDICT: Final = {"APPROVED": "approve", "CHANGES_REQUESTED": "request_changes", "REJECTED": "reject"}


def load_b() -> dict[str, Any]:
    return _json("synthetic-provider-b-webhooks.json")


def map_webhooks(document: dict[str, Any]) -> list[Event]:
    """Shape B: unordered deliveries, no stream; the orchestrator event id is the provider event id."""
    return [accept(_webhook_tree(delivery)) for delivery in document["deliveries"]]


def _webhook_tree(delivery: dict[str, Any]) -> dict[str, Any]:
    event = delivery["event"]

    def qid(native: str) -> str:
        return entity_id(PROVIDER_B, native)

    kind = event["type"]
    if kind == "agent.started":
        agent = event["agent"]
        event_type = "agent.spawned"
        payload: dict[str, Any] = {
            "agent_id": qid(agent["name"]),
            "parent_agent_id": qid(agent["parent"]),
            "role": sanitize_text(agent["role"]),
        }
    elif kind == "agent.finished":
        event_type, payload = (
            "agent.terminated",
            {"agent_id": qid(event["agent"]["name"]), "reason": event["reason"]},
        )
    elif kind == "task.created":
        task = event["task"]
        event_type = "task.created"
        payload = {"task_id": qid(task["id"]), "title": sanitize_text(task["title"])}
        if task.get("depends_on"):
            payload["depends_on"] = sorted(qid(t) for t in task["depends_on"])
    elif kind == "task.assigned":
        event_type = "task.assigned"
        payload = {"task_id": qid(event["task"]["id"]), "assignee_agent_id": qid(event["assignee"])}
    elif kind == "task.status":
        event_type = "task.status_changed"
        payload = {"task_id": qid(event["task"]["id"]), "status": _B_STATUS[event["status"]]}
    else:  # review.submitted
        review = event["review"]
        event_type = "review.verdict_recorded"
        payload = {
            "review_id": qid(review["id"]),
            "verdict": _B_VERDICT[review["verdict"]],
            "subject_task_id": qid(review["task"]),
            "findings": review["findings"],
            "blocking_findings": review["blocking"],
        }
    return _envelope(
        PROVIDER_B,
        event_type,
        {"session_id": qid(event["run"]), "agent_id": qid(event["actor"])},
        payload,
        event_id=derive_event_id(WORKSPACE, PROVIDER_B, event["id"]),
        provider_event_id=event["id"],
        occurred_at=utc(event["occurred_at"]),
        observed_at=utc(delivery["received_at"]),
    )


# --- C: minimal custom Python agent (SDK-like emitter) ---------------------------------------------


def load_c() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _json("synthetic-provider-c-agent.json")["steps"]
    return steps


def map_agent(
    steps: list[dict[str, Any]], *, seed: int = 7, start: str = "2026-03-02T09:00:00Z"
) -> list[Event]:
    """Shape C: no times or ids in the source; the SDK assigns a stream, seq, clock and UUIDv7s."""
    rng = random.Random(seed)  # noqa: S311 (seeded synthetic ids, not cryptography)
    clock = SyntheticClock(start)
    stream_id = entity_id(PROVIDER_C, "sdk-stream-1")
    session = ""
    events: list[Event] = []
    for step in steps:
        if step["op"] == "session_start":
            session = entity_id(PROVIDER_C, step["session"])
        event_type, payload = _agent_step({**step, "ordinal": len(events)}, session)
        observed_at = clock.tick()
        tree = _envelope(
            PROVIDER_C,
            event_type,
            {"session_id": session, "agent_id": entity_id(PROVIDER_C, step["by"])},
            payload,
            event_id=uuid7(rng, clock.millis()),
            observed_at=observed_at,
            stream=(stream_id, len(events)),
        )
        events.append(accept(tree))
    return events


def _agent_step(step: dict[str, Any], session: str) -> tuple[str, dict[str, Any]]:  # noqa: PLR0911 (one per op)
    def qid(native: str) -> str:
        return entity_id(PROVIDER_C, native)

    op = step["op"]
    if op in ("session_start", "session_end"):
        if op == "session_start":
            return "session.started", {"session_id": session, "initiator": step["initiator"]}
        return "session.ended", {"session_id": session, "outcome": step["outcome"]}
    if op == "spawn":
        return "agent.spawned", {
            "agent_id": qid(step["agent"]),
            "parent_agent_id": qid(step["by"]),
            "role": sanitize_text(step["role"]),
        }
    if op == "stop":
        return "agent.terminated", {"agent_id": qid(step["agent"]), "reason": step["reason"]}
    if op.startswith("task_"):
        return _task_step(step, qid)
    if op.startswith("tool_"):
        return _tool_step(step, qid)
    return _other_step(step, qid)


def _task_step(step: dict[str, Any], qid: Any) -> tuple[str, dict[str, Any]]:
    if step["op"] == "task_create":
        payload: dict[str, Any] = {"task_id": qid(step["task"]), "title": sanitize_text(step["title"])}
        if step.get("after"):
            payload["depends_on"] = sorted(qid(t) for t in step["after"])
        return "task.created", payload
    if step["op"] == "task_assign":
        return "task.assigned", {"task_id": qid(step["task"]), "assignee_agent_id": qid(step["to"])}
    return "task.status_changed", {"task_id": qid(step["task"]), "status": step["status"]}


def _tool_step(step: dict[str, Any], qid: Any) -> tuple[str, dict[str, Any]]:
    if step["op"] == "tool_end":
        payload: dict[str, Any] = {
            "call_id": qid(step["call"]),
            "outcome": "succeeded" if step["ok"] else "failed",
        }
        if "exit_code" in step:
            payload["exit_code"] = step["exit_code"]
        return "tool.call_finished", payload
    payload = {"call_id": qid(step["call"]), "tool_name": step["tool"], "kind": step["kind"]}
    if "command" in step:
        payload["command"] = command_text(step["command"])
    if "path" in step:
        payload["target_path"] = step["path"]
    return "tool.call_started", payload


def _other_step(step: dict[str, Any], qid: Any) -> tuple[str, dict[str, Any]]:
    op = step["op"]
    if op == "file":
        return "file.changed", {
            "path": step["path"],
            "change": step["change"],
            "call_id": qid(step["call"]),
            "lines_added": step["added"],
        }
    if op == "usage":
        usage = {
            "input_tokens": step["prompt_tokens"],
            "cached_input_tokens": step["cached_prompt_tokens"],
            "output_tokens": step["completion_tokens"],
        }
        return "usage.recorded", {
            "usage": usage,
            "accounting": "delta",
            "unit": "model_call",
            "model": step["model"],
        }
    if op == "review":
        return "review.verdict_recorded", {
            "review_id": qid(step["review"]),
            "verdict": step["verdict"],
            "subject_task_id": qid(step["task"]),
            "findings": step["findings"],
            "blocking_findings": step["blocking"],
        }
    if op == "test":
        failed = step["failed"]
        return "test.run_completed", {
            "run_id": qid(step["run"]),
            "outcome": "failed" if failed else "passed",
            "call_id": qid(step["call"]),
            "framework": step["framework"],
            "passed": step["passed"],
            "failed": failed,
        }
    if op == "error":
        return "error.reported", {
            "error_code": step["code"],
            "severity": "error",
            "message": sanitize_text(step["text"]),
            "call_id": qid(step["call"]),
        }
    return "message.sent", {
        "message_id": qid(f"message-{step['ordinal']}"),
        "intent": step["intent"],
        "to_agent_ids": sorted(qid(a) for a in step["to"]),
    }


# --- the projection compared across shapes ----------------------------------------------------------


def projection(event: Event) -> dict[str, Any]:
    """``(event_type, scope, payload)``, with the ``<provider>:`` qualification of entity ids removed.

    §4 qualifies every native entity id by its provider, so the same agent or
    task has a different id in each shape. The comparison strips that prefix;
    ids, times and provenance are deliberately left out.
    """
    tree = json.loads(event.model_dump_json(exclude_none=True))
    prefix = event.source.provider + ":"

    def strip(value: Any) -> Any:
        if isinstance(value, str):
            return value.removeprefix(prefix)
        if isinstance(value, list):
            return [strip(v) for v in value]
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items()}
        return value

    return {
        "event_type": tree["event_type"],
        "scope": strip(tree["scope"]),
        "payload": strip(tree["payload"]),
    }


def unique(events: list[Event]) -> Iterator[Event]:
    """Events with distinct ``event_id``s, first copy wins (a re-delivery is a no-op, §15)."""
    seen: set[str] = set()
    for event in events:
        if event.event_id not in seen:
            seen.add(event.event_id)
            yield event
