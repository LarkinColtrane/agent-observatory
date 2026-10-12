"""Shared unit-test fixtures (owner: AO-P1-002 / W1)."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from observatory.api.app import create_app
from observatory.core.config import Settings

SettingsFactory = Callable[..., Settings]


@pytest.fixture
def make_settings() -> SettingsFactory:
    """Build ``Settings`` from explicit values only (synthetic, never the real environment)."""

    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "env": "test",
            "service_name": "agent-observatory",
            "log_level": "INFO",
            "log_format": "json",
            "database_url": None,
            "migration_database_url": None,
            "redis_url": None,
            "git_sha": None,
        }
        values.update(overrides)
        return Settings(**values)

    return factory


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """``configure_logging`` mutates process-global logging and hooks; put them back after each test."""
    hooks = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access"]
    saved = {
        n: (logging.getLogger(n).handlers[:], logging.getLogger(n).level, logging.getLogger(n).propagate)
        for n in names
    }
    yield
    for name, (handlers, level, propagate) in saved.items():
        lg = logging.getLogger(name)
        for handler in lg.handlers[:]:
            if handler not in handlers:
                lg.removeHandler(handler)
                handler.close()
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
    logging.captureWarnings(False)  # restores warnings.showwarning
    sys.excepthook, threading.excepthook, sys.unraisablehook = hooks


@pytest.fixture
def app(make_settings: SettingsFactory) -> FastAPI:
    return create_app(make_settings())


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
