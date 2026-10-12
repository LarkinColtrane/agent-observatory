"""Baseline: empty schema (ADR-0005 §3; no product tables in Phase 1).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-10
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Intentionally empty: later phases add revisions on top of this baseline."""


def downgrade() -> None:
    """Intentionally empty."""
