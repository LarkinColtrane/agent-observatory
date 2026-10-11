"""Database role separation: the application role is DML-only (ADR-0005 §3)."""

from __future__ import annotations

import gc
import secrets
from collections.abc import Iterator

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from observatory.db import create_engine, to_psycopg_url

from .conftest import make_settings

INSUFFICIENT_PRIVILEGE = "42501"


async def _denied(engine: AsyncEngine, sql: str) -> None:
    async with engine.connect() as conn:
        with pytest.raises(DBAPIError) as excinfo:
            await conn.execute(text(sql))
    assert getattr(excinfo.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, sql


@pytest.fixture
def probe_table(migrator_engine: Engine, at_head: None) -> Iterator[str]:
    """A table created by the migration role, as a future migration would."""
    name = f"ao_it_probe_{secrets.token_hex(4)}"
    with migrator_engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE public.{name} (id bigserial PRIMARY KEY, v text NOT NULL)"))
    try:
        yield name
    finally:
        with migrator_engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS public.{name}"))


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE ao_it_forbidden (id int)",
        "CREATE TABLE public.ao_it_forbidden (id int)",
        "CREATE SCHEMA ao_it_forbidden",
        "CREATE TEMP TABLE ao_it_forbidden (id int)",
        "CREATE VIEW ao_it_forbidden AS SELECT 1",
        "CREATE FUNCTION ao_it_forbidden() RETURNS int LANGUAGE sql AS 'SELECT 1'",
        "SET ROLE ao_migrator",
        "SELECT lo_create(0)",
        "SELECT lo_creat(-1)",
        "SELECT lo_from_bytea(0, '\\x00'::bytea)",
    ],
)
async def test_app_role_cannot_create_objects(app_engine: AsyncEngine, ddl: str) -> None:
    await _denied(app_engine, ddl)


async def test_app_role_has_no_elevated_attributes_or_ownership(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        attrs = (
            await conn.execute(
                text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        owned = (
            await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM pg_class WHERE relowner = r.oid)"
                    " + (SELECT count(*) FROM pg_namespace WHERE nspowner = r.oid)"
                    " + (SELECT count(*) FROM pg_database WHERE datdba = r.oid)"
                    " + (SELECT count(*) FROM pg_proc WHERE proowner = r.oid)"
                    " + (SELECT count(*) FROM pg_largeobject_metadata WHERE lomowner = r.oid) "
                    "FROM pg_roles r WHERE r.rolname = current_user"
                )
            )
        ).scalar_one()
        public_create = (
            await conn.execute(text("SELECT has_schema_privilege('public', 'CREATE')"))
        ).scalar_one()
    assert tuple(attrs) == (False, False, False, False, False)
    assert owned == 0
    assert public_create is False


async def test_app_role_cannot_touch_migration_state(app_engine: AsyncEngine, at_head: None) -> None:
    await _denied(app_engine, "SELECT version_num FROM alembic.alembic_version")
    await _denied(app_engine, "UPDATE alembic.alembic_version SET version_num = 'x'")


async def test_app_role_has_dml_on_migrator_tables(app_engine: AsyncEngine, probe_table: str) -> None:
    """Default privileges make future migrator-created tables usable (DML) by the app role."""
    # probe_table is a fixture-generated identifier, never external input.
    insert = text(f"INSERT INTO {probe_table} (v) VALUES ('a') RETURNING id")  # noqa: S608
    update = text(f"UPDATE {probe_table} SET v = 'b' WHERE id = :id")  # noqa: S608
    select = text(f"SELECT v FROM {probe_table}")  # noqa: S608
    delete = text(f"DELETE FROM {probe_table} WHERE id = :id")  # noqa: S608
    async with app_engine.begin() as conn:
        new_id = (await conn.execute(insert)).scalar_one()
        await conn.execute(update, {"id": new_id})
        assert (await conn.execute(select)).scalar_one() == "b"
        await conn.execute(delete, {"id": new_id})
    for ddl in (
        f"DROP TABLE {probe_table}",
        f"ALTER TABLE {probe_table} ADD COLUMN extra int",
        f"TRUNCATE {probe_table}",
        f"CREATE INDEX ON {probe_table} (v)",
        f"ALTER TABLE {probe_table} OWNER TO CURRENT_USER",
    ):
        await _denied(app_engine, ddl)


async def test_app_role_is_member_of_no_role(app_engine: AsyncEngine) -> None:
    """Review R-A-004-04: no inherited or SET ROLE path to the migrator (or any role)."""
    async with app_engine.connect() as conn:
        memberships = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member "
                    "WHERE r.rolname = current_user"
                )
            )
        ).scalar_one()
        can_become_migrator = (
            await conn.execute(text("SELECT pg_has_role(current_user, 'ao_migrator', 'MEMBER')"))
        ).scalar_one()
    assert memberships == 0
    assert can_become_migrator is False


@pytest.mark.parametrize("database", ["postgres", "template1"])
async def test_app_role_cannot_connect_to_maintenance_databases(app_database_url: str, database: str) -> None:
    """Review R-A-004-05: PUBLIC has no CONNECT on postgres/template1."""
    url = to_psycopg_url(SecretStr(app_database_url), setting="AO_TEST_DATABASE_URL").set(database=database)
    engine = create_engine(make_settings(database_url=url.render_as_string(hide_password=False)))
    try:
        with pytest.raises(DBAPIError, match=f'permission denied for database "{database}"'):
            async with engine.connect():
                pass
    finally:
        await engine.dispose()
        gc.collect()
