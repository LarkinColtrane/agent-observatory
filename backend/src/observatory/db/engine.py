"""SQLAlchemy async engine and database readiness check (ADR-0005 §3).

The application connects with ``AO_DATABASE_URL`` (DML-only role); Alembic
uses ``AO_MIGRATION_DATABASE_URL`` (DDL role). URLs are read with
``get_secret_value()`` only here, at the point of use, and never logged or
placed in exception messages. Nothing is created at import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from observatory.core.config import ConfigurationError
from observatory.core.health import HealthCheck, make_check

if TYPE_CHECKING:
    from pydantic import SecretStr

    from observatory.core.config import Settings  # noqa: TID251 (type only)

DRIVERNAME = "postgresql+psycopg"
_ACCEPTED_DRIVERNAMES = frozenset({"postgresql", DRIVERNAME})
CONNECT_TIMEOUT_S = 1


def to_psycopg_url(value: SecretStr | None, *, setting: str) -> URL:
    """Parse a secret database URL and normalise it to the psycopg 3 driver.

    ``setting`` is the environment variable name, used in error messages; the
    URL itself never is. Raises ``ConfigurationError`` if unset, unparsable,
    not a PostgreSQL URL, or if the parsed host contains ``@`` (an unencoded
    ``@`` in the password would otherwise leave part of the password in the
    host, which drivers and logs print). The returned ``URL`` masks its
    password when rendered with ``str()``/``repr()``.
    """
    if value is None:
        raise ConfigurationError(f"{setting} is not set")
    problem: str | None = None
    url: URL | None = None
    try:
        url = make_url(value.get_secret_value())
    except Exception:  # parse errors may embed the raw string: never chain them
        problem = f"{setting} is not a valid database URL"
    if url is not None and url.drivername not in _ACCEPTED_DRIVERNAMES:
        problem = f"{setting} must use the postgresql or {DRIVERNAME} scheme"
    elif url is not None and ("@" in (url.host or "") or "@" in (url.username or "")):
        problem = f"{setting}: password must be percent-encoded"
    if problem is not None or url is None:
        # Raised outside the except block: no __context__ reference to the original error.
        raise ConfigurationError(problem or f"{setting} is not a valid database URL")
    return url.set(drivername=DRIVERNAME)


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the application's ``AsyncEngine`` from ``settings.database_url``.

    Does not connect; connections are opened lazily. The caller owns the
    engine and must ``await engine.dispose()`` on shutdown. SQL echo is off and
    bound parameters are hidden from SQLAlchemy log and error text.

    ``connect_timeout=1`` is passed to psycopg, but libpq (and psycopg's async
    connect, which mirrors it) raises any value below 2 to 2 seconds, so the
    effective connect timeout is 2s. ``core.health.run_checks`` enforces the
    readiness deadline independently of it.
    """
    url = to_psycopg_url(settings.database_url, setting="AO_DATABASE_URL")
    return create_async_engine(
        url,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
        pool_pre_ping=True,
        # echo/echo_pool install SQLAlchemy's own stdout handler, which bypasses log
        # redaction and prints bound parameters: never enable them (review R-A-002-07).
        echo=False,
        echo_pool=False,
        hide_parameters=True,
    )


def database_check(engine: AsyncEngine) -> HealthCheck:
    """Readiness check named ``database``: ``SELECT 1`` on a pooled connection.

    Time-boxing and fail-closed semantics come from ``core.health.run_checks``.
    """

    async def probe() -> None:
        async with engine.connect() as conn:
            value: object = (await conn.execute(text("SELECT 1"))).scalar_one()
        if value != 1:
            raise RuntimeError("unexpected SELECT 1 result")

    return make_check("database", probe)
