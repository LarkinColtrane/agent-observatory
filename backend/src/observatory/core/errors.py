"""Application errors and the API error body (ADR-0005 §3).

``core`` stays framework-free: the HTTP exception handlers that render these
live in ``observatory.api``.
"""

from __future__ import annotations

from typing import Any

VALIDATION_ERROR = "validation_error"
INTERNAL_ERROR = "internal_error"
INTERNAL_ERROR_MESSAGE = "internal server error"


class ObservatoryError(Exception):
    """An expected, client-facing error.

    ``message`` is returned to the client verbatim, so it must never contain
    secrets, input values or internal detail.
    """

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        if not 400 <= status <= 599:
            raise ValueError("status must be an HTTP error status (400-599)")
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def error_body(code: str, message: str, request_id: str | None) -> dict[str, Any]:
    """The single API error shape: ``{"error": {"code", "message", "request_id"}}``."""
    return {"error": {"code": code, "message": message, "request_id": request_id}}
