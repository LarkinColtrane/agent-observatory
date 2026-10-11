# Phase 1 task reviews

Independent, risk-scaled reviews of the Phase 1 task branches (plan:
[P1-plan.md](../phases/P1-plan.md)). Reviewer A covers security and data
integrity; Reviewer B covers concurrency, architecture and governance tooling.
Each section lists the rounds, every finding with its disposition, and the
final verdict. Reviewers did not modify authors' branches; reproductions ran in
their own copies.

## AO-P1-005 — governance tooling (W4; reviewer B)

**Round 1** (`8c2a1b6..a898954`) — REQUEST_CHANGES. Passed: checker PASS, hostile
YAML (alias bomb, python tags, binary, 50k nesting, directory named like a task
file) all exit 1 cleanly, usage errors exit 2; the AO-P1-006 aggregator judged
correct by eye.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-005-01 | major | aggregator "success-only" check was a substring heuristic; 5 never-failing aggregators passed | fixed: the aggregator step is executed against synthetic `needs` (success, failure, cancelled, skipped, empty) |
| R-B-005-02 | major | `continue-on-error` on a member job not rejected | fixed: rejected anywhere (job and step level) |
| R-B-005-03 | major | unregistered or `..`-aliased contract refs passed | fixed: normalised path, registered contract, equal tag |
| R-B-005-04 | minor | list fields given as strings; empty nested strings passed | fixed |
| R-B-005-05 | minor | `complete` with no L1 check that ran passed | fixed |
| R-B-005-06 | minor | task-id phase not compared with directory | fixed |
| R-B-005-07 | minor | `owned_paths: ["."]` passed | fixed: normalised paths only |
| R-B-005-08 | minor | pre-aggregation skip could become a permanent escape hatch | coordinator: removed in AO-P1-006 (acceptance criterion) |
| R-B-005-09 | minor | checker stricter than the task-contract template (`<path or glob>`) | coordinator: template amended; task-contract version 1.1.0 → 1.1.1 (R-B-005-14) |
| R-B-005-10 | nit | duplicate YAML keys silently accepted | fixed: strict loader rejects them |
| R-B-005-11 | nit | small divergences between task files and P1-plan.md | coordinator: plan updated |
| R-B-005-12 | nit | 32 s subprocess-heavy test file | fixed: in-process tests, 6.6 s |

**Round 2** (`a898954..c35e7c2`, PR branch at `a123eb1`): all 19 saved
adversarial cases now fail cleanly; workflow counterexamples C1–C6, C9, C10 and
new D1–D5 rejected, control D6 passes; 203 governance tests OK (1 skip, removed
in AO-P1-006); the AO-P1-006 workflow passes the executed aggregator test.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-005-13 | nit | a step written to detect the host vs the runner could pass the executed test | accepted: deliberate subversion is for code review; no change |
| R-B-005-14 | nit | template changed in place without a contract version bump | fixed: task-contract 1.1.1 |

## AO-P1-002 — backend core (W1; reviewer A, specialist security)

**Round 1** (`8c2a1b6..0f9f821`) — REQUEST_CHANGES. Passed: request-id fullmatch
and UUID4 fallback, readiness rules, generic error bodies, masking of exception
chains, `stack_info`, `exc_text` and orphaned tasks; a real uvicorn run was fully
JSON-redacted; 27 mutants killed.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-002-01 | blocking | URL mask stopped at `/`: `postgresql://u:ab/LEAK@h/db` leaked | fixed |
| R-A-002-02 | major | key-family test parametrised over the implementation's own tuple | fixed: literal ADR list |
| R-A-002-03 | major | `?token=` in uvicorn access logs logged verbatim (real server) | fixed: key/value text scrubber |
| R-A-002-04 | minor | secrets in reprs, dict-in-exception text, libpq DSNs | fixed (same scrubber) |
| R-A-002-05 | minor | non-str messages containing mappings not redacted | fixed |
| R-A-002-06 | minor | `Api-Key`/`privateKey`/`databaseUrl`/`auth`/header tuples leaked | fixed: normalised keys, exact `auth`, pairs |
| R-A-002-07 | minor | warnings, excepthooks and SQLAlchemy echo bypassed the handler | fixed; echo/hide_parameters in AO-P1-004 |
| R-A-002-08 | nit | single masking layers removable undetected | fixed: per-layer tests |
| R-A-002-09 | nit | console CR/LF forging; NaN produced invalid JSON | fixed |

