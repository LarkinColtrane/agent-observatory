# ADR-0005: Phase 1 engineering-foundation contract

- Status: accepted — frozen at tag `contract-phase1-foundation-v1.0.0`
- Date: 2026-10-10
- Deciders: Coordinator (proposed); Reviewer A and Reviewer B (sign-off)
- Components: C11, C12, C13 (seam only), C4/C5 (seam only)
- Related: ADR-0002, ADR-0003, TD-001, TD-006, A-004

## Context

ADR-0002 chose the stack. Phase 1 must turn it into a runnable, verified
foundation that later phases build on, without implementing any product
behaviour (ADR-0003: no event protocol before Phase 2). Several agents work in
parallel, so the layout, module seams, and quality gates are frozen here first
(parallel-work-policy: freeze before parallel work).

## Decision

### 1. Repository layout

```
backend/                      Python 3.12 service (uv-managed)
  pyproject.toml, uv.lock     single dependency manifest + lock (hotspot)
  alembic.ini, migrations/    Alembic environment and revisions
  src/observatory/
    __init__.py               __version__
    core/                     config, logging, errors, health primitives
    db/                       SQLAlchemy engine + database health check
    cache/                    Redis client + health check
    api/                      FastAPI app factory, routes, middleware
    main.py                   composition root (ASGI entry `observatory.main:app`)
  tests/unit/, tests/integration/
frontend/                     Next.js + React + TypeScript (strict), npm-locked
compose.yaml                  local stack: postgres, redis, backend, frontend
Makefile                      developer entry points (setup, check, test, up)
```

### 2. Module boundaries (enforced by import-linter in CI)

`main` → `api` → `core` and `main` → (`db`, `cache`) → `core`. `core` imports
none of `api`/`db`/`cache`; `db` and `cache` do not import `api` or each other;
`api` does not import `db` or `cache` (readiness checks are injected by
`main`). Only `main.py` composes.

### 3. Frozen interfaces (Python)

Delivered with this contract (AO-P1-001, so every worker builds on real code):

- `observatory.core.config.Settings` (pydantic-settings, env prefix `AO_`):
  `env: Literal["dev","test","prod"]` — **required, no default**;
  `service_name: str = "agent-observatory"`, `log_level: str = "INFO"`,
  `log_format: Literal["json","console"] = "json"`,
  `database_url: SecretStr | None`, `migration_database_url: SecretStr | None`,
  `redis_url: SecretStr | None`, `git_sha: str | None`.
  `env="prod"` requires `database_url` and `redis_url` (validation error
  otherwise). `get_settings() -> Settings` (cached). Secret values are read
  only via `get_secret_value()` at the point of use (engine/client/Alembic)
  and are never logged, returned, or placed in exception messages.
- `observatory.core.health`: `CheckResult(name: str, ok: bool)` (frozen
  dataclass); `HealthCheck = Callable[[], Awaitable[CheckResult]]`;
  `async run_checks(checks, timeout_s: float = 2.0) -> list[CheckResult]` —
  checks run **concurrently** under one overall deadline of `timeout_s`; a
  check that raises `Exception` or misses the deadline becomes
  `CheckResult(<name>, ok=False)` (fail closed); `asyncio.CancelledError` and
  other `BaseException`s propagate (pending checks are cancelled first);
  failure details are logged, never returned. Result order equals input
  order. `make_check(name, probe) -> HealthCheck` wraps an
  `async () -> None` probe so a failing check still reports its name; all
  W3 checks use it (names `database`, `redis`).

Implemented by workers against these signatures:

- `observatory.core.errors` (W1): `ObservatoryError(code: str, message: str,
  status: int = 400)`; API error body `{"error": {"code", "message",
  "request_id"}}`; validation → 422 `validation_error`; unhandled → 500
  `internal_error` with a generic message (no exception text).
- `observatory.core.logging.configure_logging(settings) -> None` (W1): JSON
  lines (`ts`, `level`, `logger`, `msg`, `request_id`, extra fields) or
  console. Redaction is mandatory and applies to every record:
  - a key is secret if its lower-cased name **contains** any of `password`,
    `passwd`, `secret`, `token`, `api_key`, `apikey`, `access_key`,
    `private_key`, `credential`, `authorization`, `cookie`, `x-api-key`,
    `client_secret`, `dsn`, `database_url`, `redis_url`; its value is
    replaced by `"[REDACTED]"`;
  - applied recursively to nested mappings and sequences in extra fields;
  - credentials embedded in URLs (`scheme://<user>:<password>@host`) are masked in
    every string, including the message and formatted exception/traceback
    text.
