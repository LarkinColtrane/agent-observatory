"""Alembic environment (ADR-0005 §3).

The URL comes only from ``AO_MIGRATION_DATABASE_URL`` (DDL/owner role) via
``get_settings()`` — never from ``alembic.ini`` and never from the
application's DML-only ``AO_DATABASE_URL``. Migrations use the synchronous
psycopg 3 driver.

Safety properties:
- Runs in a single transaction (PostgreSQL has transactional DDL), so a
  failed upgrade leaves no partial schema.
- A transaction-scoped advisory lock serialises concurrent migrators (e.g. two
  ``migrate`` containers starting at once): the second waits, then sees the
  already-applied revision and does nothing.
- ``SET LOCAL lock_timeout`` (default 60s, ``-x lock_timeout=<value>`` to
  override) bounds every lock wait in the migration transaction, including the
  advisory lock: a migrator stuck behind another one fails with
  "canceling statement due to lock timeout" instead of waiting forever.
- The version table lives in its own ``alembic`` schema. Default privileges
  for the application role cover schema ``public`` only, so the app role can
  neither read nor rewrite migration state.
"""

from __future__ import annotations

import re

from alembic import context
from sqlalchemy import create_engine, pool

from observatory.core.config import get_settings
from observatory.core.logging import configure_logging
from observatory.db import to_psycopg_url
from observatory.db.migration import DEFAULT_LOCK_TIMEOUT, MIGRATION_LOCK_KEY, VERSION_TABLE_SCHEMA

CONNECT_TIMEOUT_S = 5
_LOCK_TIMEOUT_RE = re.compile(r"[1-9][0-9]{0,6}(ms|s|min)")

config = context.config

# Alembic and SQLAlchemy records go through the application's redacting handler
# (review R-A-004-11), not a plain logging.config handler from alembic.ini.
if config.attributes.get("configure_logging", True):
    configure_logging(get_settings())

if config.get_main_option("sqlalchemy.url"):
    raise RuntimeError("sqlalchemy.url must not be set in alembic.ini; use AO_MIGRATION_DATABASE_URL")

# No product tables in Phase 1 (ADR-0003); later phases set this to their MetaData.
target_metadata = None


def _lock_timeout() -> str:
    value = context.get_x_argument(as_dictionary=True).get("lock_timeout", DEFAULT_LOCK_TIMEOUT)
    if not _LOCK_TIMEOUT_RE.fullmatch(value):
        raise ValueError("lock_timeout must look like 500ms, 30s or 2min")
    return value


def _migrate() -> None:
    # Validated above against a strict pattern, so the literal is safe to inline.
    context.execute(f"SET LOCAL lock_timeout = '{_lock_timeout()}'")
    context.execute(f"SELECT pg_advisory_xact_lock({MIGRATION_LOCK_KEY})")
    context.execute(f"CREATE SCHEMA IF NOT EXISTS {VERSION_TABLE_SCHEMA}")
    context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout (``alembic upgrade head --sql``) without connecting."""
    url = to_psycopg_url(get_settings().migration_database_url, setting="AO_MIGRATION_DATABASE_URL")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=VERSION_TABLE_SCHEMA,
    )
    with context.begin_transaction():
        _migrate()


def run_migrations_online() -> None:
    url = to_psycopg_url(get_settings().migration_database_url, setting="AO_MIGRATION_DATABASE_URL")
    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                version_table_schema=VERSION_TABLE_SCHEMA,
                transaction_per_migration=False,
            )
            with context.begin_transaction():
                _migrate()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
