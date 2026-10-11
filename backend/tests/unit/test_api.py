"""API app factory, request-ID middleware and error handlers (ADR-0005 §3)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from starlette.types import Message, Receive, Scope, Send

from observatory import __version__
from observatory.api import app as app_module
from observatory.api.app import create_app
from observatory.api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware, accept_request_id
from observatory.core.errors import ObservatoryError
from observatory.core.health import CheckResult, HealthCheck, make_check
from observatory.core.logging import configure_logging
from tests.unit.conftest import SettingsFactory

# Built at runtime so no source line looks like a credential to secret scanners.
URL_PW = "synthetic-" + "api-pw"
DSN = "postgresql://svc:" + URL_PW + "@db.internal/app"
EXC_DETAIL = "synthetic-internal-detail"


async def _ok() -> None:
    return None


async def _boom() -> None:
    raise RuntimeError(EXC_DETAIL)


async def _hang() -> None:
    await asyncio.sleep(3600)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


def _assert_error(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers[REQUEST_ID_HEADER]
    return dict(body["error"])


# --- operational endpoints ---------------------------------------------------


async def test_healthz(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("git_sha", [None, "0123abc"])
async def test_version(make_settings: SettingsFactory, git_sha: str | None) -> None:
    app = create_app(make_settings(service_name="observatory-test", git_sha=git_sha))
    async with _client(app) as c:
        response = await c.get("/version")
    assert response.status_code == 200
    assert response.json() == {"service": "observatory-test", "version": __version__, "git_sha": git_sha}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_no_other_unauthenticated_endpoints(client: httpx.AsyncClient, path: str) -> None:
    _assert_error(await client.get(path), 404, "not_found")


async def test_method_not_allowed_keeps_allow_header(client: httpx.AsyncClient) -> None:
    response = await client.post("/healthz")
    _assert_error(response, 405, "method_not_allowed")
    assert response.headers["allow"] == "GET"


# --- readiness ---------------------------------------------------------------


async def _readyz(app: FastAPI, checks: list[HealthCheck] | None) -> httpx.Response:
    if checks is not None:
        app.state.readiness_checks = checks
    async with _client(app) as c:
        return await c.get("/readyz")


async def test_readyz_all_ok(app: FastAPI) -> None:
    response = await _readyz(app, [make_check("database", _ok), make_check("redis", _ok)])
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": [{"name": "database", "ok": True}, {"name": "redis", "ok": True}],
    }


async def test_readyz_one_failing_is_503_without_detail(app: FastAPI) -> None:
    response = await _readyz(app, [make_check("database", _boom), make_check("redis", _ok)])
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": [{"name": "database", "ok": False}, {"name": "redis", "ok": True}],
    }
    assert EXC_DETAIL not in response.text


async def test_readyz_timeout_is_503(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "READINESS_TIMEOUT_S", 0.05)
    response = await _readyz(app, [make_check("redis", _hang)])
    assert response.status_code == 503
    assert response.json()["checks"] == [{"name": "redis", "ok": False}]


async def test_readyz_body_lists_only_name_and_ok(app: FastAPI) -> None:
    async def check_with_extra() -> CheckResult:
        return CheckResult("database", True)

    response = await _readyz(app, [check_with_extra])
    assert [set(c) for c in response.json()["checks"]] == [{"name", "ok"}]


@pytest.mark.parametrize(("env", "status", "state"), [("test", 200, "ready"), ("dev", 503, "not_ready")])
async def test_readyz_without_checks(
    make_settings: SettingsFactory, env: str, status: int, state: str
) -> None:
    response = await _readyz(create_app(make_settings(env=env)), None)
    assert response.status_code == status
    assert response.json() == {"status": state, "checks": []}


async def test_readyz_without_checks_in_prod_is_503(make_settings: SettingsFactory) -> None:
    settings = make_settings(env="prod", database_url=DSN, redis_url="redis://cache:6379/0")
    response = await _readyz(create_app(settings), None)
    assert response.status_code == 503


async def test_lifespan_sets_readiness_checks_and_closes(make_settings: SettingsFactory) -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        events.append("open")
        app.state.readiness_checks = (make_check("database", _ok), make_check("redis", _boom))
        yield
        events.append("close")

    app = create_app(make_settings(env="dev"), lifespan=lifespan)
    # httpx's ASGITransport does not run lifespan events; drive the app's own lifespan context.
    async with app.router.lifespan_context(app):
        assert events == ["open"]
        async with _client(app) as c:
            response = await c.get("/readyz")
    assert events == ["open", "close"]
    assert response.status_code == 503
    assert response.json()["checks"] == [{"name": "database", "ok": True}, {"name": "redis", "ok": False}]


# --- request ID --------------------------------------------------------------


@pytest.mark.parametrize("value", ["abcd1234", "A" * 64, "0f6b1c2e-7d1a-4c1e-9b7a-2b5e8f3c4d5a", "--------"])
def test_accept_request_id_valid(value: str) -> None:
    assert accept_request_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "abc1234",
        "A" * 65,
        "abcd1234\n",
        "abcd 1234",
        "abcd_1234",
        "abcd1234;",
        "äbcd1234",
        "abcd1234\x00",
    ],
)
def test_accept_request_id_rejects_and_generates_uuid4(value: str | None) -> None:
    generated = accept_request_id(value)
    assert generated != value
    assert uuid.UUID(generated).version == 4


async def test_valid_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={REQUEST_ID_HEADER: "client-req-0001"})
    assert response.headers[REQUEST_ID_HEADER] == "client-req-0001"


@pytest.mark.parametrize("value", ["short", "x" * 65, "has space1", "semi;colon1"])
async def test_invalid_request_id_is_replaced(client: httpx.AsyncClient, value: str) -> None:
    response = await client.get("/healthz", headers={REQUEST_ID_HEADER: value})
    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed != value
    assert uuid.UUID(echoed).version == 4


async def test_missing_request_id_is_generated(client: httpx.AsyncClient) -> None:
    first = (await client.get("/healthz")).headers[REQUEST_ID_HEADER]
    second = (await client.get("/healthz")).headers[REQUEST_ID_HEADER]
    assert uuid.UUID(first).version == 4
    assert first != second


async def _raw_call(app: Any, headers: list[tuple[bytes, bytes]]) -> list[Message]:
    """Drive an ASGI app directly so headers httpx would refuse (e.g. a trailing newline) can be sent."""
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/healthz",
        "raw_path": b"/healthz",
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _response_request_id(messages: list[Message]) -> str:
    start = next(m for m in messages if m["type"] == "http.response.start")
    values = [v.decode("latin-1") for k, v in start["headers"] if k.lower() == b"x-request-id"]
    assert len(values) == 1
    return values[0]


async def test_trailing_newline_request_id_is_rejected(app: FastAPI) -> None:
    messages = await _raw_call(app, [(b"x-request-id", b"abcd1234\n")])
    echoed = _response_request_id(messages)
    assert echoed != "abcd1234\n"
    assert uuid.UUID(echoed).version == 4


async def test_request_id_header_lookup_is_case_insensitive(app: FastAPI) -> None:
    messages = await _raw_call(app, [(b"X-Request-ID", b"mixed-case-0001")])
    assert _response_request_id(messages) == "mixed-case-0001"


async def test_request_id_in_log_records(
    make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_format="json"))
    app = create_app(make_settings())

    @app.get("/logs")
    async def logs() -> dict[str, str]:
        logging.getLogger("observatory.test").info("inside request")
        return {}

    async with _client(app) as c:
        await c.get("/logs", headers={REQUEST_ID_HEADER: "log-req-00001"})
        generated = (await c.get("/logs", headers={REQUEST_ID_HEADER: "bad"})).headers[REQUEST_ID_HEADER]
    logging.getLogger("observatory.test").info("outside request")
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [r["request_id"] for r in records if r["msg"] == "inside request"] == ["log-req-00001", generated]
    assert next(r for r in records if r["msg"] == "outside request")["request_id"] is None


async def test_non_http_scope_passes_through() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {}

    async def send(message: Message) -> None:
        return None

    await RequestIdMiddleware(inner)({"type": "lifespan"}, receive, send)
    assert seen == ["lifespan"]


async def test_exception_after_response_started_is_reraised(caplog: pytest.LogCaptureFixture) -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError(EXC_DETAIL)

    with pytest.raises(RuntimeError, match=EXC_DETAIL):
        await _raw_call(RequestIdMiddleware(inner), [])
    assert "unhandled exception" in caplog.text


# --- error bodies ------------------------------------------------------------


@pytest.fixture
def error_app(make_settings: SettingsFactory) -> FastAPI:
    app = create_app(make_settings())

    @app.get("/custom")
    async def custom() -> None:
        raise ObservatoryError("thing_missing", "the thing does not exist", status=404)

    @app.get("/custom-default")
    async def custom_default() -> None:
        raise ObservatoryError("bad_thing", "bad thing")

    @app.get("/typed")
    async def typed(count: int) -> dict[str, int]:
        return {"count": count}

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError(f"{EXC_DETAIL} while using {DSN}")

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail=EXC_DETAIL)

    @app.get("/odd-status")
    async def odd_status() -> None:
        raise HTTPException(status_code=599, detail=EXC_DETAIL)

    return app


async def test_observatory_error_body(error_app: FastAPI) -> None:
    async with _client(error_app) as c:
        err = _assert_error(
            await c.get("/custom", headers={REQUEST_ID_HEADER: "err-req-0001"}), 404, "thing_missing"
        )
        default = _assert_error(await c.get("/custom-default"), 400, "bad_thing")
    assert err == {
        "code": "thing_missing",
        "message": "the thing does not exist",
        "request_id": "err-req-0001",
    }
    assert default["message"] == "bad thing"


async def test_validation_error_does_not_echo_input(error_app: FastAPI) -> None:
    async with _client(error_app) as c:
        response = await c.get("/typed", params={"count": "synthetic-not-an-int"})
    err = _assert_error(response, 422, "validation_error")
    assert err["message"] == "request validation failed"
    assert "synthetic-not-an-int" not in response.text


async def test_unhandled_error_is_generic_500(
    error_app: FastAPI, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_format="json"))
    async with _client(error_app) as c:
        response = await c.get("/crash", headers={REQUEST_ID_HEADER: "crash-req-001"})
    err = _assert_error(response, 500, "internal_error")
    assert err["message"] == "internal server error"
    assert EXC_DETAIL not in response.text
    assert URL_PW not in response.text
    assert "Traceback" not in response.text
    logged = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    crash = next(r for r in logged if r["msg"] == "unhandled exception while serving request")
    assert crash["request_id"] == "crash-req-001"
    assert EXC_DETAIL in crash["exc_info"]  # details are logged ...
    assert URL_PW not in json.dumps(logged)  # ... but URL credentials never are


async def test_http_exception_detail_is_not_returned(error_app: FastAPI) -> None:
    async with _client(error_app) as c:
        teapot = await c.get("/teapot")
        odd = await c.get("/odd-status")
    assert _assert_error(teapot, 418, "http_error")["message"] == "I'm a Teapot"
    assert _assert_error(odd, 599, "http_error")["message"] == "error"
    assert EXC_DETAIL not in teapot.text + odd.text


@pytest.mark.parametrize("status", [200, 302, 399, 600])
def test_observatory_error_rejects_non_error_status(status: int) -> None:
    with pytest.raises(ValueError, match="HTTP error status"):
        ObservatoryError("x", "y", status=status)


def test_observatory_error_attributes() -> None:
    exc = ObservatoryError("conflict", "already exists", status=409)
    assert (exc.code, exc.message, exc.status, str(exc)) == (
        "conflict",
        "already exists",
        409,
        "already exists",
    )
