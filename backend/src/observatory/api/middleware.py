"""Request-ID middleware (ADR-0005 §3).

Pure ASGI so that it wraps everything below it: the request ID is bound for
the whole request (including exception handlers and logging), echoed in the
``X-Request-ID`` response header, and an unhandled exception becomes a generic
500 ``internal_error`` body that still carries the request ID.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from observatory.core.errors import INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE, error_body
from observatory.core.logging import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER: Final = "X-Request-ID"
_REQUEST_ID_RE: Final = re.compile(r"[A-Za-z0-9-]{8,64}")
_HEADER_KEY: Final = REQUEST_ID_HEADER.lower().encode("latin-1")


def accept_request_id(value: str | None) -> str:
    """Return ``value`` if it fully matches ``[A-Za-z0-9-]{8,64}``, else a fresh UUID4."""
    if value is not None and _REQUEST_ID_RE.fullmatch(value):
        return value
    return str(uuid.uuid4())


def _incoming_request_id(scope: Scope) -> str | None:
    for key, raw in scope.get("headers", ()):
        if key.lower() == _HEADER_KEY:
            return bytes(raw).decode("latin-1")
    return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = accept_request_id(_incoming_request_id(scope))
        token = request_id_var.set(request_id)
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # Details go to the (redacted) log only; the client gets a generic body.
            logger.exception("unhandled exception while serving request")
            if response_started:
                raise
            response = JSONResponse(
                error_body(INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE, request_id),
                status_code=500,
                headers={REQUEST_ID_HEADER: request_id},
            )
            await response(scope, receive, send)
        finally:
            request_id_var.reset(token)
