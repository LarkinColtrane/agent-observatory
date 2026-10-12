"""Readiness recovers after pooled connections stall (AO-P1-006; review R-A-006-01, R-B-006-01).

Owner: AO-P1-006 (coordinator).
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import time

from pydantic import SecretStr

from observatory.core.health import run_checks
from observatory.db import create_engine, database_check, to_psycopg_url
from observatory.main import _SingleFlight
from tests.integration.conftest import make_settings

DEADLINE_S = 2.0


class StallingProxy:
    """TCP relay that can stall every connection open at that moment.

    Models a failover or silent partition: existing connections never deliver
    another byte, while connections opened afterwards work normally.
    """

    def __init__(self, host: str, port: int) -> None:
        self._target = (host, port)
        self._stalled: list[asyncio.Event] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._writers: list[asyncio.StreamWriter] = []
        self._server: asyncio.Server | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port: int = self._server.sockets[0].getsockname()[1]
        return port

    def stall_existing(self) -> None:
        for stalled in self._stalled:
            stalled.set()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        up_reader, up_writer = await asyncio.open_connection(*self._target)
        self._writers += [writer, up_writer]
        stalled = asyncio.Event()
        self._stalled.append(stalled)
        for src, dst in ((reader, up_writer), (up_reader, writer)):
            task = asyncio.ensure_future(self._pump(src, dst, stalled))
            self._tasks.add(task)

    @staticmethod
    async def _pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter, stalled: asyncio.Event) -> None:
        while data := await src.read(65536):
            if stalled.is_set():
                continue  # dropped: never forwarded, never delivered late
            dst.write(data)
            await dst.drain()

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        for writer in self._writers:
            writer.transport.abort()  # drop at once: stalled peers may never finish a close
        if self._server is not None:
            self._server.close()
            # Bounded so a failing run reports its assertion instead of hanging here.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), timeout=5)


async def test_readiness_recovers_after_pooled_connections_stall(app_database_url: str) -> None:
    real = to_psycopg_url(SecretStr(app_database_url), setting="AO_TEST_DATABASE_URL")
    proxy = StallingProxy(real.host or "127.0.0.1", real.port or 5432)
    port = await proxy.start()
    via_proxy = real.set(port=port, host="127.0.0.1").render_as_string(hide_password=False)
    engine = create_engine(make_settings(database_url=via_proxy))
    flight = _SingleFlight(database_check(engine), timeout_s=DEADLINE_S, on_failure=engine.dispose)

    async def ready() -> bool:
        (result,) = await run_checks([flight], timeout_s=DEADLINE_S)
        return result.ok

    async def hold() -> None:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
            await asyncio.sleep(0.2)

    try:
        await asyncio.gather(*(hold() for _ in range(5)))  # several idle pooled connections
        assert engine.pool.checkedin() >= 3
        assert await ready()
        proxy.stall_existing()  # every pooled connection is now dead; new ones work
        assert not await ready()
        # One failed probe resets the pool, so the next probe connects afresh.
        # Without the reset, each stalled pooled connection fails another probe.
        start = time.monotonic()
        assert await ready(), "readiness did not recover on the probe after the failure"
        assert time.monotonic() - start < DEADLINE_S + 1.0
    finally:
        await flight.aclose()
        await engine.dispose()
        await proxy.close()
        gc.collect()
