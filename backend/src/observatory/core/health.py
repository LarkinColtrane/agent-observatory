"""Health-check primitives (ADR-0005 §3).

Checks are time-boxed and fail closed: an exception or a missed deadline
yields ``ok=False``. Details are logged, never returned to callers.
``asyncio.CancelledError`` (a ``BaseException``) is never swallowed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of one readiness check. Deliberately carries no detail text."""

    name: str
    ok: bool


HealthCheck = Callable[[], Awaitable[CheckResult]]


class _NamedCheck:
    """A ``HealthCheck`` that knows its name even when it fails."""

    __slots__ = ("_probe", "check_name")

    def __init__(self, name: str, probe: Callable[[], Awaitable[None]]) -> None:
        self.check_name = name
        self._probe = probe

    async def __call__(self) -> CheckResult:
        await self._probe()
        return CheckResult(name=self.check_name, ok=True)


def make_check(name: str, probe: Callable[[], Awaitable[None]]) -> HealthCheck:
    """Build a named check: ``ok=True`` if ``probe`` completes, else failure via ``run_checks``."""
    if not name:
        raise ValueError("check name must be non-empty")
    return _NamedCheck(name, probe)


async def _guarded(index: int, check: HealthCheck) -> CheckResult | None:
    try:
        return await check()
    except Exception:  # fail closed; BaseException (e.g. cancellation) propagates
        logger.warning("health check %d raised", index, exc_info=True)
        return None


async def run_checks(checks: Sequence[HealthCheck], timeout_s: float = 2.0) -> list[CheckResult]:
    """Run ``checks`` concurrently under one overall deadline of ``timeout_s`` seconds.

    Returns results in input order. A check that raises or does not finish in
    time is reported as ``CheckResult(name, ok=False)``; its name is taken from
    the check's ``check_name`` attribute if present, else ``check-<index>``.
    """
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    tasks = [asyncio.ensure_future(_guarded(i, c)) for i, c in enumerate(checks)]
    if not tasks:
        return []
    try:
        done, pending = await asyncio.wait(tasks, timeout=timeout_s)
    except BaseException:
        # Caller cancelled (or interpreter shutdown): never leave checks running.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        logger.warning("%d health check(s) exceeded %.2fs", len(pending), timeout_s)
    results: list[CheckResult] = []
    for i, (check, task) in enumerate(zip(checks, tasks, strict=True)):
        result = task.result() if task in done else None
        name = getattr(check, "check_name", f"check-{i}")
        results.append(result if result is not None else CheckResult(name=str(name), ok=False))
    return results
