"""Composition root (ADR-0005 §3). ASGI entry point: ``observatory.main:app``.

Only this module wires ``api`` to ``db``/``cache`` (import-linter enforces it).
Importing it has no side effects: ``app`` is built on first attribute access
(PEP 562), and the engine and Redis client live inside the lifespan, which
registers their readiness checks and disposes them on shutdown.

Readiness checks are single-flight (review R-B-004-201): at most one probe per
backing service is in flight, and concurrent ``/readyz`` callers share its
result. A burst of unauthenticated requests therefore cannot open more than one
database and one Redis connection for probing, and cannot exhaust the capped
Redis pool and report a healthy instance as not ready.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from functools import cache
from typing import TYPE_CHECKING

from fastapi import FastAPI

from observatory.api.app import READINESS_TIMEOUT_S, create_app
from observatory.cache import create_redis, redis_check
from observatory.core.config import get_settings
from observatory.core.health import CheckResult, HealthCheck
from observatory.core.logging import configure_logging
from observatory.db import create_engine, database_check

if TYPE_CHECKING:
    from observatory.core.config import Settings  # noqa: TID251 (type only)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

_log = logging.getLogger(__name__)
# Shutdown does not wait for a driver to give up a stalled connection.
_SHUTDOWN_GRACE_S = 0.1


class _SingleFlight:
    """Share one in-flight probe among concurrent callers of a health check.

    The shared probe is itself bounded by the readiness deadline: on timeout
    it is cancelled without waiting for the driver to give up the connection,
    so a stalled probe is never shared indefinitely (review R-B-006-01). A
    caller cancelled earlier does not cancel the probe for the others
    (``asyncio.shield``). The probe runs in a fresh context, so its log records
    do not carry the first caller's request id (R-B-006-03). ``aclose`` cancels
    a probe still running at shutdown.

    ``on_failure`` runs after a probe that failed or timed out (bounded by the
    same deadline). For the database it disposes the connection pool, so idle
    connections stalled on a dead path are dropped and the next probe connects
    afresh; without it, each stalled pooled connection would fail one probe
    after another (review R-A-006-01).
    """

    def __init__(
        self,
        check: HealthCheck,
        timeout_s: float = READINESS_TIMEOUT_S,
        on_failure: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._check = check
        self._timeout_s = timeout_s
        self._on_failure = on_failure
        self._inflight: asyncio.Task[CheckResult] | None = None
        self._probes: set[asyncio.Future[CheckResult]] = set()
        # run_checks names a failed check from this attribute (core.health).
        self.check_name: str | None = getattr(check, "check_name", None)

    async def __call__(self) -> CheckResult:
        if self._inflight is None or self._inflight.done():
            self._inflight = asyncio.get_running_loop().create_task(
                self._run(), context=contextvars.Context()
            )
            self._inflight.add_done_callback(_retrieve)
        return await asyncio.shield(self._inflight)

    async def _run(self) -> CheckResult:
        probe = asyncio.ensure_future(self._check())
        self._probes.add(probe)
        probe.add_done_callback(self._probes.discard)
        probe.add_done_callback(_retrieve)
        try:
            done, _ = await asyncio.wait({probe}, timeout=self._timeout_s)
        except asyncio.CancelledError:  # shutdown (aclose)
            probe.cancel()
            raise
        if not done:
            # Do not await the cancellation: a driver may take seconds to give up
            # a stalled connection. The abandoned probe finishes in the background.
            probe.cancel()
            await self._recover()
            raise TimeoutError(f"readiness probe exceeded {self._timeout_s}s")
        try:
            return probe.result()
        except Exception:
            await self._recover()
            raise

    async def _recover(self) -> None:
        if self._on_failure is None:
            return
        try:
            await asyncio.wait_for(self._on_failure(), self._timeout_s)
        except Exception:
            _log.warning("readiness recovery action failed", exc_info=True)

    async def aclose(self) -> None:
        tasks = [t for t in (self._inflight, *self._probes) if t is not None and not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=_SHUTDOWN_GRACE_S)


def _retrieve(task: asyncio.Future[CheckResult]) -> None:
    # Mark the outcome as retrieved even if no caller awaits it, so a failed or
    # abandoned probe is never reported as "exception was never retrieved".
    if not task.cancelled():
        task.exception()


def build_lifespan(settings: Settings) -> Lifespan:
    """Create backing-service clients on startup and close them on shutdown."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The exit stack closes whatever was created, in reverse order, even if
        # creating a later client fails (review R-B-004 notes).
        async with AsyncExitStack() as stack:
            checks: list[HealthCheck] = []
            if settings.database_url is not None:
                engine = create_engine(settings)
                stack.push_async_callback(engine.dispose)
                checks.append(_single_flight(stack, database_check(engine), on_failure=engine.dispose))
            if settings.redis_url is not None:
                redis = create_redis(settings)
                stack.push_async_callback(redis.aclose)
                checks.append(_single_flight(stack, redis_check(redis)))
            app.state.readiness_checks = tuple(checks)
            yield

    return lifespan


def _single_flight(
    stack: AsyncExitStack, check: HealthCheck, on_failure: Callable[[], Awaitable[None]] | None = None
) -> HealthCheck:
    # Registered after its client, so the exit stack cancels a running probe
    # before it closes the client the probe uses.
    flight = _SingleFlight(check, on_failure=on_failure)
    stack.push_async_callback(flight.aclose)
    return flight


def build_app(settings: Settings | None = None) -> FastAPI:
    """Assemble the application from settings (environment by default)."""
    resolved = settings if settings is not None else get_settings()
    configure_logging(resolved)
    return create_app(resolved, lifespan=build_lifespan(resolved))


@cache
def _default_app() -> FastAPI:
    return build_app()


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return _default_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
