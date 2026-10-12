"""URL handling, secret hygiene and Alembic wiring (no services needed)."""

from __future__ import annotations

import gc
import logging

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr
from redis.asyncio import ConnectionPool

from observatory.cache import create_redis
from observatory.core.config import ConfigurationError
from observatory.db import create_engine, to_psycopg_url
from observatory.db.migration import MIGRATION_LOCK_KEY

from .conftest import BACKEND_DIR, creds_url, make_settings, run_alembic

PW = "Synthetic" + "Pw" + "4k2x"
DB_URL = creds_url("postgresql", "ao_app", PW, "db.invalid:5432/observatory")


def _assert_sanitized(err: BaseException, *secrets: str) -> None:
    assert err.__cause__ is None
    assert err.__context__ is None
    for rendered in (str(err), repr(err), repr(err.args)):
        for secret in secrets:
            assert secret not in rendered


async def test_engine_uses_psycopg_and_masks_password() -> None:
    engine = create_engine(make_settings(database_url=DB_URL))
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.password == PW
        for rendered in (repr(engine), str(engine.url), repr(engine.url), repr(engine.pool)):
            assert PW not in rendered
    finally:
        await engine.dispose()
        gc.collect()


async def test_engine_never_echoes_sql_or_parameters() -> None:
    """Review R-A-002-07: echo bypasses log redaction; parameters must be hidden."""
    loggers = [logging.getLogger(n) for n in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool")]
    before = [list(lg.handlers) for lg in loggers]
    engine = create_engine(make_settings(database_url=DB_URL))
    try:
        assert engine.echo is False
        assert engine.sync_engine.pool.echo is False
        assert engine.sync_engine.hide_parameters is True
        assert [list(lg.handlers) for lg in loggers] == before == [[], [], []]
    finally:
        await engine.dispose()
        gc.collect()


def test_psycopg_scheme_is_kept() -> None:
    url = to_psycopg_url(SecretStr(DB_URL.replace("postgresql://", "postgresql+psycopg://")), setting="X")
    assert url.drivername == "postgresql+psycopg"


def test_engine_requires_database_url() -> None:
    with pytest.raises(ConfigurationError, match="AO_DATABASE_URL is not set"):
        create_engine(make_settings())


@pytest.mark.parametrize(
    "bad",
    [
        creds_url("mysql", "ao_app", PW, "db.invalid/observatory"),
        creds_url("postgresql+asyncpg", "ao_app", PW, "db.invalid/observatory"),
        creds_url("postgresql", "ao_app", PW, "db.invalid:notaport/observatory"),
        f"not a url {PW}",
    ],
)
def test_engine_rejects_bad_urls_without_echoing_them(bad: str) -> None:
    with pytest.raises(ConfigurationError, match="AO_DATABASE_URL") as excinfo:
        create_engine(make_settings(database_url=bad))
    _assert_sanitized(excinfo.value, PW, bad)


def test_unencoded_at_in_username_is_rejected() -> None:
    """Review R-A-004-202: a forgotten ':' must not move a password fragment into the username."""
    raw = "postgresql://" + "ao_app@" + PW + "@db.invalid:5432/observatory"
    with pytest.raises(
        ConfigurationError, match="AO_DATABASE_URL: password must be percent-encoded"
    ) as excinfo:
        create_engine(make_settings(database_url=raw))
    _assert_sanitized(excinfo.value, PW, raw)


def test_unencoded_at_in_password_is_rejected() -> None:
    """Review R-A-004-02: an unencoded '@' would put the password tail into the host."""
    raw = creds_url("postgresql", "ao_app", PW + "@tail", "db.invalid:5432/observatory")
    with pytest.raises(
        ConfigurationError, match="AO_DATABASE_URL: password must be percent-encoded"
    ) as excinfo:
        create_engine(make_settings(database_url=raw))
    _assert_sanitized(excinfo.value, PW, "tail", raw)
    # Percent-encoded is fine and decodes to the real password.
    encoded = creds_url("postgresql", "ao_app", PW + "%40tail", "db.invalid:5432/observatory")
    url = to_psycopg_url(SecretStr(encoded), setting="AO_DATABASE_URL")
    assert (url.password, url.host) == (PW + "@tail", "db.invalid")


async def test_redis_client_masks_password() -> None:
    client = create_redis(make_settings(redis_url=creds_url("redis", "default", PW, "cache.invalid:6379/0")))
    try:
        kwargs = client.connection_pool.connection_kwargs
        assert (kwargs["socket_timeout"], kwargs["socket_connect_timeout"]) == (1, 1)
        assert type(client.connection_pool) is ConnectionPool  # non-blocking: excess fails at once
        assert client.connection_pool.max_connections == 16
        assert client.auto_close_connection_pool is True  # aclose() also closes the pool
        for rendered in (repr(client), repr(client.connection_pool), str(client)):
            assert PW not in rendered
    finally:
        await client.aclose()
        gc.collect()


def test_redis_requires_url() -> None:
    with pytest.raises(ConfigurationError, match="AO_REDIS_URL is not set"):
        create_redis(make_settings())


@pytest.mark.parametrize(
    "bad",
    [creds_url("http", "default", PW, "cache.invalid/0"), creds_url("redis", "default", PW, "h:notaport/0")],
)
def test_redis_rejects_bad_urls_without_echoing_them(bad: str) -> None:
    with pytest.raises(ConfigurationError, match="AO_REDIS_URL") as excinfo:
        create_redis(make_settings(redis_url=bad))
    _assert_sanitized(excinfo.value, PW, bad)


def test_exactly_one_head_named_baseline() -> None:
    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    assert script.get_heads() == ["0001_baseline"]
    assert [rev.revision for rev in script.walk_revisions()] == ["0001_baseline"]


def test_alembic_heads_cli_reports_one_head() -> None:
    proc = run_alembic("heads", migration_url=None)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split("\n")[:-1] == ["0001_baseline (head)"]


def test_alembic_refuses_to_run_without_migration_url() -> None:
    proc = run_alembic("upgrade", "head", "--sql", migration_url=None)
    assert proc.returncode != 0
    assert "AO_MIGRATION_DATABASE_URL is not set" in proc.stderr


def test_alembic_offline_sql_is_locked_and_secret_free() -> None:
    url = creds_url("postgresql", "ao_migrator", PW, "db.invalid:5432/observatory")
    proc = run_alembic("upgrade", "head", "--sql", migration_url=url)
    assert proc.returncode == 0, proc.stderr
    sql = proc.stdout
    assert sql.index("SET LOCAL lock_timeout = '60s'") < sql.index("pg_advisory_xact_lock")
    assert f"pg_advisory_xact_lock({MIGRATION_LOCK_KEY})" in sql
    assert sql.index("pg_advisory_xact_lock") < sql.index("CREATE SCHEMA IF NOT EXISTS alembic")
    assert "CREATE TABLE alembic.alembic_version" in sql
    assert "INSERT INTO alembic.alembic_version (version_num) VALUES ('0001_baseline')" in sql
    assert PW not in proc.stdout + proc.stderr


@pytest.mark.parametrize("bad", ["1s; DROP TABLE x", "0s", "forever", "1 s"])
def test_alembic_rejects_malformed_lock_timeout(bad: str) -> None:
    url = creds_url("postgresql", "ao_migrator", PW, "db.invalid:5432/observatory")
    proc = run_alembic("-x", f"lock_timeout={bad}", "upgrade", "head", "--sql", migration_url=url)
    assert proc.returncode != 0
    assert "lock_timeout must look like" in proc.stderr
