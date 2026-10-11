"""Readiness checks fail closed, within the deadline, without leaking (no services needed)."""

from __future__ import annotations

import asyncio
import gc
import logging
import time

import pytest

from observatory.cache import create_redis, redis_check
from observatory.cache.client import MAX_CONNECTIONS
from observatory.core.health import CheckResult, run_checks
from observatory.db import create_engine, database_check

from .conftest import creds_url, make_settings

DEADLINE_S = 2.0
# run_checks gives cancelled checks a short grace period; allow generous
# scheduling slack on loaded CI runners (review R-B-004-07).
MAX_ELAPSED_S = DEADLINE_S + 1.0
PW = "Synthetic" + "Pw" + "9q7z"  # assembled at runtime: no credential-looking literal


def _db_url(host: str, port: int) -> str:
    return creds_url("postgresql+psycopg", "ao_app", PW, f"{host}:{port}/observatory")


def _redis_url(host: str, port: int) -> str:
    return creds_url("redis", "default", PW, f"{host}:{port}/0")


async def _assert_db_fails_closed(url: str, caplog: pytest.LogCaptureFixture) -> None:
    engine = create_engine(make_settings(database_url=url))
    try:
        with caplog.at_level(logging.DEBUG):
            start = time.monotonic()
            results = await run_checks([database_check(engine)], timeout_s=DEADLINE_S)
            elapsed = time.monotonic() - start
    finally:
        await engine.dispose()
        gc.collect()
    assert results == [CheckResult(name="database", ok=False)]
    assert elapsed < MAX_ELAPSED_S
    assert PW not in caplog.text


async def _assert_redis_fails_closed(url: str, caplog: pytest.LogCaptureFixture) -> None:
    client = create_redis(make_settings(redis_url=url))
    try:
        with caplog.at_level(logging.DEBUG):
            start = time.monotonic()
            results = await run_checks([redis_check(client)], timeout_s=DEADLINE_S)
            elapsed = time.monotonic() - start
    finally:
        await client.aclose()
        gc.collect()
    assert results == [CheckResult(name="redis", ok=False)]
    assert elapsed < MAX_ELAPSED_S
    assert PW not in caplog.text


async def test_database_check_closed_port(closed_port: int, caplog: pytest.LogCaptureFixture) -> None:
    await _assert_db_fails_closed(_db_url("127.0.0.1", closed_port), caplog)


async def test_database_check_unresolvable_host(caplog: pytest.LogCaptureFixture) -> None:
    await _assert_db_fails_closed(_db_url("db.invalid", 5432), caplog)


async def test_database_check_hung_server(blackhole_port: int, caplog: pytest.LogCaptureFixture) -> None:
    await _assert_db_fails_closed(_db_url("127.0.0.1", blackhole_port), caplog)


async def test_redis_check_closed_port(closed_port: int, caplog: pytest.LogCaptureFixture) -> None:
    await _assert_redis_fails_closed(_redis_url("127.0.0.1", closed_port), caplog)


async def test_redis_check_unresolvable_host(caplog: pytest.LogCaptureFixture) -> None:
    await _assert_redis_fails_closed(_redis_url("cache.invalid", 6379), caplog)


async def test_redis_check_hung_server(blackhole_port: int, caplog: pytest.LogCaptureFixture) -> None:
    await _assert_redis_fails_closed(_redis_url("127.0.0.1", blackhole_port), caplog)


async def test_redis_check_direct_call_bounded_by_socket_timeouts(blackhole_port: int) -> None:
    """Without run_checks, the client's own 1s timeouts (and no retries) still bound PING."""
    client = create_redis(make_settings(redis_url=_redis_url("127.0.0.1", blackhole_port)))
    try:
        start = time.monotonic()
        with pytest.raises(Exception):  # noqa: B017, PT011 - any redis error is a failure
            await redis_check(client)()
        assert time.monotonic() - start < MAX_ELAPSED_S
    finally:
        await client.aclose()
        gc.collect()


async def test_both_checks_together_fail_closed_in_input_order(closed_port: int) -> None:
    engine = create_engine(make_settings(database_url=_db_url("127.0.0.1", closed_port)))
    client = create_redis(make_settings(redis_url=_redis_url("127.0.0.1", closed_port)))
    try:
        results = await run_checks([database_check(engine), redis_check(client)], timeout_s=DEADLINE_S)
    finally:
        await engine.dispose()
        await client.aclose()
        gc.collect()
    assert results == [CheckResult("database", ok=False), CheckResult("redis", ok=False)]


async def test_redis_probe_burst_is_bounded_and_fails_closed(blackhole_port: int) -> None:
    """100 concurrent probes against a hung Redis: at most MAX_CONNECTIONS sockets, no hang."""
    client = create_redis(make_settings(redis_url=_redis_url("127.0.0.1", blackhole_port)))
    pool = client.connection_pool
    peak = 0
    make_connection = pool.make_connection

    def counting_make_connection():  # type: ignore[no-untyped-def]
        nonlocal peak
        conn = make_connection()
        peak = max(peak, len(pool._in_use_connections) + len(pool._available_connections) + 1)
        return conn

    pool.make_connection = counting_make_connection  # type: ignore[method-assign]
    try:
        start = time.monotonic()
        rounds = await asyncio.gather(
            *(run_checks([redis_check(client)] * 10, timeout_s=DEADLINE_S) for _ in range(10))
        )
        elapsed = time.monotonic() - start
    finally:
        await client.aclose()
        gc.collect()
    assert MAX_CONNECTIONS == 16
    assert peak == MAX_CONNECTIONS  # the cap was reached and never exceeded
    assert [r for results in rounds for r in results] == [CheckResult("redis", ok=False)] * 100
    assert elapsed < MAX_ELAPSED_S
