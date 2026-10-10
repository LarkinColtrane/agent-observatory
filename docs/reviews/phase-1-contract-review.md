# Phase 1 contract review (ADR-0005)

Coordinator-authored contract: both reviewers must approve before it is
frozen (operating contract §2). Findings and resolutions are recorded below;
final verdicts follow the marker in the form the checker parses.

## Round 1 (commit a604662) — A: REQUEST_CHANGES · B: REQUEST_CHANGES

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| P1A-01 | MAJOR | Redaction key list weaker than baseline; matching unspecified | Case-insensitive **substring** match on 16 keys (incl. `private_key`, `access_key`, `credential`, `x-api-key`, `client_secret`), recursive, URL credentials masked in all strings incl. tracebacks (ADR §3) |
| P1A-02 | MINOR | Health endpoints vs "every endpoint authenticated" | Documented exception in ADR §3 and security baseline (booleans, check names, version, SHA only) |
| P1A-03 | MINOR | Request-ID `$` accepts trailing newline | `re.fullmatch` specified |
| P1A-04 | MINOR | ADR "accepted" before review | Status `proposed` until both verdicts |
| P1A-05 | MINOR | Tags not tied to approval; tags mutable by owner identity | Checker refuses pending `contract-*` tag unless approved with both verdicts (5 tests); tag ruleset = TD-016 (owner) |
| P1A-06 | MINOR | Token persisted during pip | `persist-credentials: false`; token only to tagging step, sent as an auth header (never in a URL) |
| P1A-07 | MINOR | DB roles, env default, URL handling | `migration_database_url` (DDL) vs `database_url` (DML); `env` required (no default); secrets only via `get_secret_value()` at use |
| P1B-01 | MAJOR | W3 depends on W1's `core` | `core/config.py` + `core/health.py` shipped in 001 as real, tested code (18 tests, 100% branch coverage) |
| P1B-02 | MAJOR | No owner for engine/Redis shutdown | `create_app(settings, *, lifespan=None)`; lifespan creates/closes resources and sets `app.state.readiness_checks`; nothing at import |
| P1B-03 | MAJOR | Readiness fails open with no checks | `env=prod` requires DB+Redis URLs; empty checks → 503 unless `env=test` |
| P1B-04 | MINOR | Timing underspecified | Concurrent, one overall deadline, `Exception` only, cancellation cancels pending checks; driver timeouts 1s < 2s; `make_check` keeps names |
| P1B-05 | MINOR | Aggregator rules | `needs.<job>.result == 'success'` for each, no workflow `paths` filters; W4 test asserts coverage |
| P1B-06 | MINOR | Unowned seams | Per-directory conftests; frontend compose service validated in 006; `main.py` claim released on merge |
| P1B-07 | MINOR | Extra freeze PR | `commit: self` (resolved to the commit that introduced the entry) — tag requested in the contract PR itself |
| P1B-08 | NIT | `api` could import `db`/`cache` | Independence contract over `api`/`db`/`cache` (planted import breaks it) |

## Round 2 (commit c8b07bb) — A: REQUEST_CHANGES · B: REQUEST_CHANGES

All round-1 items verified resolved (P1A-05 partial pending owner tag ruleset, TD-016).

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| P1A-08 | MAJOR | `Settings` validation errors echoed the DB password (reproduced); test hid it via truncation | `hide_input_in_errors=True`; `get_settings()` raises a sanitized `ConfigurationError` (field + message only) built outside the `except` block, so no `__cause__`/`__context__` reference to raw inputs; short-URL regression tests over `str`, `repr` and `args`; both fixes mutation-checked |
| P1A-09 / P1B-09 | MINOR / MAJOR | `commit: self` resolved by text search — could hit a comment or `tag:` field | Resolved from **parsed** `pending_tags` per historical version; latest addition wins; must still be present; contract must be approved at that version in that commit; 7 unit tests (comment, `tag:` field, stability, remove/re-add, removed, not-approved, unparseable) |
| P1A-10 | NIT | `required_visibility: private` | `public` |
| P1B-10 | MINOR | Kept audit entries would fail CI after a contract bump | Entries whose tag already exists are skipped by the approval rule; test + mutant |
| P1B-11 | MINOR | A cancellation-ignoring check could hang `/readyz` | Bounded 0.1 s grace after cancel, stragglers abandoned; test with a cancellation-swallowing probe |

<!-- final-verdicts -->
