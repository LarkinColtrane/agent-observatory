"""observatory.events depends only on observatory.core, Pydantic and the stdlib (ADR-0008 §17; AC7)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import observatory.events

PACKAGE = Path(observatory.events.__file__).parent
ALLOWED_THIRD_PARTY = {"pydantic", "pydantic_core"}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_events_imports_only_core_pydantic_and_stdlib() -> None:
    modules = sorted(PACKAGE.glob("*.py"))
    assert {m.name for m in modules} >= {
        "__init__.py",
        "envelope.py",
        "codec.py",
        "validation.py",
        "ordering.py",
    }
    for path in modules:
        for name in _imports(path):
            top = name.split(".")[0]
            if top == "observatory":
                assert name.startswith(("observatory.core.", "observatory.events")), (path.name, name)
            else:
                assert top in sys.stdlib_module_names or top in ALLOWED_THIRD_PARTY, (path.name, name)


def test_public_api_matches_section_17() -> None:
    expected = {
        "SPEC_VERSION", "SUPPORTED_VERSIONS", "SECRET_RULES_VERSION", "SECRET_RULES",
        "Event", "Scope", "EventTime", "Source", "Adapter", "Causality", "ExtensionPayload",
        "parse_event", "validate_event", "load_recorded", "canonical_json", "fingerprint",
        "content_fingerprint", "derive_event_id", "sanitize_text", "canonical_order", "stream_key",
        "classify_duplicate", "RejectCode", "Disposition", "WarningCode", "DuplicateKind", "RecordedEvent",
        "Accepted", "Rejected",
    }  # fmt: skip
    assert expected <= set(observatory.events.__all__)
    assert observatory.events.SPEC_VERSION == "1.0"
    assert frozenset({"1.0"}) == observatory.events.SUPPORTED_VERSIONS
