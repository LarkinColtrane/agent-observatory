"""Composition root (ADR-0005 §3). ASGI entry point: ``observatory.main:app``.

Only this module wires ``api`` to ``db``/``cache`` (import-linter enforces it).
Importing it has no side effects: ``app`` is built on first attribute access
(PEP 562), and the engine and Redis client live inside the lifespan, which
registers their readiness checks and disposes them on shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import cache

from fastapi import FastAPI

from observatory.api.app import create_app
from observatory.cache import create_redis, redis_check
from observatory.core.config import Settings, get_settings
from observatory.core.health import HealthCheck
from observatory.core.logging import configure_logging
from observatory.db import create_engine, database_check

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def build_lifespan(settings: Settings) -> Lifespan:
    """Create backing-service clients on startup and close them on shutdown."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings) if settings.database_url is not None else None
        redis = create_redis(settings) if settings.redis_url is not None else None
        try:
            checks: list[HealthCheck] = []
            if engine is not None:
                checks.append(database_check(engine))
            if redis is not None:
                checks.append(redis_check(redis))
            app.state.readiness_checks = tuple(checks)
            yield
        finally:
            if redis is not None:
                await redis.aclose()
            if engine is not None:
                await engine.dispose()

    return lifespan


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
