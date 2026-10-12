# P1 Gate Report — Engineering foundation

- Phase: P1 · Run 1 · Date: 2026-10-12 · Repository: `LarkinColtrane/agent-observatory` (public)
- Plan: [P1-plan.md](P1-plan.md) (no `not_applicable` items approved; item 9 applies to the foundation's own failure modes)
- Validated commit: `c4e1f2c` (`main`, PR #6 squash merge) — fresh clone of GitHub by an independent validation agent (AO-P1-007) that did not build Phase 1. Its code tree equals the last reviewed AO-P1-006 commit `7c1aa6c` (diff touches only `docs/**`).
- **Gate commit: the commit that adds this report.** It differs from `c4e1f2c` only in `docs/**` (this report, registers, review record, handoff) and one governance-test fixture line (see the tree check below); CI runs on it before the tag is created. The annotated tag `phase-P1-v1.0.0` is created on it by the reviewed `release-tags` workflow (`pending_tags`, `commit: self`); the closure commit then records item 12.
- Environment: Linux 6.18.44 x86_64 · Python 3.12.3 (backend venv, `uv 0.12.18 sync --locked`) · Python 3.13.16 governance venv (pre-commit 4.0.1, PyYAML 6.0.2) · Node v22.22.0 / npm 10.9.4 (repo `.nvmrc` = 22.23.3; `engines` `>=22 <23`) · Docker 29.8.2, Compose v5.6.0 · postgres:16.10-alpine (roles via `deploy/postgres/init/10-ao-roles.sh`), local redis-server 7.0.15 (CI uses redis:7.4.11-alpine) · ruff 0.16.9, mypy 2.3.1, pytest 9.1.1, import-linter 2.15, bandit 1.9.4, pip-audit 2.10.1, alembic 1.20.0, uvicorn 0.53.0, gitleaks 8.21.2 (checksum-verified by the script) · ESLint 9.39.5, tsc 6.0.3, Prettier 3.9.9, Vitest 5.0.1.
- Tree check (Reviewer B's condition for not re-validating): `git diff --name-only c4e1f2c <gate commit>` lists only `docs/**` paths plus one fixture line in `tests/governance/test_check_governance.py` (the pending-tag test now sets P1 `in_progress` itself instead of reading the live register, which the gate moves to `gate_review`). No backend, frontend, compose, deploy, workflow or script file differs. CI runs all jobs on the gate commit; the governance suite, governance checker and artifact checker run in its `governance-core` job.
- **Gate commit: `bb84e30`** (PR #7). CI on it: governance run 38203813639 — all six jobs **success**. Annotated tag `phase-P1-v1.0.0` published on it (item 12).
- **Gate decision: PASSED — P1 closed** (this closure commit records item 12; the tag is never moved).

| # | Check | Command | Ran | Result | Notes |
|---|---|---|---|---|---|
| 1 | Full test suite | `AO_REQUIRE_INTEGRATION=1 pytest -q --cov` (backend, real Postgres 16 + Redis) · `npm ci && npm test` · `python -I -m unittest discover -s tests/governance -t .` | yes | pass | Backend 312 passed, 0 failed, 0 skipped (85.2 s); coverage 98.87% (floor 90%). Frontend 2 files / 10 tests passed. Governance 212 tests OK, 0 skips. No skips anywhere, so no debt entry needed |
| 2 | Lint | `ruff check .` · `npm run lint` (eslint --max-warnings=0) · `python -I scripts/check-governance.py` | yes | pass | ruff "All checks passed!"; eslint exit 0, 0 warnings; checker PASS |
| 3 | Format | `ruff format --check .` · `npm run format:check` | yes | pass | "34 files already formatted"; "All matched files use Prettier code style!" |
| 4 | Strict typecheck | `mypy` (`strict = true`, packages=observatory) · `npm run typecheck` (next typegen + tsc --noEmit) · `lint-imports` | yes | pass | mypy "Success: no issues found in 15 source files" (src only; tests are not typechecked, as in CI); tsc exit 0; import-linter "Contracts: 2 kept, 0 broken" |
| 5 | Pre-commit | `SKIP=no-commit-to-branch pre-commit run --all-files --show-diff-on-failure` | yes | pass | Exit 0; 16 hooks Passed, branch guard Skipped (gate runs on main, as in CI); `git status --porcelain` empty afterwards |
| 6 | Docker | CI-executed: GitHub Actions run 38202285031 (job `containers`, id 114658078770) · local `docker compose --env-file compose.env.example config -q` | yes | pass | CI-executed, run 38202285031 on c4e1f2c: conclusion **success** (all 6 jobs success, aggregator `governance` success). Containers job: backend/migrate/frontend images built from scratch; postgres, redis, frontend, backend Healthy, migrate exited 0; /readyz `ready` with database+redis ok; CSP/nosniff headers; backend uid 10001, frontend uid 1001. Local compose config exit 0. Images not built locally |
| 7 | Migrations | `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` (AO_ENV=test, migration role) · `alembic heads` (line count) | yes | pass | Empty DB (`current` showed no revision) → `0001_baseline (head)` → base → `0001_baseline (head)`, all rc=0; heads=1; history `<base> -> 0001_baseline`. Previous phase tag `phase-P0-v1.1.0` has no database/backend (0 such paths in its tree), so upgrade-from-empty is the upgrade from P0 |
| 8 | Security checks | `scripts/secret-scan.sh` · `scripts/secret-scan.sh --working-tree` · `uv export --locked …` piped to `pip-audit --strict --disable-pip --require-hashes` · `npm audit --audit-level=high` · `bandit -r src` · `git grep`/`git log -p` secret patterns | yes | pass | gitleaks history (all refs): "18 commits scanned … no leaks found"; working tree (incl. .venv, node_modules): no leaks; pip-audit (75 locked pins): "No known vulnerabilities found"; npm audit: 0 vulns (0 high/critical); bandit HIGH 0 / MEDIUM 0 / LOW 0 (856 LOC, 0 nosec; same with --ignore-nosec); no committed secrets (only dummy `u:p@h` fixtures in redaction tests and `change-me-*` placeholders) |
| 9 | Failure injection | `fi.sh` / `fi-config.sh` against a running `uvicorn observatory.main:app` (AO_ENV=dev, real Postgres + Redis) | yes | pass | Foundation modes (P1 plan scope): Redis down → 503 redis=false, healthz 200, back → 200 in 0.01 s; Postgres stop → 503, start → 200 in 0.55 s; pause → 503 at 2.0 s, unpause → 200; malformed X-Request-ID → UUID4, valid echoed; 5 bad configs fail sanitized; 50 concurrent /readyz DB-down: max 1.52 s (stop) / 2.85 s (pause), 0 over 3 s, app alive; 0 password hits in logs. Product modes (adapter disconnect, malformed/duplicate/out-of-order events, slow consumer) **do not exist in P1** (no event pipeline, ADR-0003): not exercised, not passed |
| 10 | Independent review | Phase-level reviews by Reviewer A and Reviewer B on the validated commit and this evidence (`docs/reviews/phase-1-gate-review.md`), on top of the per-task reviews (`docs/reviews/phase-1-task-reviews.md`) | yes | pass | Phase verdicts: A APPROVE_WITH_NOTES, B APPROVE_WITH_NOTES; no BLOCKING or MAJOR finding open. Task verdicts: 002 A APPROVE_WITH_NOTES; 003 B APPROVE; 004 A+B APPROVE_WITH_NOTES; 005 B APPROVE; 006 A APPROVE_WITH_NOTES, B APPROVE |
| 11 | Registers | `python -I scripts/check-governance.py` · `python -I scripts/check-artifacts.py` | yes | pass | Checker PASS: `info: register counts: assumptions=10, debt=22 (open debt=16)`; artifacts PASS: `info: P1-tasks: 7 task(s), 5 handoff(s)` |
| 12 | Git checkpoint | `release-tags` workflow run 38203813651 (`pending_tags`, `commit: self`) · `git ls-remote --tags origin` · `git cat-file -t phase-P1-v1.0.0` · `git rev-parse phase-P1-v1.0.0^{commit}` | yes | pass | Annotated tag `phase-P1-v1.0.0` (object `500c0dc`) → `bb84e30` (gate commit, PR #7 squash merge), message "Agent Observatory Phase 1 engineering foundation, Level 3 gate passed (items 1-11) and signed off by Reviewer A and Reviewer B."; created by the reviewed workflow on 2026-10-12, peeled ref verified by the coordinator against `origin/main`. Clean tree at the gate commit |

## Validator's anomalies and observations (none is a gate failure)

1. **Item 9 scope.** Level 3 item 9 lists product failure modes. P1-plan.md approves no `not_applicable` items and states that item 9 applies to the foundation's own failure modes; the row is `pass` on that scope only. TD-001's description lists "product failure injection" among missing tooling; when TD-001 is marked repaid, the coordinator should state that product failure injection moves to the phases that build the event pipeline.
2. **Item 10.** `phase-1-task-reviews.md` records per-task reviews (final rounds on `dea6e2b`, `08be1a7`, `dbec4aa`, `c35e7c2`, `7c1aa6c`). It records no separate review of the phase as a whole. The merged code equals reviewed `7c1aa6c` (docs-only difference), so the review covers the gate commit's code. Whether that satisfies "both reviewers review the phase" is for the reviewers and coordinator to decide; this agent did not review.
3. **Newline in X-Request-ID over the wire.** Values containing LF, CR or obs-fold are rejected by the HTTP server parser (uvicorn: `400 Bad Request`, "Invalid HTTP request received.", no X-Request-ID header, no injected header) before reaching the app. Replacement by UUID4 for newline-bearing values was shown in-process at the ASGI middleware (4 variants → UUID4). The app kept serving afterwards.
4. **Over-redaction in one error message.** The unencoded-`@` error is logged as `AO_DATABASE_URL: [REDACTED] must be percent-encoded`, because the log scrubber masks the word after "password". This is not a leak, but the message loses its meaning (source text: `password must be percent-encoded`).
5. **Log volume during outages.** One WARNING with traceback is logged per failed probe (101 `health check 0 raised` records during the run). This is already TD-023.
6. `/version` returns `git_sha: null` locally and in the CI compose stack (AO_GIT_SHA unset). Not a gate criterion.
7. Local Node 22.22.0 differs from `.nvmrc` 22.23.3 (engines range satisfied); CI uses `.nvmrc`. Local Redis is 7.0.15, while CI uses 7.4.11.
8. Bad configs are caught at two points. Missing or invalid AO_ENV and prod-without-URLs fail at settings load (`ConfigurationError`, uvicorn rc=1). A bad URL (unencoded `@`, wrong scheme) fails at lifespan startup (rc=3, "Application startup failed"), so the process never serves.

## Evidence appendix (raw lines)

### Clone
```
$ git -C l3/repo rev-parse HEAD
c4e1f2c6583d2e510869c62e962bb2ea988a4c57
pr6 head tree: d893fc328bba76b37c69dfcdda4da4f452d0e3d1  main tree: d893fc328bba76b37c69dfcdda4da4f452d0e3d1
git diff 7c1aa6c c4e1f2c -- backend frontend compose.yaml deploy .github Makefile scripts .pre-commit-config.yaml | wc -l  -> 0
```

### Item 1
```
backend$ AO_REQUIRE_INTEGRATION=1 .venv/bin/pytest -q -p no:cacheprovider --cov -rs
TOTAL                               581      4    124      4    99%
11 files skipped due to complete coverage.        (coverage report, not tests)
Required test coverage of 90.0% reached. Total coverage: 98.87%
312 passed in 85.18s (0:01:25)
pytest rc=0
frontend$ npm ci  -> found 0 vulnerabilities, rc=0
frontend$ npm test
 Test Files  2 passed (2)
      Tests  10 passed (10)
$ python -I -m unittest discover -s tests/governance -t .
Ran 212 tests in 41.743s
OK                                   (0 lines mentioning skip)
```

### Items 2–4
```
$ .venv/bin/ruff check .            -> All checks passed!  rc=0
$ .venv/bin/ruff format --check .   -> 34 files already formatted  rc=0
$ .venv/bin/mypy                    -> Success: no issues found in 15 source files  rc=0   ([tool.mypy] strict = true)
$ .venv/bin/lint-imports            -> Layered architecture (ADR-0005 §2) KEPT / api, db and cache are independent; only main composes (ADR-0005 §2) KEPT / Contracts: 2 kept, 0 broken.
$ npm run lint          -> eslint . --max-warnings=0  rc=0
$ npm run typecheck     -> ✓ Types generated successfully; tsc --noEmit rc=0
$ npm run format:check  -> All matched files use Prettier code style!  rc=0
$ npm run build (extra) -> rc=0, routes / and /_not-found static
```

### Item 5
```
check for added large files....Passed   check for case conflicts....Passed   check for merge conflicts....Passed
check yaml....Passed   check json....Passed   check toml....Passed   detect private key....Passed
fix end of files....Passed   trim trailing whitespace....Passed   mixed line ending....Passed
don't commit to branch....Skipped   Detect hardcoded secrets....Passed   ruff (legacy alias)....Passed
ruff format....Passed   governance check....Passed   task/handoff artifact check....Passed
governance checker adversarial tests....Passed
rc=0 ; git status --porcelain -> (empty)
```

### Item 6 (CI-executed; GitHub API, unauthenticated, plus job log via GitHub connector)
```
run 38202285031 #29 head_sha=c4e1f2c6583d2e510869c62e962bb2ea988a4c57 main push completed/success 04:04:13Z..04:06:31Z
JOB containers id=114658078770 success 04:04:16Z..04:05:25Z   (steps 1-7, 9 success; 8 "Logs on failure" skipped)
JOB governance-core success · frontend success · backend-integration success · backend success · governance (aggregator) success
log: migrate Built / backend Built / frontend Built
log: Container agent-observatory-postgres-1 Healthy · redis-1 Healthy · frontend-1 Healthy · migrate-1 Exited · backend-1 Healthy
log: {"status":"ok"}{"status":"ready","checks":[{"name":"database","ok":true},{"name":"redis","ok":true}]}
log: Content-Security-Policy: ... frame-ancestors 'none' · X-Content-Type-Options: nosniff · (no X-Powered-By)
log: backend uid=10001 · frontend uid=1001
local$ docker compose --env-file compose.env.example config -q  -> rc=0
```

### Item 7
```
$ alembic current (empty DB)  -> (no revision)
$ alembic upgrade head   rc=0   "Running upgrade  -> 0001_baseline"
$ alembic downgrade base rc=0   "Running downgrade 0001_baseline -> "
$ alembic upgrade head   rc=0   -> current: 0001_baseline (head)
$ alembic heads          -> 0001_baseline (head)   count=1
$ alembic history        -> <base> -> 0001_baseline (head), Baseline: empty schema (ADR-0005 §3; no product tables in Phase 1).
$ git ls-tree -r --name-only phase-P0-v1.1.0 | grep -cE '^(backend|.*alembic|.*migrations)'  -> 0
migration password occurrences in alembic output: 0
```

### Item 8
```
$ scripts/secret-scan.sh               -> INF 18 commits scanned. / INF no leaks found  rc=0  (refs: main, origin/main, origin/protection-probe, 2 tags)
$ scripts/secret-scan.sh --working-tree -> INF no leaks found  rc=0
$ uv export --locked --format requirements-txt --no-emit-project -q > requirements-audit.txt   (75 pins)
$ pip-audit --strict --disable-pip --require-hashes -r requirements-audit.txt -> No known vulnerabilities found  rc=0
$ npm audit --audit-level=high -> found 0 vulnerabilities rc=0 ; {'info':0,'low':0,'moderate':0,'high':0,'critical':0}
$ bandit -q -r src -> rc=0 ; JSON totals HIGH 0 MEDIUM 0 LOW 0 loc 856 nosec 0 ; --ignore-nosec: HIGH 0 MEDIUM 0 LOW 0
$ git ls-files / git log --all --name-only: no .env/.pem/.key/id_rsa files ; AKIA/PRIVATE KEY/ghp_/xox/sk-/AIza patterns: 0 (tree and full history)
```

### Item 9 (fi.out, fi-config.out)
```
baseline readyz: 200 {"status":"ready","checks":[{"name":"database","ok":true},{"name":"redis","ok":true}]}
(a) Redis down:  readyz 503 {"status":"not_ready","checks":[{"name":"database","ok":true},{"name":"redis","ok":false}]} ; healthz {"status":"ok"} 200
(a) Redis back:  recovered: 200 after 0.01s, 1 attempt(s)
(b) docker stop: container state exited ; readyz 503 {...database ok:false, redis ok:true} ; healthz 200
(e) burst (DB stopped): n=50 codes={503: 50} min=0.845s median=1.340s max=1.516s wall=1.624s over3s=0 ; healthz after 200
(b) docker start: recovered: 200 after 0.55s, 2 attempt(s)
(b') docker pause: readyz 503 in 2.004s (database ok:false)
(e') burst (DB paused): n=50 codes={503: 50} min=2.493s median=2.725s max=2.846s wall=2.855s over3s=0 ; healthz after 200
(b') docker unpause: recovered: 200 after 0.02s, 1 attempt(s)
(c) valid 'abcDEF12-3456' -> x-request-id: abcDEF12-3456 ; valid 64 chars -> echoed
(c) too short 'abc1234' (7) -> 36cd4906-f736-4891-8cd6-7cbf538eb4b0 ; too long (65) -> a5127ed0-8854-46cc-a828-4c1561a5232f
(c) bad chars 'abcd_efgh;<x>' -> UUID4 ; absent -> UUID4
(c) raw LF / CR / obs-fold in header -> HTTP/1.1 400 Bad Request (server parser), injected header in response: False
(c) ASGI in-process b'abcdefgh\nX-Evil: 1', b'abcdefgh\n', b'\nabcdefgh', b'abcdefgh\r\n' -> UUID4 (all True)
(d) [AO_ENV missing (URLs set)] rc=1 secret_occurrences=0 : ConfigurationError: invalid configuration: env: Field required
(d) [AO_ENV=prod, no URLs] rc=1 secret_occurrences=0 : ... env=prod requires: AO_DATABASE_URL, AO_REDIS_URL
(d) [AO_ENV=prod, DB URL only] rc=1 secret_occurrences=0 : ... env=prod requires: AO_REDIS_URL
(d) [AO_ENV invalid 'staging'] rc=1 secret_occurrences=0 : env: Input should be 'dev', 'test' or 'prod'
(d) [unencoded @ in DB password (dev)] rc=3 secret_occurrences=0 : ConfigurationError: AO_DATABASE_URL: [REDACTED] must be percent-encoded / Application startup failed. Exiting.
(d) [unencoded @ in DB password (prod)] rc=3 secret_occurrences=0 : same
(d) [non-postgres scheme] rc=3 secret_occurrences=0 : AO_DATABASE_URL must use the postgresql or postgresql+psycopg scheme
(d) [alembic, unencoded @ in migration password] rc=1 secret_occurrences=0 : AO_MIGRATION_DATABASE_URL: [REDACTED] must be percent-encoded
    (secret_occurrences counts full values plus 16-char prefixes and the post-'@' fragments)
(f) app.log (241 JSON lines, 0 non-JSON): occurrences of each of 6 throwaway passwords = 0 ; across all 24 workspace logs = 0 ;
    12-char prefix / 12-char suffix of the 3 service passwords = 0 ; postgres container log = 0
app.log record mix: 101 WARNING "health check 0 raised", 2 "health check 1 raised", 2 "1 health check(s) exceeded 2.00s",
    3 "Invalid HTTP request received." ; no ERROR-level records ; graceful shutdown "Application shutdown complete."
```

### Item 10 (quoted from docs/reviews/phase-1-task-reviews.md, final-verdicts block)
```
- Reviewer B final outcome: APPROVE — AO-P1-005 round 2 (c35e7c2, PR #5 head a123eb1)
- Reviewer A final outcome: APPROVE_WITH_NOTES — AO-P1-002 round 3 (dea6e2b)
- Reviewer B final outcome: APPROVE — AO-P1-003 round 2 (08be1a7)
- Reviewer A final outcome: APPROVE_WITH_NOTES — AO-P1-004 round 2 (dbec4aa)
- Reviewer B final outcome: APPROVE_WITH_NOTES — AO-P1-004 round 2 (dbec4aa)
- Reviewer A final outcome: APPROVE_WITH_NOTES — AO-P1-006 round 2 (7c1aa6c)
- Reviewer B final outcome: APPROVE — AO-P1-006 round 2 (7c1aa6c)
Blocking: R-A-002-01, R-A-004-01, R-A-006-01/R-B-006-01, all "fixed". Major: R-B-005-01..03, R-A-002-02/03/201/202,
R-A-004-02..04, R-B-004-01/02/201, all "fixed" (R-B-004-201 via single-flight readiness). No open BLOCKING/MAJOR.
```

### Item 11
```
$ python -I scripts/check-governance.py
required_files: ok / registers: ok / state: ok / adrs: ok / links: ok / secret_patterns: ok
info: register counts: assumptions=10, debt=22 (open debt=16)
info: secret pattern backstop scanned 358 index/history blobs
PASS
$ python -I scripts/check-artifacts.py
info: P1-tasks: 7 task(s), 5 handoff(s)
PASS
```

### Cleanup
`val-l3-pg` removed (`docker rm -f -v`), local redis on the validation port shut down, uvicorn stopped (graceful), no `val-`/`ao-` containers left, daemon untouched; no dangling volume created during the run (all predate 04:05Z). Secret env files deleted.