- `observatory.api.app.create_app(settings, *, lifespan=None) -> FastAPI` (W1):
  `lifespan` is an optional async context manager factory
  `(FastAPI) -> AsyncContextManager[None]` that creates resources, sets
  `app.state.readiness_checks: Sequence[HealthCheck]`, and closes the
  resources on exit. Endpoints:
  `GET /healthz` → 200 `{"status":"ok"}`;
  `GET /readyz` → runs `app.state.readiness_checks` (default empty) via
  `run_checks`; 200 `{"status":"ready","checks":[{"name","ok"}]}` if all ok,
  else 503 `"not_ready"`; **no checks registered → 503 unless
  `settings.env == "test"`**;
  `GET /version` → `{"service","version","git_sha"}`.
  These three endpoints are the documented exception to "every endpoint is
  authenticated" (security baseline): they expose no secrets, only check
  names, booleans, the version and the git SHA.
  Request-ID middleware accepts an incoming `X-Request-ID` only if it
  `re.fullmatch`es `[A-Za-z0-9-]{8,64}`, else generates a UUID4; echoes it
  in the response header and log records.
- `observatory.db` (W3): `create_engine(settings) -> AsyncEngine` (psycopg 3,
  `postgresql+psycopg://`, `connect_timeout=1`); `database_check(engine) ->
  HealthCheck` (`SELECT 1`). Alembic uses `migration_database_url` (DDL
  role); the application uses `database_url` (DML-only role). All code,
  including Alembic `env.py`, obtains settings via `get_settings()`; direct
  `Settings()` construction outside `config.py` is banned by Ruff (TID251),
  because only `get_settings()` guarantees sanitized errors. No product
  tables in Phase 1; baseline revision `0001_baseline` is empty; exactly one
  head.
- `observatory.cache` (W3): `create_redis(settings) -> redis.asyncio.Redis`
  (`socket_timeout=1`, `socket_connect_timeout=1`); `redis_check(client) ->
  HealthCheck` (`PING`).
- `observatory.main` (Coordinator, AO-P1-006): builds settings, logging, and
  a lifespan that creates engine + Redis client, registers their checks, and
  disposes them on shutdown; nothing is created at import time.

Test ownership: `backend/tests/unit/conftest.py` (W1),
`backend/tests/integration/conftest.py` (W3); no shared root conftest.

### 4. Frontend contract

Node 22, Next.js (App Router), React, TypeScript `strict`, ESLint, Prettier,
Vitest. npm scripts: `lint`, `typecheck`, `format:check`, `test`, `build`.
No product UI and no backend calls in Phase 1.

### 5. Quality gates and CI

One workflow (`.github/workflows/governance.yml`, **no workflow-level
`paths` filters**) runs all jobs:
`governance-core` (existing governance checks), `backend` (ruff check +
format check, mypy --strict, import-linter, pytest unit with coverage
floor, bandit, pip-audit), `backend-integration` (Postgres + Redis services;
Alembic upgrade→downgrade→upgrade, `alembic heads` = 1, integration tests),
`frontend` (npm ci, lint, typecheck, format check, test, build, npm audit
high), `containers` (compose build, up, health). A final aggregator job named
**`governance`** lists every other job in `needs`, runs with `if: always()`,
and fails unless **each** `needs.<job>.result == 'success'` (skipped,
cancelled or failed all fail) — so the ruleset's single required check
covers the whole gate without changing repository settings. A governance
test asserts the aggregator's `needs` covers every job in the workflow.

### 6. Dependency policy

All versions resolved with a cutoff at least two weeks old
(`uv lock --exclude-newer`, `npm install --before`); locks committed; CI
installs strictly from locks (`uv sync --locked`, `npm ci`).

### 7. Tags

The session proxy refuses tag pushes. Tags are created by the reviewed
`release-tags` workflow on `main`: it reads `pending_tags` in
`docs/governance-state.yaml`, creates each listed annotated tag only if the
target commit is on `main` and the tag does not already exist, never moves or
deletes tags, and has no inputs. `commit: self` means "the commit that first
added this entry" (resolved from history, so it is stable across later
pushes). The governance checker refuses a pending `contract-*` tag unless
that contract is `approved` with approving verdicts from both reviewers.
Checkout runs without persisted credentials; the token is given only to the
push. A tag ruleset (no updates/deletions of `phase-*`/`contract-*`) is an
owner setting (TD-016).

## Consequences

- Positive: one frozen seam set lets backend-core, frontend, data/containers
  and governance tooling proceed in parallel with disjoint files.
- Negative: CI runtime grows (several jobs per PR); accepted.
- Changing any frozen interface above needs a superseding ADR (contract
  version bump) and Reviewer B's breaking-change decision.
- Rollback path: revert the Phase 1 merges; Phase 0 tag untouched.

## Review

- Reviewer A: APPROVE_WITH_NOTES · Reviewer B: APPROVE_WITH_NOTES (after two REQUEST_CHANGES rounds) — `docs/reviews/phase-1-contract-review.md`.
