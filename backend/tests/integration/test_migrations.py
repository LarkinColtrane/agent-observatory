"""Alembic upgrade → downgrade → upgrade on real PostgreSQL 16 (migration role)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, text

from observatory.db.migration import MIGRATION_LOCK_KEY

from .conftest import BACKEND_DIR, run_alembic, scrub

HEAD = "0001_baseline"


def _versions(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('alembic.alembic_version')")).scalar_one()
        if exists is None:
            return []
        return list(conn.execute(text("SELECT version_num FROM alembic.alembic_version")).scalars())


def _alembic_env(url: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AO_")}
    return env | {"AO_ENV": "test", "AO_MIGRATION_DATABASE_URL": url}


@contextmanager
def _holding_migration_lock(engine: Engine) -> Iterator[Connection]:
    """Hold MIGRATION_LOCK_KEY (session-level) as another migrator would."""
    with engine.connect() as holder:
        holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
        holder.commit()
        try:
            yield holder
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY})
            holder.commit()


def _ok(*args: str, url: str) -> str:
    proc = run_alembic(*args, migration_url=url)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_upgrade_downgrade_upgrade(migration_database_url: str, migrator_engine: Engine) -> None:
    _ok("upgrade", "head", url=migration_database_url)
    assert _versions(migrator_engine) == [HEAD]
    assert _ok("current", url=migration_database_url).split() == [HEAD, "(head)"]

    _ok("downgrade", "base", url=migration_database_url)
    assert _versions(migrator_engine) == []

    _ok("upgrade", "head", url=migration_database_url)
    assert _versions(migrator_engine) == [HEAD]
    # Idempotent: a second upgrade is a no-op.
    _ok("upgrade", "head", url=migration_database_url)
    assert _versions(migrator_engine) == [HEAD]


def test_concurrent_migrators_serialize(migration_database_url: str, migrator_engine: Engine) -> None:
    """Several migrate jobs starting at once (e.g. replicas) all succeed and apply once."""
    _ok("downgrade", "base", url=migration_database_url)
    env = _alembic_env(migration_database_url)
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    outcomes = []
    for proc in procs:
        with proc:
            _, err = proc.communicate(timeout=60)
        outcomes.append((proc.returncode, scrub(err, migration_database_url)))
    assert [rc for rc, _ in outcomes] == [0] * 4, outcomes
    assert _versions(migrator_engine) == [HEAD]


def test_app_role_cannot_run_migrations(app_database_url: str, at_head: None) -> None:
    """The DML-only role can neither create the version schema nor read migration state."""
    proc = run_alembic("upgrade", "head", migration_url=app_database_url)
    assert proc.returncode != 0
    assert "permission denied" in proc.stderr


def test_migrator_waits_for_the_advisory_lock(migration_database_url: str, migrator_engine: Engine) -> None:
    """Review R-B-004-01: deterministic proof that env.py takes MIGRATION_LOCK_KEY.

    With the lock held elsewhere, ``alembic upgrade head`` must block without
    writing anything; once released it must complete and record the head.
    """
    _ok("downgrade", "base", url=migration_database_url)
    with _holding_migration_lock(migrator_engine):
        proc = subprocess.Popen(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=_alembic_env(migration_database_url),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            time.sleep(2.5)
            still_waiting = proc.poll() is None
            versions_while_held = _versions(migrator_engine)
        except BaseException:
            proc.kill()
            proc.communicate()
            raise
        if not still_waiting:
            proc.communicate()
    with proc:
        _, err = proc.communicate(timeout=60)
    assert still_waiting, "alembic did not wait for the migration advisory lock"
    assert versions_while_held == []
    assert proc.returncode == 0, scrub(err, migration_database_url)
    assert _versions(migrator_engine) == [HEAD]


def test_waiting_migrator_fails_at_lock_timeout(migration_database_url: str, migrator_engine: Engine) -> None:
    """Review R-B-004-06: a migrator stuck behind another errors out instead of hanging."""
    _ok("downgrade", "base", url=migration_database_url)
    with _holding_migration_lock(migrator_engine):
        start = time.monotonic()
        proc = run_alembic("-x", "lock_timeout=1s", "upgrade", "head", migration_url=migration_database_url)
        elapsed = time.monotonic() - start
    assert proc.returncode != 0
    assert "canceling statement due to lock timeout" in proc.stderr
    assert elapsed < 20
    assert _versions(migrator_engine) == []
    _ok("upgrade", "head", url=migration_database_url)
