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
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from functools import cache
from typing import TYPE_CHECKING

from fastapi import FastAPI

from observatory.api.app import create_app
from observatory.cache import create_redis, redis_check
from observatory.core.config import get_settings
from observatory.core.health import CheckResult, HealthCheck
from observatory.core.logging import configure_logging
from observatory.db import create_engine, database_check

if TYPE_CHECKING:
    from observatory.core.config import Settings  # noqa: TID251 (type only)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


class _SingleFlight:
    """Share one in-flight probe among concurrent callers of a health check.

    A caller cancelled by the readiness deadline does not cancel the shared
    probe (``asyncio.shield``); the next caller after it finishes starts a new
    one. ``aclose`` cancels a probe still running at shutdown.
    """

    def __init__(self, check: HealthCheck) -> None:
        self._check = check
        self._inflight: asyncio.Task[CheckResult] | None = None
        # run_checks names a failed check from this attribute (core.health).
        self.check_name: str | None = getattr(check, "check_name", None)

    async def __call__(self) -> CheckResult:
        if self._inflight is None or self._inflight.done():
            self._inflight = asyncio.ensure_future(self._check())
            # Retrieve the outcome even if every caller was cancelled, so a failed
            # probe is never reported as "exception was never retrieved".
            self._inflight.add_done_callback(lambda t: t.cancelled() or t.exception())
        return await asyncio.shield(self._inflight)

    async def aclose(self) -> None:
        if self._inflight is not None and not self._inflight.done():
            self._inflight.cancel()
            await asyncio.gather(self._inflight, return_exceptions=True)


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
                checks.append(_single_flight(stack, database_check(engine)))
            if settings.redis_url is not None:
                redis = create_redis(settings)
                stack.push_async_callback(redis.aclose)
                checks.append(_single_flight(stack, redis_check(redis)))
            app.state.readiness_checks = tuple(checks)
            yield

    return lifespan


def _single_flight(stack: AsyncExitStack, check: HealthCheck) -> HealthCheck:
    # Registered after its client, so the exit stack cancels a running probe
    # before it closes the client the probe uses.
    flight = _SingleFlight(check)
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
