# ADR-0005: Phase 1 engineering-foundation contract

- Status: accepted
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

`api` → (`db`, `cache`) → `core`. `core` imports none of `api`/`db`/`cache`;
`db` and `cache` do not import `api` or each other. Only `main.py` composes.

### 3. Frozen interfaces (Python)

- `observatory.core.config.Settings` (pydantic-settings, env prefix `AO_`):
  `env: Literal["dev","test","prod"]="dev"`, `service_name: str="agent-observatory"`,
  `log_level: str="INFO"`, `log_format: Literal["json","console"]="json"`,
  `database_url: SecretStr | None`, `redis_url: SecretStr | None`,
  `git_sha: str | None`. `get_settings() -> Settings` (cached).
  Secrets are `SecretStr`; never logged or returned.
- `observatory.core.health`: `CheckResult(name: str, ok: bool)` (frozen
  dataclass); `HealthCheck = Callable[[], Awaitable[CheckResult]]`;
  `async run_checks(checks, timeout_s: float = 2.0) -> list[CheckResult]` —
  each check is time-boxed; exceptions and timeouts become `ok=False`
  (fail closed); details are logged, never returned.
- `observatory.core.errors`: `ObservatoryError(code: str, message: str,
  status: int = 400)`; API error body `{"error": {"code", "message",
  "request_id"}}`; validation → 422 `validation_error`; unhandled → 500
  `internal_error` with a generic message.
- `observatory.core.logging.configure_logging(settings) -> None`: JSON lines
  (`ts`, `level`, `logger`, `msg`, `request_id`, extra fields) or console;
  a redaction filter masks values of secret-like keys (`password`, `secret`,
  `token`, `api_key`, `authorization`, `cookie`, `dsn`, `database_url`,
  `redis_url`) and credentials in URLs.
- `observatory.api.app.create_app(settings, readiness_checks=()) -> FastAPI`:
  `GET /healthz` → 200 `{"status":"ok"}`; `GET /readyz` → 200
  `{"status":"ready","checks":[{"name","ok"}]}` or 503 `"not_ready"`;
  `GET /version` → `{"service","version","git_sha"}`. Request-ID middleware
  accepts an incoming `X-Request-ID` matching `^[A-Za-z0-9-]{8,64}$`, else
  generates a UUID4; echoes it in the response header.
- `observatory.db`: `create_engine(settings) -> AsyncEngine` (psycopg 3,
  `postgresql+psycopg://`); `database_check(engine) -> HealthCheck`
  (`SELECT 1`). No product tables in Phase 1; Alembic baseline revision
  `0001_baseline` is empty; exactly one head.
- `observatory.cache`: `create_redis(settings) -> redis.asyncio.Redis`;
  `redis_check(client) -> HealthCheck` (`PING`).

### 4. Frontend contract

Node 22, Next.js (App Router), React, TypeScript `strict`, ESLint, Prettier,
Vitest. npm scripts: `lint`, `typecheck`, `format:check`, `test`, `build`.
No product UI and no backend calls in Phase 1.

### 5. Quality gates and CI

One workflow (`.github/workflows/governance.yml`) runs all jobs:
`governance-core` (existing governance checks), `backend` (ruff check +
format check, mypy --strict, import-linter, pytest unit with coverage
floor, bandit, pip-audit), `backend-integration` (Postgres + Redis services;
Alembic upgrade→downgrade→upgrade, `alembic heads` = 1, integration tests),
`frontend` (npm ci, lint, typecheck, format check, test, build, npm audit
high), `containers` (compose build, up, health). A final aggregator job named
**`governance`** depends on all of them with `if: always()` and fails unless
every one succeeded — so the ruleset's single required check covers the whole
gate without changing repository settings, and a skipped job can never pass.

### 6. Dependency policy

All versions resolved with a cutoff at least two weeks old
(`uv lock --exclude-newer`, `npm install --before`); locks committed; CI
installs strictly from locks (`uv sync --locked`, `npm ci`).

### 7. Tags

The session proxy refuses tag pushes. Tags are created by the reviewed
`release-tags` workflow on `main`: it reads `pending_tags` in
`docs/governance-state.yaml`, creates each listed annotated tag only if the
target commit is on `main` and the tag does not already exist, never moves or
deletes tags, and has no inputs.

## Consequences

- Positive: one frozen seam set lets backend-core, frontend, data/containers
  and governance tooling proceed in parallel with disjoint files.
- Negative: CI runtime grows (several jobs per PR); accepted.
- Changing any frozen interface above needs a superseding ADR (contract
  version bump) and Reviewer B's breaking-change decision.
- Rollback path: revert the Phase 1 merges; Phase 0 tag untouched.

## Review

- Reviewer A / Reviewer B: see `docs/reviews/phase-1-contract-review.md`.
