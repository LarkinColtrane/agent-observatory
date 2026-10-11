"""The TID251 exception is type-only (ADR-0005 §3, AO-P1-006).

Ruff bans importing ``observatory.core.config.Settings`` outside config.py so
that settings are only built through ``get_settings()`` (sanitized errors).
Ruff flags the import even under ``TYPE_CHECKING``, so modules that need the
type suppress it per line. This test keeps that suppression honest: every
``noqa: TID251`` must sit on an import inside an ``if TYPE_CHECKING:`` block,
which is never executed, so ``Settings()`` cannot be constructed at runtime.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = [ROOT / "backend/src", ROOT / "backend/migrations"]
NOQA = re.compile(r"#\s*noqa:[^#]*\bTID251\b")


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def violations(source: str) -> list[int]:
    """Line numbers carrying a TID251 noqa that is not a type-only import."""
    allowed: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for stmt in node.body:
                if isinstance(stmt, ast.Import | ast.ImportFrom):
                    allowed.update(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
    return [n for n, line in enumerate(source.splitlines(), 1) if NOQA.search(line) and n not in allowed]


class SettingsBanTests(unittest.TestCase):
    def test_repository_suppressions_are_type_only(self) -> None:
        bad = []
        for base in SCANNED:
            for path in sorted(base.rglob("*.py")) if base.is_dir() else []:
                bad += [f"{path.relative_to(ROOT)}:{n}" for n in violations(path.read_text(encoding="utf-8"))]
        self.assertEqual(bad, [], "TID251 may only be suppressed on imports under `if TYPE_CHECKING:`")

    def test_type_checking_import_is_allowed(self) -> None:
        src = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from observatory.core.config import Settings  # noqa: TID251 (type only)\n"
        )
        self.assertEqual(violations(src), [])

    def test_runtime_import_is_rejected(self) -> None:
        src = "from observatory.core.config import Settings  # noqa: TID251\n"
        self.assertEqual(violations(src), [1])

    def test_suppressed_construction_is_rejected(self) -> None:
        src = (
            "import typing\n"
            "if typing.TYPE_CHECKING:\n"
            "    from observatory.core.config import Settings  # noqa: TID251\n"
            "s = config.Settings()  # noqa: TID251\n"
        )
        self.assertEqual(violations(src), [4])

    def test_other_if_blocks_are_not_exempt(self) -> None:
        src = "if DEBUG:\n    from observatory.core.config import Settings  # noqa: E501,TID251\n"
        self.assertEqual(violations(src), [2])


if __name__ == "__main__":
    unittest.main()
