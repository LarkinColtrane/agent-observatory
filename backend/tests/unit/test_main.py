"""Composition root (ADR-0005 §3; owner: AO-P1-006 / Coordinator)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

import observatory.main as main_module
from observatory.core.config import get_settings
from observatory.core.health import CheckResult, make_check, run_checks
from observatory.core.logging import request_id_var
from observatory.main import build_app, build_lifespan
from tests.unit.conftest import SettingsFactory

# Synthetic credentials, assembled at runtime (never a literal secret in the repo).
_PW = "unit" + "-only-" + "pw"
_DB_URL = "postgresql+psycopg://ao_app:" + _PW + "@127.0.0.1:1/observatory"
_REDIS_URL = "redis://127.0.0.1:1/0"


class _Closable:
    def __init__(self, kind: str, events: list[str]) -> None:
        self.kind, self.events = kind, events

    async def dispose(self) -> None:
        self.events.append(f"{self.kind}:closed")

    async def aclose(self) -> None:
        self.events.append(f"{self.kind}:closed")


@pytest.fixture
def fake_seams(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the db/cache seams with recorders; returns the event log."""
    events: list[str] = []

    def named(name: str) -> Any:
        async def check() -> CheckResult:
            return CheckResult(name, True)

        return check

    monkeypatch.setattr(main_module, "create_engine", lambda s: _Closable("engine", events))
    monkeypatch.setattr(main_module, "create_redis", lambda s: _Closable("redis", events))
    monkeypatch.setattr(main_module, "database_check", lambda e: named("database"))
    monkeypatch.setattr(main_module, "redis_check", lambda c: named("redis"))
    return events


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_no_backing_services_registers_no_checks(make_settings: SettingsFactory) -> None:
    app = build_app(make_settings())
    async with app.router.lifespan_context(app):
        assert app.state.readiness_checks == ()
        async with _client(app) as c:
            assert (await c.get("/readyz")).status_code == 200  # env=test permits no checks


async def test_registers_checks_and_closes_clients(
    make_settings: SettingsFactory, fake_seams: list[str]
) -> None:
    app = FastAPI(lifespan=build_lifespan(make_settings(database_url=_DB_URL, redis_url=_REDIS_URL)))
    async with app.router.lifespan_context(app):
        assert [await c() for c in app.state.readiness_checks] == [
            CheckResult("database", True),
            CheckResult("redis", True),
        ]
        assert fake_seams == []
    assert fake_seams == ["redis:closed", "engine:closed"]


