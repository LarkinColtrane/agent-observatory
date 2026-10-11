"""Role bootstrap script (deploy/postgres/init/10-ao-roles.sh) and the compose healthcheck.

Password-rule tests run the script with /bin/sh and need no services. The
idempotency and failed-first-init tests start throwaway postgres containers
(docker + the postgres:16.10-alpine image; skipped locally without them,
failures under AO_REQUIRE_INTEGRATION=1).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator

import pytest

from .conftest import BOOTSTRAP_SCRIPT, POSTGRES_IMAGE, REPO_ROOT, require_docker

VALIDATION_MESSAGES = (
    "is not set",
    "must contain only",
    "still holds a placeholder",
    "must be at least 16 characters",
    "must differ",
)
# Same capability set as the postgres service in compose.yaml (asserted below).
POSTGRES_CAPS = ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"]


def _pw() -> str:
    return secrets.token_hex(16)  # [0-9a-f]{32}: valid, and cannot contain "change"


def _run_script_locally(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    sh = shutil.which("sh")
    assert sh is not None
    base = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PGHOST": "/nonexistent",
        "PGCONNECT_TIMEOUT": "1",
    }
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sh, str(BOOTSTRAP_SCRIPT)],
        env=base | env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


GOOD_APP, GOOD_MIG, GOOD_SUPER = _pw(), _pw(), _pw()


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"AO_PG_APP_PASSWORD": ""}, "AO_PG_APP_PASSWORD is not set"),
        ({"AO_PG_MIGRATION_PASSWORD": ""}, "AO_PG_MIGRATION_PASSWORD is not set"),
        ({"AO_PG_APP_PASSWORD": "<change-me-app-password>"}, "AO_PG_APP_PASSWORD must contain only"),
        (
            {"AO_PG_APP_PASSWORD": "Change-Me-0123456789abcdef"},
            "AO_PG_APP_PASSWORD still holds a placeholder",
        ),
        ({"AO_PG_MIGRATION_PASSWORD": "abcCHANGEdef0123456789"}, "still holds a placeholder"),
        ({"AO_PG_APP_PASSWORD": "abc123_-XYZ"}, "AO_PG_APP_PASSWORD must be at least 16 characters"),
        ({"AO_PG_APP_PASSWORD": "abcdef0123456789@x"}, "AO_PG_APP_PASSWORD must contain only"),
        ({"AO_PG_APP_PASSWORD": "abcdef0123456789%40"}, "AO_PG_APP_PASSWORD must contain only"),
        ({"AO_PG_APP_PASSWORD": "abcdef 0123456789"}, "AO_PG_APP_PASSWORD must contain only"),
        ({"AO_PG_APP_PASSWORD": "abcdef0123456789é"}, "AO_PG_APP_PASSWORD must contain only"),
        ({"AO_PG_APP_PASSWORD": GOOD_MIG}, "AO_PG_APP_PASSWORD and AO_PG_MIGRATION_PASSWORD must differ"),
        ({"POSTGRES_PASSWORD": GOOD_APP}, "POSTGRES_PASSWORD must differ from the role passwords"),
        ({"POSTGRES_PASSWORD": GOOD_MIG}, "POSTGRES_PASSWORD must differ from the role passwords"),
        ({"POSTGRES_PASSWORD": "change-me-superuser"}, "POSTGRES_PASSWORD still holds a placeholder"),
        ({"POSTGRES_PASSWORD": "short"}, "POSTGRES_PASSWORD must be at least 16 characters"),
        ({"POSTGRES_PASSWORD": ""}, "POSTGRES_PASSWORD (or PGPASSWORD) is not set"),
        ({"POSTGRES_PASSWORD": "", "PGPASSWORD": GOOD_APP}, "PGPASSWORD must differ from the role passwords"),
    ],
)
def test_bootstrap_rejects_bad_passwords_without_printing_them(
    override: dict[str, str], message: str
) -> None:
    env = {
        "AO_PG_APP_PASSWORD": GOOD_APP,
        "AO_PG_MIGRATION_PASSWORD": GOOD_MIG,
        "POSTGRES_PASSWORD": GOOD_SUPER,
    } | override
    env = {k: v for k, v in env.items() if v}
    proc = _run_script_locally(env)
    assert proc.returncode == 1
    assert message in proc.stderr
    for value in env.values():
        assert value not in proc.stdout + proc.stderr


def test_bootstrap_accepts_valid_passwords_and_proceeds_to_connect() -> None:
    """Positive control: valid values pass every check (the script then tries psql)."""
    proc = _run_script_locally(
        {
            "AO_PG_APP_PASSWORD": GOOD_APP,
            "AO_PG_MIGRATION_PASSWORD": GOOD_MIG,
            "POSTGRES_PASSWORD": GOOD_SUPER,
        }
    )
    assert proc.returncode != 0  # no server at PGHOST=/nonexistent
    assert not any(m in proc.stderr for m in VALIDATION_MESSAGES)
    for value in (GOOD_APP, GOOD_MIG, GOOD_SUPER):
        assert value not in proc.stdout + proc.stderr


# ---------------------------------------------------------------- docker-based


def _docker(
    docker: str, *args: str, env: dict[str, str] | None = None, stdin: str | None = None, timeout: float = 60
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [docker, *args],
        env=(os.environ | env) if env else None,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _compose_postgres_healthcheck() -> str:
    """The exact postgres healthcheck command from compose.yaml."""
    for line in (REPO_ROOT / "compose.yaml").read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("test:") and "pg_isready" in stripped:
            kind, command = json.loads(stripped.removeprefix("test:").strip())
            assert kind == "CMD-SHELL"
            return str(command)
    raise AssertionError("postgres healthcheck not found in compose.yaml")


def _wait(predicate: object, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for {what}")


def _start_postgres(docker: str, *extra: str, env: dict[str, str]) -> str:
    name = f"ao-it-pg-{secrets.token_hex(4)}"
    env_flags = [flag for key in env for flag in ("-e", key)]  # values via environment, not argv
    proc = _docker(docker, "run", "-d", "--name", name, *env_flags, *extra, POSTGRES_IMAGE, env=env)
    assert proc.returncode == 0, proc.stderr
    return name


def _server_up(docker: str, name: str) -> bool:
    return (
        _docker(docker, "exec", name, "pg_isready", "-q", "-h", "127.0.0.1", "-U", "postgres").returncode == 0
    )


SNAPSHOT_SQL = """
SELECT json_build_object(
  'roles', (SELECT json_agg(json_build_array(rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
                   rolcanlogin, rolreplication, rolbypassrls) ORDER BY rolname)
            FROM pg_roles WHERE rolname LIKE 'ao\\_%'),
  'members', (SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
              WHERE r.rolname = 'ao_app'),
  'dbs', (SELECT json_agg(json_build_array(datname, pg_get_userbyid(datdba), datacl::text,
                 shobj_description(oid, 'pg_database')) ORDER BY datname) FROM pg_database
          WHERE datname IN ('observatory', 'postgres', 'template1'))
)
"""
DB_SNAPSHOT_SQL = """
SELECT json_build_object(
  'public', (SELECT json_build_array(pg_get_userbyid(nspowner), nspacl::text)
             FROM pg_namespace WHERE nspname = 'public'),
  'defaults', (SELECT json_agg(json_build_array(pg_get_userbyid(defaclrole), defaclobjtype, defaclacl::text)
               ORDER BY defaclobjtype) FROM pg_default_acl),
  'lo', (SELECT json_agg(json_build_array(oid::regprocedure::text, proacl::text) ORDER BY oid)
         FROM pg_proc WHERE proname IN ('lo_creat', 'lo_create', 'lo_from_bytea', 'lo_import'))
)
"""


@pytest.fixture
def plain_postgres() -> Iterator[tuple[str, str, dict[str, str]]]:
    """A fresh postgres container WITHOUT the init script mounted."""
    docker = require_docker()
    env = {"POSTGRES_PASSWORD": _pw()}
    name = _start_postgres(docker, env=env)
    try:
        _wait(lambda: _server_up(docker, name), 60, "postgres to start")
        yield docker, name, env
    finally:
        _docker(docker, "rm", "-f", "-v", name)


def _snapshot(docker: str, name: str) -> tuple[str, str]:
    cluster = _docker(docker, "exec", name, "psql", "-X", "-tA", "-U", "postgres", "-c", SNAPSHOT_SQL)
    db = _docker(
        docker,
        "exec",
        name,
        "psql",
        "-X",
        "-tA",
        "-U",
        "postgres",
        "-d",
        "observatory",
        "-c",
        DB_SNAPSHOT_SQL,
    )
    assert cluster.returncode == 0, cluster.stderr
    assert db.returncode == 0, db.stderr
    return cluster.stdout, db.stdout


def test_bootstrap_is_idempotent_and_marks_completion(
    plain_postgres: tuple[str, str, dict[str, str]],
) -> None:
    docker, name, _ = plain_postgres
    roles = {"AO_PG_APP_PASSWORD": _pw(), "AO_PG_MIGRATION_PASSWORD": _pw()}
    script = BOOTSTRAP_SCRIPT.read_text()
    check = ["exec", "-i", name, "sh", "-s", "--", "--check"]

    assert _docker(docker, *check, stdin=script).returncode != 0  # nothing bootstrapped yet

    run = ["exec", "-i", "-e", "AO_PG_APP_PASSWORD", "-e", "AO_PG_MIGRATION_PASSWORD", name, "sh", "-s"]
    first = _docker(docker, *run, env=roles, stdin=script)
    assert first.returncode == 0, first.stderr
    after_first = _snapshot(docker, name)
    assert _docker(docker, *check, stdin=script).returncode == 0

    second = _docker(docker, *run, env=roles, stdin=script)
    assert second.returncode == 0, second.stderr
    assert _snapshot(docker, name) == after_first
    assert _docker(docker, *check, stdin=script).returncode == 0
    assert '"members" : 0' in after_first[0]
    assert "ao-bootstrap: complete v1" in after_first[0]

    # The role password set from the environment works over TCP (scram).
    login = _docker(
        docker,
        "exec",
        "-e",
        "PGPASSWORD",
        name,
        "psql",
        "-X",
        "-tA",
        "-h",
        "127.0.0.1",
        "-U",
        "ao_app",
        "-d",
        "observatory",
        "-c",
        "SELECT current_user",
        env={"PGPASSWORD": roles["AO_PG_APP_PASSWORD"]},
    )
    assert (login.returncode, login.stdout.strip()) == (0, "ao_app"), login.stderr
    logs = _docker(docker, "logs", name)
    for value in roles.values():
        assert value not in logs.stdout + logs.stderr


def test_compose_postgres_hardening_matches_tested_caps() -> None:
    compose = (REPO_ROOT / "compose.yaml").read_text()
    assert f"cap_add: [{', '.join(POSTGRES_CAPS)}]" in compose
    assert "10-ao-roles.sh --check" in _compose_postgres_healthcheck()


def _start_initialising(docker: str, env: dict[str, str]) -> str:
    init_dir = str(BOOTSTRAP_SCRIPT.parent)
    caps = [flag for cap in POSTGRES_CAPS for flag in ("--cap-add", cap)]
    return _start_postgres(
        docker,
        "-v",
        f"{init_dir}:/docker-entrypoint-initdb.d:ro",
        "--cap-drop",
        "ALL",
        *caps,
        "--security-opt",
        "no-new-privileges:true",
        env=env,
    )


def test_first_init_through_entrypoint_turns_healthy() -> None:
    docker = require_docker()
    healthcheck = _compose_postgres_healthcheck()
    name = _start_initialising(
        docker, {"POSTGRES_PASSWORD": _pw(), "AO_PG_APP_PASSWORD": _pw(), "AO_PG_MIGRATION_PASSWORD": _pw()}
    )
    try:
        _wait(
            lambda: _docker(docker, "exec", name, "sh", "-c", healthcheck).returncode == 0,
            90,
            "the compose healthcheck to pass after a good first init",
        )
    finally:
        _docker(docker, "rm", "-f", "-v", name)


def test_failed_first_init_never_turns_healthy() -> None:
    """Review R-A-004-01: a failed init + restart leaves a running server that must stay unhealthy."""
    docker = require_docker()
    healthcheck = _compose_postgres_healthcheck()
    name = _start_initialising(
        docker,
        {
            "POSTGRES_PASSWORD": _pw(),
            "AO_PG_APP_PASSWORD": "change-me-app-password",
            "AO_PG_MIGRATION_PASSWORD": _pw(),
        },
    )
    try:
        waited = _docker(docker, "wait", name, timeout=90)
        assert waited.returncode == 0
        assert waited.stdout.strip() != "0"  # the entrypoint aborted
        assert "still holds a placeholder" in _docker(docker, "logs", name).stderr
        # Restart on the same data directory: the image skips init and serves anyway.
        assert _docker(docker, "start", name).returncode == 0
        _wait(lambda: _server_up(docker, name), 60, "postgres to restart")
        for _ in range(3):
            assert _docker(docker, "exec", name, "sh", "-c", healthcheck).returncode != 0
            time.sleep(0.5)
    finally:
        _docker(docker, "rm", "-f", "-v", name)
