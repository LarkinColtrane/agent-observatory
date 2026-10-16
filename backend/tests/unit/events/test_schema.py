r"""Golden test for the informative JSON Schema (ADR-0008 §17; AO-P2-004 AC3).

If this fails after an intended model change, regenerate the checked-in copy from the repository root
and review the diff::

    cd backend && .venv/bin/python -m observatory.events.schema \
        > ../docs/contracts/event-protocol-v1.schema.json
"""

from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from typing import Any

import pytest

from observatory.events.schema import _without_nulls, json_schema, render
from observatory.events.taxonomy import PAYLOADS
from tests.unit.events.test_golden import GOLDEN as GOLDEN_EVENTS

GOLDEN = Path(__file__).resolve().parents[4] / "docs" / "contracts" / "event-protocol-v1.schema.json"
REGENERATE = (
    "schema drift: regenerate with `cd backend && .venv/bin/python -m observatory.events.schema "
    "> ../docs/contracts/event-protocol-v1.schema.json` and review the diff"
)


def test_schema_matches_the_golden_file() -> None:
    assert GOLDEN.read_text(encoding="utf-8") == render(), REGENERATE


def test_schema_is_deterministic_and_well_formed() -> None:
    text = render()
    assert text == render()
    assert text.endswith("}\n")
    assert text.isascii()
    assert json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n" == text


def test_schema_covers_every_type_and_never_allows_null() -> None:
    schema = json_schema()
    core, extension = schema["properties"]["event_type"]["anyOf"]
    assert core["enum"] == sorted(PAYLOADS["1.0"])
    assert re.fullmatch(extension["pattern"].strip("^$"), "x-golden.checkpoint")  # C26
    refs = {rule["then"]["properties"]["payload"]["$ref"] for rule in schema["allOf"]}
    assert refs == {f"#/$defs/{m.__name__}" for m in PAYLOADS["1.0"].values()} | {"#/$defs/ExtensionPayload"}
    text = json.dumps(schema)
    assert '"null"' not in text
    assert '"default": null' not in text
    for model in PAYLOADS["1.0"].values():
        assert schema["$defs"][model.__name__]["additionalProperties"] is False


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_module_prints_the_schema(capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_module("observatory.events.schema", run_name="__main__")
    assert capsys.readouterr().out == render()


def test_null_branches_are_removed() -> None:
    assert _without_nulls({"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}) == {
        "type": "string"
    }
    two = {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]}
    assert _without_nulls(two) == {"anyOf": [{"type": "string"}, {"type": "integer"}]}


def _admits(constraint: dict[str, Any], value: str) -> bool:
    """A minimal reading of the schema's ``event_type`` constraint (no jsonschema dependency)."""
    if "anyOf" in constraint:
        return any(_admits(option, value) for option in constraint["anyOf"])
    if "enum" in constraint:
        return value in constraint["enum"]
    return re.search(constraint["pattern"], value) is not None


def test_schema_admits_every_valid_event_type() -> None:
    """R-B-P2-006-02: the top-level constraint must not exclude extension events (C26)."""
    constraint = json_schema()["properties"]["event_type"]
    golden_extension = GOLDEN_EVENTS["extension event"][0]["event_type"]
    assert _admits(constraint, golden_extension)
    for event_type in [*PAYLOADS["1.0"], "x-acme.build_step", "x-sessionco.thing"]:
        assert _admits(constraint, event_type), event_type
    for event_type in ("session.resumed", "x-Acme.thing", "acme.thing"):
        assert not _admits(constraint, event_type), event_type