async def test_clients_closed_when_app_fails(make_settings: SettingsFactory, fake_seams: list[str]) -> None:
    app = FastAPI(lifespan=build_lifespan(make_settings(database_url=_DB_URL, redis_url=_REDIS_URL)))
    with pytest.raises(RuntimeError, match="boom"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("boom")
    assert fake_seams == ["redis:closed", "engine:closed"]


async def test_engine_disposed_when_redis_creation_fails(
    make_settings: SettingsFactory, fake_seams: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(settings: object) -> None:
        raise ValueError("bad redis configuration")

    monkeypatch.setattr(main_module, "create_redis", broken)
    app = FastAPI(lifespan=build_lifespan(make_settings(database_url=_DB_URL, redis_url=_REDIS_URL)))
    with pytest.raises(ValueError, match="bad redis"):
        async with app.router.lifespan_context(app):
            pass  # pragma: no cover - startup fails before the app runs
    assert fake_seams == ["engine:closed"]


async def test_only_configured_services_are_created(
    make_settings: SettingsFactory, fake_seams: list[str]
) -> None:
    app = FastAPI(lifespan=build_lifespan(make_settings(redis_url=_REDIS_URL)))
    async with app.router.lifespan_context(app):
        assert len(app.state.readiness_checks) == 1
    assert fake_seams == ["redis:closed"]


async def test_real_seams_fail_closed_when_services_are_down(make_settings: SettingsFactory) -> None:
    """End to end through the real db/cache seams: unreachable services make /readyz 503."""
    app = build_app(make_settings(env="dev", database_url=_DB_URL, redis_url=_REDIS_URL))
    async with app.router.lifespan_context(app), _client(app) as c:
        response = await c.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == [{"name": "database", "ok": False}, {"name": "redis", "ok": False}]
    assert _PW not in response.text


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("AO_")}


def test_import_has_no_side_effects() -> None:
    """Importing the module reads no settings; only accessing ``app`` does (and fails sanitized)."""
    run = [sys.executable, "-I", "-c"]
    imported = subprocess.run(  # noqa: S603 (fixed argv: this interpreter, constant code)
        [*run, "import observatory.main"], env=_clean_env(), capture_output=True, text=True, check=False
    )
    assert imported.returncode == 0, imported.stderr
    accessed = subprocess.run(  # noqa: S603 (fixed argv: this interpreter, constant code)
        [*run, "import observatory.main as m; m.app"],
        env=_clean_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert accessed.returncode != 0
    assert "invalid configuration" in accessed.stderr


@pytest.fixture
def default_app_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in [k for k in os.environ if k.startswith("AO_")]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("AO_ENV", "test")
    get_settings.cache_clear()
    main_module._default_app.cache_clear()
    yield
    get_settings.cache_clear()
    main_module._default_app.cache_clear()


@pytest.mark.usefixtures("default_app_env")
def test_app_is_built_once_on_first_access() -> None:
    assert main_module.app is main_module.app
    assert isinstance(main_module.app, FastAPI)


def test_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        _ = main_module.nope


# --- single-flight readiness (review R-B-004-201) -----------------------------


class _CountingProbe:
    """A health check that records how many invocations overlap."""

    def __init__(self, name: str, delay: float = 0.05, ok: bool = True) -> None:
        self.name, self.delay, self.ok = name, delay, ok
        self.calls = self.running = self.peak = 0
        self.cancelled = asyncio.Event()

    async def __call__(self) -> CheckResult:
        self.calls += 1
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.running -= 1
        if not self.ok:
            raise ConnectionError("probe failed")
        return CheckResult(self.name, True)


@pytest.fixture
def counting_seams(monkeypatch: pytest.MonkeyPatch, fake_seams: list[str]) -> dict[str, _CountingProbe]:
    probes = {"database": _CountingProbe("database"), "redis": _CountingProbe("redis")}
    monkeypatch.setattr(main_module, "database_check", lambda e: probes["database"])
    monkeypatch.setattr(main_module, "redis_check", lambda c: probes["redis"])
    return probes


async def test_concurrent_readyz_share_one_probe_per_service(
    make_settings: SettingsFactory, counting_seams: dict[str, _CountingProbe]
) -> None:
    app = build_app(make_settings(env="dev", database_url=_DB_URL, redis_url=_REDIS_URL))
    async with app.router.lifespan_context(app), _client(app) as c:
        responses = await asyncio.gather(*(c.get("/readyz") for _ in range(100)))
    assert [r.status_code for r in responses] == [200] * 100
    for probe in counting_seams.values():
        assert probe.peak == 1
        assert probe.calls < 10  # 100 callers shared a handful of probes


async def test_cancelled_caller_does_not_cancel_shared_probe(
    counting_seams: dict[str, _CountingProbe],
) -> None:
    probe = counting_seams["database"]
    flight = main_module._SingleFlight(probe)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(flight(), timeout=0.01)
    assert await flight() == CheckResult("database", True)
    assert probe.calls == 1
    assert not probe.cancelled.is_set()


async def test_failed_probe_keeps_its_name() -> None:
    async def boom() -> None:
        raise ConnectionError("down")

    flight = main_module._SingleFlight(make_check("redis", boom))
    assert await run_checks([flight]) == [CheckResult("redis", False)]


async def test_shutdown_cancels_inflight_probe(
    make_settings: SettingsFactory, counting_seams: dict[str, _CountingProbe]
) -> None:
    probe = counting_seams["redis"]
    probe.delay = 60
    app = FastAPI(lifespan=build_lifespan(make_settings(redis_url=_REDIS_URL)))
    async with app.router.lifespan_context(app):
        (check,) = app.state.readiness_checks
        task = asyncio.ensure_future(check())
        await asyncio.sleep(0.01)
    assert probe.cancelled.is_set()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_stalled_shared_probe_is_bounded_and_replaced(
    counting_seams: dict[str, _CountingProbe],
) -> None:
    """Review R-B-006-01: a stalled probe must not be shared forever."""
    probe = counting_seams["database"]
    probe.delay = 60
    flight = main_module._SingleFlight(probe, timeout_s=0.05)
    with pytest.raises(TimeoutError):
        await flight()
    await asyncio.sleep(0)  # the abandoned probe handles its cancellation
    assert probe.cancelled.is_set()  # the deadline reached the probe itself
    probe.delay = 0
    assert await flight() == CheckResult("database", True)
    assert probe.calls == 2  # a fresh probe, not the stalled one


async def test_probe_does_not_inherit_caller_request_id() -> None:
    """Review R-B-006-03: the shared probe runs in a fresh context."""
    seen: list[str | None] = []

    async def probe() -> CheckResult:
        seen.append(request_id_var.get())
        return CheckResult("database", True)

    token = request_id_var.set("caller-request-1")
    try:
        await main_module._SingleFlight(probe)()
    finally:
        request_id_var.reset(token)
    assert seen == [None]


async def test_timeout_does_not_wait_for_a_slow_cancellation() -> None:
    """A driver may take seconds to give up a stalled connection; readiness must not."""

    async def stubborn() -> CheckResult:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            await asyncio.sleep(1)  # e.g. psycopg's cancel request on a dead path
            raise
        return CheckResult("database", True)  # pragma: no cover

    flight = main_module._SingleFlight(stubborn, timeout_s=0.05)
    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(TimeoutError):
        await flight()
    assert loop.time() - start < 0.5
    await flight.aclose()


async def test_recovery_runs_after_failure_and_timeout_only() -> None:
    """Review R-A-006-01: the pool reset hook runs when a probe fails or times out."""
    recoveries: list[str] = []
    outcome = {"mode": "ok"}

    async def probe() -> CheckResult:
        if outcome["mode"] == "fail":
            raise ConnectionError("down")
        if outcome["mode"] == "hang":
            await asyncio.sleep(60)
        return CheckResult("database", True)

    async def recover() -> None:
        recoveries.append(outcome["mode"])

    flight = main_module._SingleFlight(probe, timeout_s=0.05, on_failure=recover)
    assert await flight() == CheckResult("database", True)
    outcome["mode"] = "fail"
    with pytest.raises(ConnectionError):
        await flight()
    outcome["mode"] = "hang"
    with pytest.raises(TimeoutError):
        await flight()
    assert recoveries == ["fail", "hang"]
    await flight.aclose()


async def test_lifespan_resets_the_database_pool_on_probe_failure(
    make_settings: SettingsFactory, monkeypatch: pytest.MonkeyPatch, fake_seams: list[str]
) -> None:
    async def down() -> CheckResult:
        raise ConnectionError("down")

    monkeypatch.setattr(main_module, "database_check", lambda e: down)
    app = FastAPI(lifespan=build_lifespan(make_settings(database_url=_DB_URL)))
    async with app.router.lifespan_context(app):
        (check,) = app.state.readiness_checks
        with pytest.raises(ConnectionError):
            await check()
        assert fake_seams == ["engine:closed"]  # engine.dispose() reset the pool