**Round 2** (`0f9f821..eb09c11`) — REQUEST_CHANGES. All round-1 findings
confirmed fixed; 45/45 mutants killed.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-002-201 | major | unanchored scrubber: 1 MB in 3.1 s; a 15 KB path cost ~150 ms per request | fixed: anchored possessive key; 1 MB in ~15 ms |
| R-A-002-202 | major | secrets over 256 chars leaked their tail (JWT signature) | fixed: no length cap |
| R-A-002-203 | minor | multi-pair Cookie, PEM bodies, list-of-lists headers | fixed |
| R-A-002-204 | minor | `sys.unraisablehook` not routed | fixed |
| R-A-002-205 | minor | contract's `token` substring hides usage metrics (`prompt_tokens`) | coordinator: TD-022 (blocks P2) |
| R-A-002-206 | nit | escaped quotes; tab in userinfo | (b) fixed; (a) accepted |

**Round 3** (`eb09c11..dea6e2b`) — APPROVE_WITH_NOTES. 59 mutants, 58 killed;
the survivor (non-possessive key) proven equivalent by a 200k-string
differential test; 13 hostile inputs scale linearly from 1 to 4 MB.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-002-301 | minor | column-aligned values (4+ spaces) leak | TD-012 (blocks P3) |
| R-A-002-302 | minor | JSON-escaped keys inside strings leak | TD-012 |
| R-A-002-303 | nit | PGP private key blocks | TD-012 |
| R-A-002-304 | nit | value already starting with `[REDACTED]` skipped | TD-012 |

Documented limits accepted by Reviewer A: scheme-less `user:pw@host`, CLI
`--password X`, URL-encoded `password%3DX`, pydantic `input_value`, unquoted
values containing spaces.

## AO-P1-003 — frontend (W2; reviewer B)

Before review: `npm audit` reported 8 highs. Fixes newer than the cutoff were
taken under ADR-0006; `braces` (no fix) was removed with `eslint-config-next`
(TD-013).

**Round 1** (`8c2a1b6..258ff20`) — APPROVE_WITH_NOTES. Registry publish times
checked for all 442 lock entries: only ADR-0006 rows are newer than the
cutoff, each the minimal fix; production security headers verified on a
standalone build.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-003-01 | minor | CSP `isDev` failed open for non-production NODE_ENV builds | fixed |
| R-B-003-02 | minor | no test of headers/CSP | fixed: next.config tests (catch the old bug) |
| R-B-003-03 | minor | `node:22-alpine` mutable tag | fixed: version + digest |
| R-B-003-04 | minor | runtime could rewrite its bundle; npm/corepack kept | fixed |
| R-B-003-05 | minor | `unsafe-inline`; no HSTS/Permissions-Policy | TD-017 (blocks P6) |
| R-B-003-06 | nit | `vitest` watch mode | fixed |
| R-B-003-07..10 | minor | ADR-0006 wording, lapse rule, mechanism, acceptance timing | coordinator: ADR-0006 revised; TD-018 |

**Round 2** (`258ff20..08be1a7`) — APPROVE. Remaining nits: R-B-003-11
(`.nvmrc` vs image Node version; fixed in AO-P1-006), R-B-003-12
(`npm audit signatures` cannot run in the session; enforced in CI).

## ADR-0006 — security-patch exception

Reviewer A: APPROVE_WITH_NOTES (keep the removal condition, attach the lock
diff, provenance check, no fast path — all applied). Reviewer B: APPROVE.

## AO-P1-004 — data + containers (W3; reviewers A and B; CRITICAL)

