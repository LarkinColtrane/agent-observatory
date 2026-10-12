r"""Golden test for the informative JSON Schema (ADR-0008 §17; AO-P2-004 AC3).

If this fails after an intended model change, regenerate the checked-in copy from the repository root
and review the diff::

    cd backend && .venv/bin/python -m observatory.events.schema \
        > ../docs/contracts/event-protocol-v1.schema.json
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from observatory.events.schema import _without_nulls, json_schema, render
from observatory.events.taxonomy import PAYLOADS

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
    assert schema["properties"]["event_type"]["enum"] == sorted(PAYLOADS["1.0"])
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
