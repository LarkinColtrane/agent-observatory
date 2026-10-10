"""Health-check primitives (ADR-0005 §3): concurrent, time-boxed, fail closed."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from observatory.core.health import CheckResult, make_check, run_checks


async def _ok() -> None:
    return None


async def _boom() -> None:
    raise RuntimeError("secret detail must not be returned")


async def _hang() -> None:
    await asyncio.sleep(3600)


async def test_all_ok_preserves_order() -> None:
    checks = [make_check("database", _ok), make_check("redis", _ok)]
    assert await run_checks(checks) == [CheckResult("database", True), CheckResult("redis", True)]


async def test_exception_fails_closed_with_name_and_no_detail(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    results = await run_checks([make_check("database", _boom), make_check("redis", _ok)])
    assert results == [CheckResult("database", False), CheckResult("redis", True)]
    assert all(not hasattr(r, "detail") for r in results)
    assert "raised" in caplog.text  # detail goes to logs, not to the result


async def test_timeout_fails_closed_and_runs_concurrently() -> None:
    started = time.monotonic()
    results = await run_checks(
        [make_check("slow-a", _hang), make_check("slow-b", _hang), make_check("ok", _ok)], timeout_s=0.2
    )
    elapsed = time.monotonic() - started
    assert results == [CheckResult("slow-a", False), CheckResult("slow-b", False), CheckResult("ok", True)]
    assert elapsed < 1.0  # one overall deadline, not one per check


async def test_unnamed_check_gets_positional_name() -> None:
    async def bare() -> CheckResult:
        raise ValueError("x")

    assert await run_checks([bare]) == [CheckResult("check-0", False)]


async def test_check_returning_result_is_passed_through() -> None:
    async def custom() -> CheckResult:
        return CheckResult("custom", False)

    assert await run_checks([custom]) == [CheckResult("custom", False)]


async def test_empty_and_invalid_timeout() -> None:
    assert await run_checks([]) == []
    with pytest.raises(ValueError, match="positive"):
        await run_checks([make_check("x", _ok)], timeout_s=0)


async def test_cancellation_propagates_and_cancels_checks() -> None:
    cancelled = asyncio.Event()

    async def watched() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.ensure_future(run_checks([make_check("w", watched)], timeout_s=30))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


class _Fatal(BaseException):
    """A non-Exception BaseException (asyncio handles KeyboardInterrupt/SystemExit specially)."""


async def test_base_exception_is_not_swallowed() -> None:
    async def fatal() -> None:
        raise _Fatal

    with pytest.raises(_Fatal):
        await run_checks([make_check("k", fatal)])


async def test_check_ignoring_cancellation_cannot_hang_readiness() -> None:
    release = asyncio.Event()

    async def stubborn() -> None:
        while not release.is_set():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                continue  # misbehaving probe: swallows cancellation

    started = time.monotonic()
    results = await run_checks([make_check("stubborn", stubborn)], timeout_s=0.2)
    assert results == [CheckResult("stubborn", False)]
    assert time.monotonic() - started < 1.0
    release.set()  # let the abandoned task finish so the loop closes cleanly
    await asyncio.sleep(0)


def test_make_check_requires_name() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        make_check("", _ok)
