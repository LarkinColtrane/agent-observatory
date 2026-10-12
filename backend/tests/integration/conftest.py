"""Integration-test fixtures (ADR-0005 §3; owner W3).

Service URLs come from the environment:
  AO_TEST_DATABASE_URL            application (DML-only) role
  AO_TEST_MIGRATION_DATABASE_URL  migration (DDL/owner) role, same database
  AO_TEST_REDIS_URL
Unset → the test is skipped locally; with AO_REQUIRE_INTEGRATION=1 (CI) an
unset URL is a failure, so CI can never pass by silently skipping.

Every test collected from this directory carries ``@pytest.mark.integration``.
Tests that need no services (failure modes, URL handling) run everywhere.
"""

from __future__ import annotations

import asyncio
import gc
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import Engine, create_engine, pool
from sqlalchemy.ext.asyncio import AsyncEngine

from observatory.cache import create_redis
from observatory.core.config import Settings
from observatory.db import create_engine as create_app_engine
from observatory.db import to_psycopg_url

REQUIRE_FLAG = "AO_REQUIRE_INTEGRATION"
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
BOOTSTRAP_SCRIPT = REPO_ROOT / "deploy" / "postgres" / "init" / "10-ao-roles.sh"
POSTGRES_IMAGE = os.environ.get("AO_TEST_POSTGRES_IMAGE", "postgres:16.10-alpine")
_THIS_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if _THIS_DIR in Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.integration)


def service_url(name: str) -> str:
    """Return the URL in ``name``; skip if unset, or fail if AO_REQUIRE_INTEGRATION=1."""
    value = os.environ.get(name, "")
    if value:
        return value
    if os.environ.get(REQUIRE_FLAG) == "1":
        pytest.fail(f"{name} is not set but {REQUIRE_FLAG}=1", pytrace=False)
    pytest.skip(f"{name} is not set (set {REQUIRE_FLAG}=1 to make this a failure)")


def require_docker() -> str:
    """Return the docker CLI path if docker and the Postgres test image are usable.

    Skips locally otherwise; fails under AO_REQUIRE_INTEGRATION=1.
    """
    docker = shutil.which("docker")
    usable = docker is not None and (
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [docker, "image", "inspect", POSTGRES_IMAGE],
            capture_output=True,
            timeout=30,
            check=False,
        ).returncode
        == 0
    )
    if docker is not None and usable:
        return docker
    reason = f"docker with image {POSTGRES_IMAGE} is not available"
    if os.environ.get(REQUIRE_FLAG) == "1":
        pytest.fail(f"{reason} but {REQUIRE_FLAG}=1", pytrace=False)
    pytest.skip(reason)


def make_settings(**overrides: str) -> Settings:
    """Settings for tests, independent of the process environment's AO_* values."""
    values: dict[str, SecretStr | None] = dict.fromkeys(
        ("database_url", "migration_database_url", "redis_url"), None
    )
    values.update({k: SecretStr(v) for k, v in overrides.items()})
    return Settings(env="test", **values)


def creds_url(scheme: str, user: str, password: str, rest: str) -> str:
    """Build a credentialed URL at runtime.

    No source line then contains a credentialed-URL literal (governance secret backstop).
    """
    return f"{scheme}://{user}" + ":" + password + "@" + rest


def password_of(url: str) -> str | None:
    return to_psycopg_url(SecretStr(url), setting="url").password if "://" in url else None


def scrub(text: str, *urls: str) -> str:
    """Remove credentials from subprocess output before it can reach an assertion message."""
    for url in urls:
        for secret in (url, password_of(url)):
            if secret:
                text = text.replace(secret, "[REDACTED]")
    return text


def run_alembic(
    *args: str, migration_url: str | None, timeout: float = 60
) -> subprocess.CompletedProcess[str]:
    """Run the Alembic CLI exactly as CI/compose do, with a clean AO_* environment."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AO_")}
    env["AO_ENV"] = "test"
    if migration_url is not None:
        env["AO_MIGRATION_DATABASE_URL"] = migration_url
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if migration_url is not None:
        proc.stdout = scrub(proc.stdout, migration_url)
        proc.stderr = scrub(proc.stderr, migration_url)
    return proc


@pytest.fixture(scope="session")
def app_database_url() -> str:
    return service_url("AO_TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def migration_database_url() -> str:
    return service_url("AO_TEST_MIGRATION_DATABASE_URL")


@pytest.fixture(scope="session")
def redis_url() -> str:
    return service_url("AO_TEST_REDIS_URL")


@pytest.fixture
def migrator_engine(migration_database_url: str) -> Iterator[Engine]:
    """Synchronous engine as the migration (owner) role, for setup and inspection."""
    url = to_psycopg_url(SecretStr(migration_database_url), setting="AO_TEST_MIGRATION_DATABASE_URL")
    engine = create_engine(url, poolclass=pool.NullPool, connect_args={"connect_timeout": 5})
    try:
        yield engine
    finally:
        engine.dispose()
        gc.collect()


@pytest.fixture
def at_head(migration_database_url: str) -> None:
    proc = run_alembic("upgrade", "head", migration_url=migration_database_url)
    assert proc.returncode == 0, proc.stderr


@pytest.fixture
async def app_engine(app_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_app_engine(make_settings(database_url=app_database_url))
    try:
        yield engine
    finally:
        await engine.dispose()
        gc.collect()  # surface unclosed-resource warnings inside this test


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = create_redis(make_settings(redis_url=redis_url))
    try:
        yield client
    finally:
        await client.aclose()
        gc.collect()


@pytest.fixture
def closed_port() -> Iterator[int]:
    """A local TCP port that refuses connections.

    The socket stays bound (but never listens) for the whole test, so no other
    process can take the port meanwhile (review R-B-004-07).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        yield port


@pytest.fixture
async def blackhole_port() -> AsyncIterator[int]:
    """A TCP port that accepts connections and never answers (a hung server)."""
    writers: list[asyncio.StreamWriter] = []

    async def hold(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writers.append(writer)

    server = await asyncio.start_server(hold, "127.0.0.1", 0)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        for writer in writers:
            writer.close()
        server.close()
        await server.wait_closed()
        gc.collect()
