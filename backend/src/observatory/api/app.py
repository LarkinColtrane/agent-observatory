"""FastAPI application factory (ADR-0005 §3).

Exposes only the unauthenticated operational endpoints ``/healthz``,
``/readyz`` and ``/version``; the OpenAPI schema and docs UIs are disabled so
no other unauthenticated endpoint exists. Readiness checks are injected by the
composition root through ``lifespan`` (``app.state.readiness_checks``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from observatory import __version__
from observatory.api.middleware import RequestIdMiddleware
from observatory.core.errors import VALIDATION_ERROR, ObservatoryError, error_body
from observatory.core.health import HealthCheck, run_checks
from observatory.core.logging import request_id_var

if TYPE_CHECKING:  # annotation only: Settings is built solely by get_settings()
    from observatory.core.config import Settings  # noqa: TID251 (type only; never constructed)

logger = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

#: Overall deadline for all readiness checks together.
READINESS_TIMEOUT_S = 2.0

_HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


def _error_response(
    code: str, message: str, status: int, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(error_body(code, message, request_id_var.get()), status_code=status, headers=headers)


def create_app(settings: Settings, *, lifespan: Lifespan | None = None) -> FastAPI:
    """Build the API. ``lifespan`` may set ``app.state.readiness_checks``; default is none."""
    app = FastAPI(
        title=settings.service_name,
        version=__version__,
        lifespan=lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.readiness_checks = ()

    app.add_middleware(RequestIdMiddleware)  # also renders unhandled exceptions as 500

    @app.exception_handler(ObservatoryError)
    async def observatory_error(_: Request, exc: ObservatoryError) -> JSONResponse:
        logger.info("request failed: %s (%d)", exc.code, exc.status)
        return _error_response(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # The pydantic error list can echo request input: never returned or logged.
        logger.info("request validation failed (%d error(s))", len(exc.errors()))
        return _error_response(VALIDATION_ERROR, "request validation failed", 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_ERROR_CODES.get(exc.status_code, "http_error")
        try:
            message = HTTPStatus(exc.status_code).phrase
        except ValueError:
            message = "error"
        return _error_response(code, message, exc.status_code, headers=exc.headers)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        checks: Sequence[HealthCheck] = request.app.state.readiness_checks
        results = await run_checks(checks, timeout_s=READINESS_TIMEOUT_S)
        ready = all(r.ok for r in results) and (bool(results) or settings.env == "test")
        body = {
            "status": "ready" if ready else "not_ready",
            "checks": [{"name": r.name, "ok": r.ok} for r in results],
        }
        return JSONResponse(body, status_code=200 if ready else 503)

    @app.get("/version")
    async def version() -> dict[str, str | None]:
        return {"service": settings.service_name, "version": __version__, "git_sha": settings.git_sha}

    return app