**Round 1** (`8c2a1b6..c4b9adb`) — A: REQUEST_CHANGES; B: REQUEST_CHANGES.
Held: no passwords in server logs with `log_statement=all`; idempotent
bootstrap; secrets via psql `\getenv` only; Alembic version table invisible to
the app role; single-transaction, advisory-locked migrations; fail-closed
probes under black-hole, paused and partitioned services with no leaked
connections; non-root images without uv or dev packages.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-004-01 | blocking | failed first init + restart left Postgres healthy with the placeholder superuser password and no roles | fixed: superuser password validated; completion marker + `--check` healthcheck; failed-init tests |
| R-A-004-02 | major | unencoded `@` put a password fragment in the host (logged) | fixed: rejected, sanitized error |
| R-A-004-03 | major | weak / case-variant / unsafe-charset passwords accepted | fixed: `[A-Za-z0-9_-]{16,}`, no "change"; claim narrowed |
| R-A-004-04 | major | no role-membership or bootstrap-script tests | fixed: membership, `SET ROLE` denied, 17 script cases |
| R-A-004-05 | minor | app role could reach postgres/template1, TEMP there, large objects | fixed: revoked; ownership test covers large objects |
| R-A-004-06 | minor | migrate cannot run with `AO_ENV=prod` under least privilege | TD-019 (blocks P11) |
| R-A-004-07 | minor | secrets visible via `docker inspect` | accepted for local dev; TD-020 (blocks P11) |
| R-A-004-08 | minor | Redis without AUTH/TLS | accepted for P1; TD-021 (blocks P11) |
| R-A-004-09 | nit | libpq 2 s `connect_timeout` floor | documented; A-011 |
| R-A-004-10 | minor | postgres/redis containers not hardened | fixed (redis verified in CI `containers` job) |
| R-A-004-11 | minor | Alembic `fileConfig` bypassed redaction | coordinator: `env.py` uses `configure_logging` |
| R-A-004-12 | nit | pip/setuptools in runtime image; empty `AO_GIT_SHA` | fixed |
| R-B-004-01 | major | concurrent-migrators test passed with the lock removed | fixed: deterministic held-lock test (fails without the lock) |
| R-B-004-02 | major | unbounded Redis pool behind unauthenticated `/readyz` | fixed: pool cap 16 |
| R-B-004-03 | minor | cancellation tested before any I/O | fixed: in-flight cancellation (slot released after psycopg's fixed ~10 s) |
| R-B-004-04 | minor | "1 s" connect timeout is really 2 s | documented; A-011 |
| R-B-004-05 | minor | `to_psycopg_url` added to the frozen db surface | kept; declared as an addition |
| R-B-004-06 | minor | migrator waits on the advisory lock forever | fixed: `SET LOCAL lock_timeout` (60 s, `-x` override) |
| R-B-004-07 | nit | tight timing slack; closed-port race | fixed |
| R-B-004-08 | nit | duplicate compose build; uv version mismatch | accepted; uv aligned at 0.12.18 |

**Round 2** (`c4b9adb..dbec4aa`) — A: APPROVE_WITH_NOTES; B:
APPROVE_WITH_NOTES. A verified the failed-init path end to end through
`compose.yaml` (unhealthy, dependants never start) and re-ran the membership
mutant (now caught); B verified each fix by mutation.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-004-201 | major | capped Redis pool makes >16 concurrent `/readyz` report a healthy instance not ready | coordinator: single-flight readiness in `main.py` (tests: 100 concurrent → all 200, one probe per service) |
| R-B-004-202 | nit | lock test infers waiting from a sleep | accepted |
| R-B-004-203 | nit | shared Redis cap will need revisiting for real traffic | accepted; revisit when Redis carries load |
| R-A-004-201 | nit | failed-init Postgres keeps running (unhealthy, unpublished) | accepted (documented `down -v`) |
| R-A-004-202 | nit | `@` in username accepted | coordinator: rejected, with test |
| R-A-004-203 | nit | migrator can rewrite the completion marker | accepted (roles still required) |
| R-A-004-204 | minor | redis hardening not run locally | verified by CI `containers` job |

<!-- final-verdicts -->
- **Reviewer B final outcome:** APPROVE — AO-P1-005 round 2 (`c35e7c2`, PR #5 head `a123eb1`)
- **Reviewer A final outcome:** APPROVE_WITH_NOTES — AO-P1-002 round 3 (`dea6e2b`)
- **Reviewer B final outcome:** APPROVE — AO-P1-003 round 2 (`08be1a7`)
- **Reviewer A final outcome:** APPROVE_WITH_NOTES — AO-P1-004 round 2 (`dbec4aa`)
- **Reviewer B final outcome:** APPROVE_WITH_NOTES — AO-P1-004 round 2 (`dbec4aa`)
