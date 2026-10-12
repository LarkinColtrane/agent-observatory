"""Constants shared by the Alembic environment and its tests (single definition)."""

from __future__ import annotations

# Alembic's version table lives in its own schema; the app role has no access to it.
VERSION_TABLE_SCHEMA = "alembic"
# Transaction-scoped advisory lock key that serialises concurrent migrators
# ("AOMIGR" in ASCII; visible in pg_locks as objid).
MIGRATION_LOCK_KEY = 0x414F_4D49_4752
# Default bound on waiting for any lock (including MIGRATION_LOCK_KEY) during a
# migration; override per run with `alembic -x lock_timeout=<value> ...`.
DEFAULT_LOCK_TIMEOUT = "60s"
