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
FILE_NOQA = re.compile(r"#\s*ruff\s*:\s*noqa", re.IGNORECASE)
CONFIG = ROOT / "backend/src/observatory/core/config.py"


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def violations(source: str, *, is_config: bool = False) -> list[int]:
    """Line numbers that break the ban, whatever noqa comments are present.

    - a ``noqa: TID251`` that is not on an import inside ``if TYPE_CHECKING:``;
    - any file-level ``# ruff: noqa`` directive (it would silence TID251 too);
    - any runtime ``Settings(...)`` call outside config.py (review R-B-006-02).
    """
    tree = ast.parse(source)
    allowed: set[int] = set()
    calls: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for stmt in node.body:
                if isinstance(stmt, ast.Import | ast.ImportFrom):
                    allowed.update(range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1))
        if isinstance(node, ast.Call) and not is_config:
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name == "Settings":
                calls.add(node.lineno)
    bad = {n for n, line in enumerate(source.splitlines(), 1) if NOQA.search(line) and n not in allowed}
    bad |= {n for n, line in enumerate(source.splitlines(), 1) if FILE_NOQA.search(line)}
    return sorted(bad | calls)


class SettingsBanTests(unittest.TestCase):
    def test_repository_suppressions_are_type_only(self) -> None:
        bad = []
        for base in SCANNED:
            for path in sorted(base.rglob("*.py")) if base.is_dir() else []:
                source = path.read_text(encoding="utf-8")
                bad += [f"{path.relative_to(ROOT)}:{n}" for n in violations(source, is_config=path == CONFIG)]
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

    def test_runtime_construction_is_rejected_even_with_blanket_noqa(self) -> None:
        src = "from observatory.core import config\nS = config.Settings()  # noqa\nT = Settings()\n"
        self.assertEqual(violations(src), [2, 3])

    def test_file_level_ruff_noqa_is_rejected(self) -> None:
        src = "# ruff: noqa: TID251\nfrom observatory.core.config import Settings\n"
        self.assertEqual(violations(src), [1])

    def test_config_module_may_construct_settings(self) -> None:
        self.assertEqual(violations("S = Settings()\n", is_config=True), [])

    def test_other_if_blocks_are_not_exempt(self) -> None:
        src = "if DEBUG:\n    from observatory.core.config import Settings  # noqa: E501,TID251\n"
        self.assertEqual(violations(src), [2])


if __name__ == "__main__":
    unittest.main()
