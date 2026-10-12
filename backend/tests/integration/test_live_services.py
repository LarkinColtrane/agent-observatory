"""Readiness checks against real PostgreSQL and Redis."""

from __future__ import annotations

import asyncio
import gc
import time

from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from observatory.cache import redis_check
from observatory.cache.client import MAX_CONNECTIONS
from observatory.core.health import CheckResult, run_checks
from observatory.db import create_engine, database_check, to_psycopg_url

from .conftest import make_settings

DEADLINE_S = 2.0
PSYCOPG_CANCEL_BOUND_S = 5.0 + 5.0 + 2.0  # cancel request + wait for server + slack


async def test_database_check_ok(app_engine: AsyncEngine) -> None:
    check = database_check(app_engine)
    assert await check() == CheckResult(name="database", ok=True)
    assert await run_checks([check]) == [CheckResult(name="database", ok=True)]


async def test_engine_connects_as_app_role_with_psycopg(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        row = (await conn.execute(text("SELECT current_user, version()"))).one()
    assert row[0] == "ao_app"
    assert row[1].startswith("PostgreSQL 16.")
    assert app_engine.dialect.driver == "psycopg"


async def test_redis_check_ok(redis_client: Redis) -> None:
    check = redis_check(redis_client)
    assert await check() == CheckResult(name="redis", ok=True)
    assert await run_checks([check]) == [CheckResult(name="redis", ok=True)]


async def test_concurrent_checks_share_pools_safely(app_engine: AsyncEngine, redis_client: Redis) -> None:
    """Overlapping readiness probes within the Redis pool cap (15 <= 16) all succeed."""
    checks = [database_check(app_engine), redis_check(redis_client)] * 3
    rounds = await asyncio.gather(*(run_checks(checks) for _ in range(5)))
    for results in rounds:
        assert [r.name for r in results] == ["database", "redis"] * 3
        assert all(r.ok for r in results)


class FreezableProxy:
    """TCP relay to a real server that can stop forwarding (a stalled network path).

    Once frozen, any connection that tries to relay data hangs forever; data is
    dropped, never delivered late. Connections opened after ``thaw()`` relay normally.
    """

    def __init__(self, host: str, port: int) -> None:
        self._target = (host, port)
        self._frozen = False
        self._never = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()
        self._writers: list[asyncio.StreamWriter] = []
        self._server: asyncio.Server | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port: int = self._server.sockets[0].getsockname()[1]
        return port

    def freeze(self) -> None:
        self._frozen = True

    def thaw(self) -> None:
        self._frozen = False

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        up_reader, up_writer = await asyncio.open_connection(*self._target)
        self._writers += [writer, up_writer]
        frozen_at_open = self._frozen
        for src, dst in ((reader, up_writer), (up_reader, writer)):
            task = asyncio.ensure_future(self._pump(src, dst, frozen_at_open))
            self._tasks.add(task)

    async def _pump(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter, frozen_at_open: bool) -> None:
        stalled = False
        while data := await src.read(65536):
            # A connection stalls for good once it relays while frozen.
            stalled = stalled or self._frozen or frozen_at_open
            if stalled:
                continue  # drop: never forwarded, never delivered late
            dst.write(data)
            await dst.drain()

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for writer in self._writers:
            writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


async def test_in_flight_probe_cancelled_at_deadline_releases_its_connection(app_database_url: str) -> None:
    """Review R-B-004-03: cancel a probe that is blocked on the network, not before I/O."""
    real = to_psycopg_url(SecretStr(app_database_url), setting="AO_TEST_DATABASE_URL")
    proxy = FreezableProxy(real.host or "127.0.0.1", real.port or 5432)
    port = await proxy.start()
    via_proxy = real.set(port=port, host="127.0.0.1").render_as_string(hide_password=False)
    engine = create_engine(make_settings(database_url=via_proxy))
    try:
        assert await run_checks([database_check(engine)]) == [CheckResult("database", ok=True)]
        proxy.freeze()  # the pooled connection's next round trip never completes
        start = time.monotonic()
        results = await run_checks([database_check(engine)], timeout_s=DEADLINE_S)
        assert results == [CheckResult("database", ok=False)]
        assert time.monotonic() - start < DEADLINE_S + 1.0
        # psycopg handles a cancelled query by sending a cancel request (up to 5s)
        # and waiting for the server (up to 5s), then closing the connection; the
        # abandoned probe task returns its connection within that fixed bound.
        released_by = time.monotonic() + PSYCOPG_CANCEL_BOUND_S
        while engine.pool.checkedout() and time.monotonic() < released_by:  # noqa: ASYNC110 - polls a sync counter
            await asyncio.sleep(0.1)
        assert engine.pool.checkedout() == 0
        proxy.thaw()
        assert await run_checks([database_check(engine)]) == [CheckResult("database", ok=True)]
    finally:
        await engine.dispose()
        await proxy.close()
        gc.collect()


async def test_redis_probe_burst_never_exceeds_pool_cap(redis_client: Redis) -> None:
    """Review R-B-004-02: 100 concurrent probes open at most MAX_CONNECTIONS sockets."""
    pool = redis_client.connection_pool
    peak = 0
    make_connection = pool.make_connection

    def counting_make_connection():  # type: ignore[no-untyped-def]
        nonlocal peak
        conn = make_connection()
        peak = max(peak, len(pool._in_use_connections) + len(pool._available_connections) + 1)
        return conn

    pool.make_connection = counting_make_connection  # type: ignore[method-assign]
    start = time.monotonic()
    results = await run_checks([redis_check(redis_client)] * 100, timeout_s=DEADLINE_S)
    assert time.monotonic() - start < DEADLINE_S + 1.0
    assert 0 < peak <= MAX_CONNECTIONS
    assert [r.name for r in results] == ["redis"] * 100
    assert any(r.ok for r in results)
    # Probes beyond the cap fail closed at once (MaxConnectionsError), they never queue.
    assert len(pool._in_use_connections) + len(pool._available_connections) <= MAX_CONNECTIONS
