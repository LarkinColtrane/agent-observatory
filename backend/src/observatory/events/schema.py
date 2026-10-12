r"""Informative JSON Schema of event protocol v1, generated from the models (ADR-0008 §17).

The Python validator is normative: a JSON Schema cannot express §10 (secrets,
forbidden characters), the cross-field rules or the references. Regenerate the
checked-in copy with::

    cd backend && .venv/bin/python -m observatory.events.schema \
        > ../docs/contracts/event-protocol-v1.schema.json
"""

from __future__ import annotations

import json
import sys
from typing import Any, Final

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from observatory.events.envelope import SPEC_VERSION, Event
from observatory.events.payloads import EXTENSION_TYPE, ExtensionPayload
from observatory.events.taxonomy import PAYLOADS

SCHEMA_ID: Final = "https://agent-observatory.invalid/contracts/event-protocol-v1.schema.json"


def _without_nulls(node: Any) -> Any:
    """Drop the ``null`` branches and ``null`` defaults Pydantic emits for optional fields (no nulls, §2)."""
    if isinstance(node, list):
        return [_without_nulls(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {k: _without_nulls(v) for k, v in node.items() if not (k == "default" and v is None)}
    if "anyOf" in out:
        out["anyOf"] = [option for option in out["anyOf"] if option != {"type": "null"}]
        if len(out["anyOf"]) == 1:
            out.update(out.pop("anyOf")[0])
    return out


def json_schema() -> dict[str, Any]:
    """The schema: the envelope, plus the payload selected by each ``event_type``."""
    payloads = PAYLOADS[SPEC_VERSION]
    models: list[type[BaseModel]] = [Event, ExtensionPayload, *payloads.values()]
    _, generated = models_json_schema([(m, "validation") for m in models], ref_template="#/$defs/{model}")
    defs = generated["$defs"]
    defs["Event"]["properties"]["payload"] = {"type": "object", "description": "selected by event_type"}
    defs["Event"]["properties"]["spec_version"] = {"const": SPEC_VERSION}
    del defs["EventPayload"]
    dispatch: list[dict[str, Any]] = [
        {
            "if": {"properties": {"event_type": {"const": name}}},
            "then": {"properties": {"payload": {"$ref": f"#/$defs/{model.__name__}"}}},
        }
        for name, model in sorted(payloads.items())
    ]
    dispatch.append(
        {
            "if": {"properties": {"event_type": {"pattern": f"^{EXTENSION_TYPE.pattern}$"}}},
            "then": {"properties": {"payload": {"$ref": "#/$defs/ExtensionPayload"}}},
        }
    )
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": f"Agent Observatory event protocol {SPEC_VERSION} (informative)",
        "description": "Generated from observatory.events; the Python validator is normative (ADR-0008 §17).",
        "$ref": "#/$defs/Event",
        "properties": {"event_type": {"enum": sorted(payloads)}},
        "allOf": dispatch,
        "$defs": defs,
    }
    return dict(_without_nulls(schema))


def render() -> str:
    """Deterministic text: sorted keys, 2-space indent, ASCII, trailing newline."""
    return json.dumps(json_schema(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render())
