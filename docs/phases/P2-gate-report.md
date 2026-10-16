# P2 Gate Report — Universal agent event protocol

- Phase: P2 · Run 1 · Date: 2026-10-16 · Repository: `LarkinColtrane/agent-observatory` (public)
- Plan: [P2-plan.md](P2-plan.md). No `not_applicable` gate items are approved. Item 9 applies to the protocol's own failure modes: there is no running event service until P4. Owner checklist: [P2-closure-checklist.md](P2-closure-checklist.md) (44 items, answered below).
- Validated commit: `8dd71601f51c171e1bd907fcae6c99d3855b2d31` (`main`, PR #11 squash merge). Validated from a fresh clone of GitHub by an independent validation agent (AO-P2-007) that built no part of Phase 2.
  - Code tree check: `git diff af8f58d 8dd7160` touches only six `docs/**` files. No path under backend, frontend, scripts, .github, compose.yaml, deploy, tests or `.pre-commit-config.yaml` differs. So the merged code equals the AO-P2-006 round-3 commit `af8f58d`, which both reviewers approved.
  - Since `phase-P1-v1.0.0`: `frontend/` is unchanged (empty diff), no migration, compose, deploy, workflow or lock file changed, and no dependency was added. The only `backend/pyproject.toml` change adds the `observatory.events` import-linter layer.
- Gate commit: the commit that adds this report, on `p2/007-gate`. It differs from `8dd7160` only in `docs/**`: this report, the AO-P2-007 task contract, handoff and claim, and the coordinator's contract-freeze record. CI runs on it before the phase tag is created.
- Environment: Linux 6.18.44 x86_64.
  - Backend: Python 3.12.3 venv (`uv 0.12.18 sync --locked --python python3.12`; `unicodedata` 15.0.0, which matches the C0 pin).
  - Governance: Python 3.13.16 venv (pre-commit 4.0.1, PyYAML 6.0.2).
  - Frontend: Node v22.22.0 / npm 10.9.4 (`.nvmrc` 22.23.3; `engines` `>=22 <23`).
  - Containers: Docker 29.8.2, Compose v5.6.0, `postgres:16.10-alpine` (roles via `deploy/postgres/init/10-ao-roles.sh`) and local redis-server 7.0.15 (CI uses redis:7.4.11-alpine).
  - Backend tools: ruff 0.16.9, mypy 2.3.1, pytest 9.1.1, coverage 7.16.1, pydantic 2.13.5, import-linter 2.15, alembic 1.20.0, bandit 1.9.4, pip-audit 2.10.1, gitleaks 8.21.2 (checksum-verified by the script).
  - Frontend tools: ESLint 9.39.5, tsc 6.0.3, Prettier 3.9.9, Vitest 5.0.1.
- Contract tag: `contract-event-protocol-v1.0.0` exists on origin as an annotated tag (tag object `5d44cbe`, peeled to `8dd7160`; `git cat-file -t` gives `tag`). It was created by release-tags run 38924710807 (success) with the message "…ADR-0008 with clarifications C0-C26 v1.0.0, frozen after adversarial implementation review (AO-P2-006)…". The validator created no tag.
- **Gate decision: pending phase gate review and item 12.**

| # | Check | Command | Ran | Result | Notes |
|---|---|---|---|---|---|
| 1 | Full test suite | `AO_REQUIRE_INTEGRATION=1 pytest -q -p no:cacheprovider --cov -rs` (backend, real Postgres 16.10 + Redis) · `npm ci && npm test` · `python -I -m unittest discover -s tests/governance -t .` | yes | pass | Backend: 1400 passed, 0 failed, 0 skipped (126.8 s). Coverage 98.74% against the 90% floor; `observatory.events` modules are 96–100%. Frontend: 2 files and 10 tests passed. Governance: 214 tests OK, 0 skips. No skips anywhere, so no debt entry is needed. CI on `8dd7160` (backend-integration) also shows 1400 passed and 98.74% |
| 2 | Lint | `ruff check .` · `npm run lint` (eslint --max-warnings=0) · `python -I scripts/check-governance.py` | yes | pass | ruff "All checks passed!". eslint exit 0 with 0 warnings. Checker PASS |
| 3 | Format | `ruff format --check .` · `npm run format:check` | yes | pass | "71 files already formatted"; "All matched files use Prettier code style!" |
| 4 | Strict typecheck | `mypy` (`strict = true`, packages=observatory, pydantic plugin) · `npm run typecheck` · `lint-imports` | yes | pass | mypy "Success: no issues found in 29 source files" (src only, as in CI). tsc exit 0. import-linter "Contracts: 2 kept, 0 broken"; the layer `observatory.events` sits between api/db/cache and core |
| 5 | Pre-commit | `SKIP=no-commit-to-branch pre-commit run --all-files --show-diff-on-failure` | yes | pass | Exit 0. 16 hooks passed and the branch guard was skipped (the gate runs on main, as in CI). `git status --porcelain` was empty afterwards |
| 6 | Docker | CI-executed: GitHub Actions governance run 38924710919 (job `containers`, id 117053195413) on `8dd7160` · local `docker compose --env-file compose.env.example config -q` | yes | pass | Run 38924710919 on `8dd7160`: conclusion **success**, all 6 jobs success (aggregator `governance` success). Containers job: the stack was built, then postgres, redis, frontend and backend were Healthy and migrate exited. /readyz was `ready` with database and redis ok. The CSP `frame-ancestors 'none'` and nosniff headers were present, with no X-Powered-By. Backend ran as uid 10001 and frontend as uid 1001. Local compose config exit 0. Images were not built locally |
| 7 | Migrations | `alembic current` → `upgrade head` → `downgrade base` → `upgrade head` → `heads` (line count) · `upgrade head` from the P1 head (AO_ENV=test, migration role) | yes | pass | Empty DB (no revision) → `0001_baseline (head)` → base → `0001_baseline (head)`, all rc=0. heads=1. History is `<base> -> 0001_baseline`. P2 adds no migration: 0 alembic or migration paths changed since `phase-P1-v1.0.0`, so the upgrade from the previous phase tag's head is a no-op (rc=0, 0 "Running upgrade" lines). 0 password occurrences in the output |
| 8 | Security checks | `scripts/secret-scan.sh` · `scripts/secret-scan.sh --working-tree` (pristine clone) · `uv export --locked …` piped to `pip-audit --strict --disable-pip --require-hashes` · `npm audit --audit-level=high` · `bandit -q -r src` | yes | pass | gitleaks over all refs: "25 commits scanned … no leaks found". Pristine working tree of `8dd7160`: no leaks. pip-audit (75 hashed pins): "No known vulnerabilities found". npm audit: 0 vulnerabilities (0 high or critical). bandit: HIGH 0, MEDIUM 0, LOW 0 over 2986 LOC. One `# nosec B105` is on the enum value `"secret_detected"`, a false positive shown with --ignore-nosec. `npm audit signatures` could not download locally but passed in CI run 38924710919. The build-artefact noise in a used working tree is listed under anomalies |
| 9 | Failure injection | `fi_protocol.py` and `fi_internal_error.py` (validator's own scripts, outside the repo) against `observatory.events` at `8dd7160` | yes | pass | Protocol modes (P2 plan scope), 505 cases: malformed, encoding, numbers, duplicate keys, depth, 64 KiB edges, future versions, unknown types, identifiers, forbidden characters, 270 secret-bearing cases, 34 usage attacks, `validate_event` tree attacks, skew warnings, and duplicate, conflicting, redelivered and out-of-order sets. 505 of 505 match ADR-0008 §12/§15 (code and disposition), with 0 values echoed. Drop records hold no digest or metadata, and quarantine records carry `sha256:` of the raw bytes. All 15 RejectCodes were observed (`internal_error` by fault injection). Worst 64 KiB case: 155 ms. Service modes (adapter disconnect, storage unavailable, slow consumer) **do not exist in P2**: not exercised and not passed (P4/P5) |
| 10 | Independent review | Phase-level gate review by Reviewer A and Reviewer B on the validated commit and this evidence (after this report) · per-task final verdicts in `docs/reviews/phase-2-reviews.md` and `docs/reviews/phase-2-contract-review.md` | no | not_run | Pending the phase gate review. Recorded final verdicts so far: AO-P2-001 A APPROVE (r3), B APPROVE_WITH_NOTES (r2). AO-P2-002 contract A APPROVE, B APPROVE_WITH_NOTES (r4). C0–C8 A+B APPROVE. AO-P2-003..005/008 implementation and freeze review AO-P2-006 r3 (`af8f58d`) A APPROVE, B APPROVE. No BLOCKING or MAJOR finding is recorded as open. This validator did not review the code |
| 11 | Registers | `python -I scripts/check-governance.py` · `python -I scripts/check-artifacts.py` (on `8dd7160` and on the gate branch) | yes | pass | Checker PASS: `info: register counts: assumptions=11, debt=24 (open debt=16)`. Artifacts PASS: `info: P1-tasks: 7 task(s), 6 handoff(s)` · `info: P2-tasks: 6 task(s), 6 handoff(s)` on `8dd7160`. Gate-branch figures are in the appendix |
| 12 | Git checkpoint | `release-tags` workflow (`pending_tags`, `commit: self`) · `git ls-remote --tags origin` · `git cat-file -t phase-P2-v1.0.0` | no | not_run | Recorded at closure by the coordinator, after the gate commit is merged and the tag is created and pushed |

## Validator's anomalies and observations (none is a gate failure)

1. **Item 9 scope.** Level 3 item 9 lists service failure modes. The P2 plan approves no `not_applicable` items and states that item 9 applies to the protocol's own failure modes. The row is `pass` on that scope only. Adapter disconnect, storage unavailable and slow consumer have nothing to run against until P4/P5.
2. **Proposed debt TD-030 (low): the JSON key-name test omits C20's `pwd` suffix.**
   - The §10.3 key-name test uses ADR-0005's `is_secret_key`. C20 adds "a key whose normalised name ends in `pwd`" only in the text tier's key/value rule.
   - So `{"x-acme": {"MYSQL_PWD": "<value>"}}` is accepted when the value is not credential-shaped (case X.obs.pwdkey). The same pair written as text, `MYSQL_PWD=<value>`, is `secret_detected` (X.obs.pwdtext). The same holds for `db_pwd` and `pwd`.
   - This matches the letter of ADR-0008 (JSON key names follow ADR-0005 rules) but contradicts C20's intent.
   - Mitigations: P3 adapters declare their extension keys statically and Reviewer A reviews them (§11). An unknown top-level key is `schema_violation`, a quarantine with metadata only.
   - Suggested repayment: a secret-rules patch (`SECRET_RULES_VERSION` 2, §16 security exception, Reviewer A sign-off) that applies `_secret_name` to JSON keys. Until then, Reviewer A rejects `*pwd` extension keys in adapter review. The coordinator registers it; the validator cannot edit the register.
3. **Log scrubber scope (item 4).** `core.logging` masks secret-named keys, `key=value` pairs whose key is secret-named, and URL userinfo, exactly as ADR-0005 §3 specifies. A bare credential-shaped token after a non-secret key name (`key=<sk-…>`) passes through log text unchanged. Only `observatory.events` has the credential-shape detectors (by design, §10.3 "independently of `core.logging`"). This is unchanged since P1, so it is not a regression. The owner may want to decide whether logs should adopt the event credential tier.
4. **Two checks were not reached by valid input.**
   - Check 15 (canonical size > 64 KiB, `too_large` quarantine) could not be reached through `parse_event`. Canonical bytes are at most the raw bytes plus 14 (fraction digits on two timestamps), and per-field caps keep a schema-valid event far below 64 KiB. Oversize therefore always ends at check 1 (drop) or check 13. The check is defensive.
   - `internal_error` was observed only by monkeypatching internal helpers (`parse_json`, `inspect_tree`, `canonical_text`) to raise with a secret-bearing message. Each gave `internal_error`/drop, pointer `""`, no digest and no echo.
5. **Expectation corrections in the validator's own script** (recorded so that the cases are not mistaken for implementation findings). On first run, 12 cases differed from the validator's predicted outcome, and each was resolved by reading ADR-0008:
   - An unknown namespace is never echoed in a pointer, so `/extensions`, not `/extensions/x-acme` (§12 pointer rules).
   - Bool, null and unknown token-named keys under `payload.usage` are `secret_detected`: the exemption needs one of the five names **and** a JSON integer (§10.3).
   - `sk-sk-sk-…` is a genuine credential-pattern hit.
   - `mysql -p -p …` with no attached value is not a hit.
   - UTF-16LE (NUL bytes are valid UTF-8) fails at JSON syntax.
   - A 60000-digit literal under 64 KiB is `integer_out_of_range`, answered in 0.8 ms.
   - Depth and extension-depth fixtures had to be rebuilt to the exact container counts (C7).
   - Quarantine digests carry a `sha256:` prefix.

   The final run has 0 mismatches.
6. **gitleaks `--working-tree` on a used tree.** The pristine clone is clean. The validation clone, after tests and `npm run build`, has 12 hits, all in gitignored artefacts:
   - `__pycache__/*.pyc` compiled from tests that build synthetic secrets at run time;
   - `frontend/.next/**` build output (preview and encryption keys that Next.js generates per build; never committed).

   This is consistent with R-A-P2-006-12 (declined: scan a clean tree). The history scan is clean.
7. **Governance state on `main`.** At `8dd7160`, `event-protocol` is still `status: approved`, `tag: null`, although the tag already exists. The coordinator's freeze record (`9d38a45` on the gate branch) sets `frozen` and the tag. The checker passes on both.
8. **Reference trace file order equals `canonical_order`** (59 events, 16 types). This holds for 500 of 500 seeded shuffles and for fully reversed delivery. A whole-trace redelivery classifies as 59 `exact_duplicate`.
9. Local Node 22.22.0 differs from `.nvmrc` 22.23.3 (the engines range is satisfied), and local Redis 7.0.15 differs from CI's 7.4.11. CI uses the pinned versions.
10. Unused pre-allocated register ids: TD-025, TD-028, TD-029, A-014, A-015. Consistent with "use only if needed".

## Owner's 44-item closure checklist

Mapping: "L3 n" is a row of the table above. Case ids such as M01, X.*, U01 and DU01 are rows of the item 9 results (`fi_protocol.py`, see the appendix).

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Phase 1 baseline integrity | pass | `phase-P1-v1.0.0` is an annotated tag (object `500c0dc`, `git cat-file -t` = tag) peeled to `bb84e30`, and `git merge-base --is-ancestor phase-P1-v1.0.0 HEAD` succeeds. P1 is `closed` in governance-state and the checker passes. All P1 suites still pass (L3 1: the 81 integration tests run against real Postgres and Redis). P1 migrations, compose, deploy, workflows, frontend and locks are unchanged since the tag |
| 2 | TD-022 ADR approved | pass | ADR-0007 Status `accepted`, listed in the ADR index. TD-022 `repaid` by AO-P2-001. Reviewer A APPROVE (round 3, `ea7be5b`) and Reviewer B APPROVE_WITH_NOTES (round 2, notes applied) in `phase-2-reviews.md` final verdicts |
| 3 | Safe numeric usage telemetry | pass | `test_telemetry.py` 351 tests pass (L3 1). Validator probe: a typed `UsageMetrics` survives in JSON logs with exact values, while an untyped `prompt_tokens` stays `[REDACTED]`. `UsageMetrics` rejects -1, True, 1.5, "5" and 10^12+1 without echo. Event-side usage attacks U01–U32 match §9 |
| 4 | Secret redaction still effective | pass | `test_logging.py` 153 tests pass. Probe: `password=` in the message, the `password` and `dsn` extras and an untyped token key are all `[REDACTED]`, and secret-named values have 0 occurrences in the log line. `scrub_text` and `redact` work as specified by ADR-0005 §3. The scope limit is in observation 3 |
| 5 | Canonical event envelope | pass | ADR-0008 §2 envelope as frozen `Event` models. All 59 reference-trace lines parse and re-serialise byte-identically. `test_schema.py` golden for `event-protocol-v1.schema.json` passes. Envelope negatives M18–M24 give `schema_violation` |
| 6 | Event taxonomy | pass | 16 types in 10 families (§8), all 16 present in the reference trace. `test_taxonomy.py` 237 tests pass. Unknown and miscased types give `unknown_event_type`/quarantine (V03) |
| 7 | Identity model | pass | §4: v8 accepted only when derived from `provider_event_id` (I10.6, I11 `invalid_reference`, I12 accepted). Cross-workspace squatting of a derived id is rejected (I13). Nil, max, uppercase, v1 and bad-variant UUIDs give `schema_violation` (I10). Entity ids follow Id rules (I01–I09) |
| 8 | Agent hierarchy representation | pass | `agent.spawned` with `parent_agent_id` and the spawner in `scope.agent_id`. The trace holds a coordinator with backend, frontend, testing and security-reviewer agents. Self-parenting gives `invalid_reference` (I15). Unit tests are in `test_taxonomy.py` and `test_review_fixes.py` |
| 9 | Task/dependency representation | pass | `task.created` (`parent_task_id`, `depends_on` sets), `task.dependency_added`, `task.assigned` (handoff) and `task.status_changed` (blocked_by, evidence). Unordered or duplicate sets give `schema_violation` (I16, I17), and 65 deps give `schema_violation` (S11). The trace runs in dependency order |
| 10 | Causality model | pass | `causality.correlation_id` and `causation_id` (§2). `causation_id == event_id` gives `invalid_reference` (I14). Cross-event causal checks are deferred to P4 by contract (§7, §15) |
| 11 | Temporal semantics | pass | §6: offsets, missing Z, leap seconds, years 1999 and 2100, Feb 30, 7 fraction digits and lower-case designators are rejected (M25). 0–6 digits are accepted and canonicalised to 6. Skew and delay are accepted with the `occurred_after_observed` or `late_observation` warning and the timestamp is not rewritten (W01, W02) |
| 12 | Ordering semantics | pass | `canonical_order`: 500 of 500 seeded shuffles and reversed delivery give an identical order (O01, O03). Within a stream, `seq` wins over backwards timestamps (O04). A gap gives a stable order and no invented event (O08). Duplicate ids, two workspaces or a non-Event raise (O05–O07). `test_ordering.py` and `test_properties.py` pass |
| 13 | Schema versioning | pass | §16: `1.1`, `2.0`, `1.0.0`, `1`, `01.0`, `0.9`, a non-string or a missing `spec_version` all give `unsupported_version`/quarantine (V01). The quarantine record keeps only the valid metadata (V01.meta), and an invalid `event_id` is omitted, not echoed (V02) |
| 14 | Extension rules | pass | §11 and C7: 5 namespaces, more than 4 KiB, an array of 33, depth 5, a namespace without the `x-` prefix, or denylisted keys (stdout, prompt) give `schema_violation`. Depth 4 is accepted. `x-acme.thing` is accepted. `x-session.*` gives `schema_violation` (C15) (S08–S10, D08, V03–V06) |
| 15 | Deterministic serialization | pass | §13: `canonical_json(parse(line)) == line` for all 59 lines. Regenerating the trace in a pristine clone is byte-identical (`git status` clean, same SHA-256). Raw input padded to exactly 65536 bytes with whitespace is accepted and canonicalised (S01) |
| 16 | Round-trip tests | pass | `test_properties.py` (6, seeded and bounded) and `test_canonical.py` (16) pass. Validator round-trip of every trace line (B0) |
| 17 | Validation | pass | §12 check order and dispositions: all 15 RejectCodes observed, and 505 of 505 cases match (L3 9). Every quarantine check runs after the secret scan: a secret plus a bad version, or a secret plus a ZWSP, gives a drop (X.order.schema, X.C21). `validate_event` tree attacks (float, None, subclasses, cycles, shared containers, an Event instance, 20000-deep) give a drop (T01–T13, S13) |
| 18 | Duplicate semantics | pass | §15 and C25: `exact_duplicate`, `redelivery` (restart with new observed_at, adapter version, stream and seq; also a provider-derived id), `conflict` (payload or occurred_at changed; reused provider id), `sequence_conflict` and `distinct` (DU01–DU10). Mixed workspaces raise ValueError and non-Events raise TypeError (DU08, DU11, DU12) |
| 19 | Event fingerprints, if adopted | pass | Adopted (§14): `fingerprint` and `content_fingerprint` (C14 `"time":{}`). The redelivery and conflict split rests on `content_fingerprint` (DU02, DU09, DU10). Reviewer B independently derived the fingerprints from ADR-0008 alone and they matched (`phase-2-reviews.md` round 1–3) |
| 20 | Malformed-event rejection | pass | M01–M25, N01–N10 and K01–K04: invalid JSON, non-objects, BOM, invalid, overlong and surrogate UTF-8, floats, NaN and Infinity, `-0`, out-of-range and 60000-digit integers, and duplicate keys (including after escape decoding) all give a drop with no echo |
| 21 | Oversized-event rejection | pass | Raw 65536 bytes accepted and 65537 bytes `too_large`/drop (S01, S02). 10 MiB rejected in 0.04 ms (S03). 100000 `[` gives `too_large` and 30000 `[` gives `too_deep` with no RecursionError (D05, D06). Field caps give `schema_violation` (S05, S11). `validate_event` tree over 64 KiB gives `too_large`/drop (S12) |
| 22 | Malicious identifier tests | pass | Path traversal, absolute, backslash, drive, `%2e`, empty segment, `~`, fullwidth and one-dot-leader dots (NFKC) all give `schema_violation` (I18). Bidi and NUL in ids give `forbidden_character` (I07, I08). Uppercase or `/` in a workspace, a 129-char id, Cyrillic and markup ids give `schema_violation`. Markup in Text is kept verbatim as data (I19, A-013) |
| 23 | Secret-bearing payload tests | pass | 270 cases give `secret_detected`/drop with no digest and no echo: 27 secret shapes in every free-text field (command, query, title, role, display_name, message) and in extension values; credential shapes in ids, `provider_event_id`, paths, tool_name, model, keys and unknown fields; secret-named keys at any depth; NFKC and ZWSP-split variants; `[REDACTED]x` (C18). The negatives `task-42`, `desk-ops` and "Basic authentication enabled" are accepted. Limitation: observation 2 (proposed TD-030) and TD-026/TD-027 |
| 24 | Usage telemetry adversarial tests | pass | U01–U32 (34 rows): negative, bool, string, null, more than 10^12 and 2^53 counts; floats; subset violations; empty or unknown fields; bad, lower-case, non-ISO and XAU currencies (XOF allowed, C16); cost as a number; `estimated_cost` and `pricing_ref` provenance; cumulative/unit_id rules (C9, C12); usage keys outside `payload.usage` give `secret_detected`. `test_telemetry.py` passes |
| 25 | Provider-neutral fixtures | pass | Three synthetic shapes: A (`synthetic-provider-a-transcript.jsonl`), B (`synthetic-provider-b-webhooks.json`) and C (`synthetic-provider-c-agent.json`), each with `"_synthetic": true`. The directory README is headed "SYNTHETIC — no real data". `mappers.py`, `reference.py` and the trace are labelled synthetic, and the `.sha256` file is covered by the README. `test_provider_shapes.py` (10) passes |
| 26 | Deterministic reference trace | pass | `sha256sum` gives `0ee1ee7ee2a475df98f1e9053bd6b97b67ca16fd9ac2052b4bc5004332fa2e4b`, which equals `reference-trace-v1.sha256` (`sha256sum -c` OK) and the test literal `PINNED` in `test_reference_trace.py`. Every line re-serialises identically. Regeneration in a pristine clone is byte-identical |
| 27 | Golden contract tests | pass | `test_golden.py` (5) and `test_schema.py` (6) pass. Reviewer B's independent derivation of canonical bytes, fingerprints, the derived id and the trace digest from ADR-0008 alone matched (AO-P2-006 rounds 1–3) |
| 28 | Security reviewer approval | pass | Reviewer A final outcome: APPROVE for AO-P2-003..005/008 and the AO-P2-006 freeze review round 3 (`af8f58d`, code-identical to `8dd7160`), and APPROVE for the ADR-0008 contract. The phase-level gate review is still pending (L3 10) |
| 29 | Protocol/methodology reviewer approval | pass | Reviewer B final outcome: APPROVE for the AO-P2-006 round 3 (`af8f58d`) implementation and the C0–C26 freeze. The phase-level gate review is still pending (L3 10) |
| 30 | Independent validator approval | pass | This validator's verdict: **PASS_WITH_LIMITATIONS**. L3 items 1–9 and 11 pass. Limitations: item 9 covers the protocol only (no service exists); proposed TD-030; existing TD-026 and TD-027. Items 10 and 12 are not this validator's to pass |
| 31 | Ruff | pass | L3 2 and 3: `ruff check .` "All checks passed!"; `ruff format --check .` "71 files already formatted" |
| 32 | Strict mypy | pass | L3 4: "Success: no issues found in 29 source files" (`strict = true`) |
| 33 | Frontend checks, if the frontend changed | not_applicable | `git diff --stat phase-P1-v1.0.0..8dd7160 -- frontend` is empty, so the frontend did not change in P2. The frontend checks still ran and passed: `npm ci`, test (10), lint, typecheck, format:check, build and `npm audit` (L3 1–4 and 8), plus the CI frontend job |
| 34 | Bandit | pass | L3 8: `bandit -q -r src` rc 0; HIGH 0, MEDIUM 0, LOW 0 over 2986 LOC. The one `nosec B105` is on a code name, as reviewed |
| 35 | Dependency audits | pass | L3 8: pip-audit over 75 hashed pins found no known vulnerabilities, and `npm audit --audit-level=high` found 0. No dependency or lock file changed in P2. `npm audit signatures` passed in CI (local download blocked) |
| 36 | gitleaks | pass | L3 8: history over all refs, 25 commits, no leaks. Pristine working tree: no leaks. CI governance-core secret scan: success |
| 37 | Pre-commit | pass | L3 5: all 16 hooks passed and the tree stayed clean |
| 38 | Docker/CI where applicable | pass | L3 6: CI run 38924710919 on `8dd7160` succeeded in all 6 jobs, including containers, backend-integration and frontend. Local compose config is valid |
| 39 | Fresh-clone validation | pass | Fresh `git clone` of GitHub `main` at `8dd7160`. `uv sync --locked` and `npm ci` ran from the locks, with new Postgres 16.10 and Redis instances and throwaway credentials. No check used the working copy of any other agent |
| 40 | Governance checker | pass | L3 11: `check-governance.py` PASS and `check-artifacts.py` PASS on `8dd7160` and on the gate branch |
| 41 | Debt reconciliation | pass | TD-022 and TD-001 are `repaid` (both blocked P2), so P2 `blocked_by: []`. TD-026 (P11) and TD-027 (blocks P3, listed in P3 `blocked_by`) are recorded with owners and triggers. TD-025, TD-028 and TD-029 are unused. The checker's consistency rules pass. New: TD-030 is proposed in observation 2 for the coordinator to register (it does not block P2) |
| 42 | Assumption reconciliation | pass | A-001 stays `open` (review phase P3) with the P2 synthetic three-shape evidence in its history. Real adapters validate it in P3. A-013 (data-not-instructions) stays `open` for P6, and A-002 and A-003 are unaffected. A-014 and A-015 are unused. The checker validates the register |
| 43 | Rollback instructions | pass | See "Rollback" below. Rehearsed in a scratch clone: reverting the three P2 squash commits in reverse order gives a tree identical to `8b1cce4` (P1 closure), with an empty diff |
| 44 | Recovery tag | not_run | `phase-P2-v1.0.0` is created after the gate commit by the reviewed `release-tags` workflow (`pending_tags`, `commit: self`). The coordinator records it at closure together with L3 12 |

Totals: pass 42 · not_applicable 1 (item 33, reason given) · not_run 1 (item 44) · fail 0. Items 28 and 29 rest on the recorded AO-P2-006 final verdicts. The phase-level review (L3 10) and the phase tag (L3 12, item 44) are still open, so the phase cannot close on this report alone.

## Rollback

From [rollback-policy.md](../rollback-policy.md). Published history and tags are never rewritten. Rollback is by `git revert` through a PR.

- **What P2 added on `main`**, as squash commits after `phase-P1-v1.0.0` (`bb84e30`) and the P1 closure commit `8b1cce4`:
  1. `ce93f44` — AO-P2-001 (ADR-0007, typed usage telemetry, `core/telemetry.py`, logging);
  2. `a3cd5ed` — AO-P2-002 (ADR-0008 contract);
  3. `8dd7160` — AO-P2-003..008 (`observatory.events`, fixtures, reference trace, schema).

  Then come the gate commit (this report) and the closure commit (item 12).
- **Schema first, then code.** P2 added no migration: `alembic heads` is `0001_baseline`, unchanged since P1. There is no downgrade step; verify that `alembic current` = `0001_baseline (head)`.
- **Phase rollback (return to the P1 state):**
  1. Revert the P2 closure and gate commits once they exist, newest first.
  2. Then revert `git revert 8dd7160 a3cd5ed ce93f44`, also newest first.
  3. Merge through a PR and re-run L1/L2 and the full L3 before any new tag.

  The rehearsal (appendix) shows the resulting tree equals `8b1cce4`. That is `phase-P1-v1.0.0` plus the P1 closure's docs and fixture-line update.
- **Task rollback:** reverting only `8dd7160` removes the protocol implementation and keeps ADR-0007 and ADR-0008. Reverting `ce93f44` restores TD-022 behaviour and requires setting TD-022 back to open. The checker then blocks P2 (Reviewer B round 1 showed this).
- **Contract rollback:** a superseding ADR, with every consumer notified. ADR-0008 Rollback says nothing is stored in v1 yet.
- **Tags:**
  - Tags are never moved or deleted. `contract-event-protocol-v1.0.0` (`5d44cbe` → `8dd7160`) and `phase-P1-v1.0.0` (`500c0dc` → `bb84e30`) stay as they are, as does `phase-P2-v1.0.0` once created.
  - A bad tag is superseded by a new tag name.
  - To inspect or rebuild the P1 state without changing `main`: `git checkout phase-P1-v1.0.0`, or `git switch -c restore-p1 phase-P1-v1.0.0`.
- **Recording:** every rollback is recorded in the next handoff or gate report, with what was reverted, why, the commit or tag restored, and the checks re-run.

## Evidence appendix (raw lines)

Raw logs are kept by the validator outside the repository (`gate-p2/evidence/`): uv-sync, npm-ci, item1-backend-pytest, items2-4-backend, frontend, governance-main, item5-precommit, item6-docker, item7-migrations, item8-gitleaks, item8-pyaudit-bandit, item8-npm-audit, item9-failure-injection, item9-results.json, item9-internal-error, item25-synthetic, item26-trace, item33-frontend-diff, item43-rollback-rehearsal, reviewed-vs-main, ci-runs.json, ci-jobs.json, and the scripts `fi_protocol.py`, `fi_internal_error.py` and `probe_logging.py`.

### Clone and baseline
```
$ git clone https://github.com/LarkinColtrane/agent-observatory.git repo ; git rev-parse HEAD
8dd71601f51c171e1bd907fcae6c99d3855b2d31
$ git ls-remote --tags origin
5d44cbe7bd1bab47eec8d27fe33128921a7cac92  refs/tags/contract-event-protocol-v1.0.0
8dd71601f51c171e1bd907fcae6c99d3855b2d31  refs/tags/contract-event-protocol-v1.0.0^{}
500c0dc8bd08e89fa41ae0d6da9d95cfef451b76  refs/tags/phase-P1-v1.0.0
bb84e3073dc24e11a5f56f73487cd3a77a0c8b7d  refs/tags/phase-P1-v1.0.0^{}
(plus contract-phase1-foundation-v1.0.0 -> a8ea522, phase-P0-v1.1.0 -> 8ce0ed3)
$ git cat-file -t contract-event-protocol-v1.0.0 -> tag ; tagger github-actions[bot]
$ git cat-file -t phase-P1-v1.0.0 -> tag ; git merge-base --is-ancestor phase-P1-v1.0.0 HEAD -> ok
$ git diff --stat af8f58d 8dd7160 -> 6 files, all docs/** (adr/0008, governance-state, P2-plan, both P2 review records, technical-debt)
code paths differing (backend frontend scripts .github compose.yaml deploy tests .pre-commit-config.yaml): 0
$ git diff --stat phase-P1-v1.0.0..8dd7160 -- frontend -> (empty)
$ git diff --name-only phase-P1-v1.0.0..8dd7160 -- compose.yaml deploy .github .pre-commit-config.yaml backend/uv.lock frontend/package-lock.json backend/pyproject.toml
backend/pyproject.toml   (import-linter layer observatory.events only)
```

### Item 1
```
backend$ AO_REQUIRE_INTEGRATION=1 .venv/bin/pytest -q -p no:cacheprovider --cov -rs
src/observatory/events/envelope.py  351  8  106  9  96%
src/observatory/events/validation.py 125 1   38  1  99%
TOTAL                               2083     16    542     17    99%
21 files skipped due to complete coverage.        (coverage report, not tests)
Required test coverage of 90.0% reached. Total coverage: 98.74%
1400 passed in 126.84s (0:02:06)
pytest rc=0
collected per file: unit/events 726 (adversarial 116, taxonomy 237, text 122, validation 86, review_fixes 77, ...),
  test_telemetry 351, test_logging 153, integration 81, other unit 89
frontend$ npm ci -> found 0 vulnerabilities rc=0 ; npm test -> Test Files 2 passed (2) / Tests 10 passed (10) rc=0
$ python -I -m unittest discover -s tests/governance -t .
Ran 214 tests in 54.666s
OK
```

### Items 2–4
```
$ .venv/bin/ruff check .            -> All checks passed!  rc=0
$ .venv/bin/ruff format --check .   -> 71 files already formatted  rc=0
$ .venv/bin/mypy                    -> Success: no issues found in 29 source files  rc=0   ([tool.mypy] strict = true)
$ .venv/bin/lint-imports            -> Analyzed 29 files, 67 dependencies. / Layered architecture (ADR-0005 §2) KEPT /
                                       api, db and cache are independent; only main composes (ADR-0005 §2) KEPT / Contracts: 2 kept, 0 broken.
$ npm run lint (eslint . --max-warnings=0) rc=0 ; npm run typecheck rc=0 ; npm run format:check -> All matched files use Prettier code style! rc=0
$ npm run build (extra) rc=0
```

### Item 5
```
check for added large files....Passed  check for case conflicts....Passed  check for merge conflicts....Passed
check yaml....Passed  check json....Passed  check toml....Passed  detect private key....Passed
fix end of files....Passed  trim trailing whitespace....Passed  mixed line ending....Passed
don't commit to branch....Skipped  Detect hardcoded secrets....Passed  ruff (legacy alias)....Passed
ruff format....Passed  governance check....Passed  task/handoff artifact check....Passed
governance checker adversarial tests....Passed
rc=0 ; git status --porcelain -> (empty)
```

### Item 6 (GitHub REST API, unauthenticated; job logs via the GitHub connector)
```
GET /actions/runs?head_sha=8dd71601…  total 3
38924710919 governance  push main 8dd7160 completed success #45 15:32:02Z..15:34:07Z
38924710807 release-tags push main 8dd7160 completed success (job tags success)
38924728813 Graph Update: uv in /backend completed success
JOB frontend 117053194941 success (Install, Lint, Typecheck, Format, Tests, Build, Dependency audit, Registry signatures: success)
JOB backend-integration 117053195334 success (Alembic up/down/up, one head, all tests with real services: success)
JOB containers 117053195413 success (steps 1-7, 9 success; 8 "Logs on failure" skipped)
JOB backend 117053195552 success · governance-core 117053195555 success · governance (aggregator) 117054098869 success
log: postgres-1 Healthy · redis-1 Healthy · migrate-1 Exited · frontend-1 Healthy · backend-1 Healthy
log: {"status":"ok"}{"status":"ready","checks":[{"name":"database","ok":true},{"name":"redis","ok":true}]}
log: Content-Security-Policy: … frame-ancestors 'none' · X-Content-Type-Options: nosniff · X-Frame-Options: DENY
log: backend uid=10001 · frontend uid=1001
log (backend-integration): Total coverage: 98.74% / 1400 passed in 91.74s
local$ docker compose --env-file compose.env.example config -q  -> rc=0
```

### Item 7
```
$ alembic current (empty DB)   -> (no revision) rc=0
$ alembic upgrade head   rc=0   "Running upgrade  -> 0001_baseline, Baseline: empty schema …"
$ alembic downgrade base rc=0   "Running downgrade 0001_baseline -> , …"
$ alembic current        -> (no revision) rc=0
$ alembic upgrade head   rc=0   -> current: 0001_baseline (head)
$ alembic heads          -> 0001_baseline (head)   count=1
$ alembic history        -> <base> -> 0001_baseline (head)
$ git diff --name-only phase-P1-v1.0.0..HEAD, alembic/migrations paths -> 0
$ alembic upgrade head (DB at 0001_baseline = phase-P1-v1.0.0 head) -> rc=0 ; 'Running upgrade' lines: 0 (no-op)
migration password occurrences in output: 0
```

### Item 8
```
$ scripts/secret-scan.sh               -> INF 25 commits scanned. / INF no leaks found  rc=0
     (refs: main, p2/007-gate, origin/main, origin/protection-probe, 4 tags)
$ scripts/secret-scan.sh --working-tree (pristine clone of 8dd7160) -> INF no leaks found rc=0
$ scripts/secret-scan.sh --working-tree (used validation clone, informative) -> rc=1, 12 findings, all gitignored:
     3 in backend/tests/**/__pycache__/*.pyc, 9 in frontend/.next/** build output
$ uv export --locked --format requirements-txt --no-emit-project -q > requirements-audit.txt   (75 pins, 410 hashes)
$ pip-audit --strict --disable-pip --require-hashes -r requirements-audit.txt -> No known vulnerabilities found  rc=0
$ npm audit --audit-level=high -> found 0 vulnerabilities rc=0 ; {'info':0,'low':0,'moderate':0,'high':0,'critical':0,'total':0}
$ npm audit signatures (local) -> npm error Failed to download rc=1   (CI step "Registry signatures and provenance": success)
$ bandit -q -r src -> rc=0 ; JSON totals HIGH 0 MEDIUM 0 LOW 0 loc 2986 results 0
$ bandit --ignore-nosec -> 1 result: B105 LOW events/codes.py:19 'secret_detected' (enum code name)
```

### Item 9 (fi_protocol.py; fi_internal_error.py)
```
cases=505 ok=505 mismatches=0 echoes=0
  baseline 2/2 · malformed 25/25 · malformed-time 10/10 · numbers 18/18 · duplicate-key 4/4 · depth 11/11 · size 13/13
  future-version 10/10 · unknown-type 11/11 · identifier 24/24 · identifier-path 11/11 · forbidden-char 14/14
  secret-text 207/207 · secret-id 14/14 · secret-path 7/7 · secret-key 28/28 · secret-key-observation 1/1 · secret-negative 9/9
  usage-attack 34/34 · validate_event 13/13 · time-skew 2/2 · duplicates 13/13 · out-of-order 8/8 · timing 16/16
outcomes: secret_detected/drop 270 · schema_violation/quarantine 86 · accepted 27 · invalid_json/drop 18 · forbidden_character/quarantine 16
  unsupported_version/quarantine 10 · float_not_allowed/drop 9 · integer_out_of_range/drop 8 · invalid_encoding/drop 6
  unknown_event_type/quarantine 6 · duplicate_key/drop 4 · not_an_object/drop 5 · too_deep/drop 5 · too_large/drop 5 · invalid_reference/quarantine 5
drop records: no raw_sha256, no metadata (asserted per case) ; quarantine records: raw_sha256 == "sha256:" + sha256(raw) (asserted per case)
V01.meta quarantine keeps event_id, workspace_id, event_type, spec_version, provider, adapter, stream_id, seq ; V02 invalid event_id omitted
X.pointer secret at /extensions/x-acme/note -> pointer "/extensions" (namespace key not echoed) ; M23 unknown payload key -> "/payload"
X.obs.pwdkey {"x-acme":{"MYSQL_PWD":<plain>}} -> accepted ; X.obs.pwdtext "MYSQL_PWD=<plain>" -> secret_detected/drop   (observation 2)
W01 occurred_at +17 min -> accepted ['occurred_after_observed'], timestamp kept ; W02 +60 days -> accepted ['late_observation']
DU01 exact_duplicate · DU02 redelivery · DU03 conflict · DU04 conflict · DU05 sequence_conflict · DU06 distinct · DU07 distinct
DU08 ValueError (two workspaces) · DU09 redelivery (derived v8) · DU10 conflict · DU11/DU12 TypeError (non-Event)
O01 500/500 shuffles identical · O02 trace file order == canonical_order · O03 reversed identical · O04 seq beats timestamps [0, 1]
O05 duplicate id ValueError · O06 two workspaces ValueError · O07 non-Event TypeError · O08 gap: 58 events stable · O09 59 exact_duplicate
timing (max of 3 runs, ms): P01 U+FDFA x21k (NFKC x18) 154.6 · P16 64 KiB int array 123.6 · P04 mysql + bare -p 106.2 · P10 -Eu clusters 67.4
  P12 6000 keys 54.2 · P09 Bearer 36.1 · S13 validate_event 20000-deep 29.9 · P14 set password 29.6 · P05 :// + ':' 28.6 · P07 BEGIN 23.3
  N07 60000-digit literal 0.8 · S03 10 MiB 0.04 · S01 65536 B accepted 2.8
internal_error injection: parse_json -> internal_error/drop ptr '' sha None echo=False ; inspect_tree (validate_event) -> same ;
  canonical_text (validate_event) -> same
```

### Items 3–4 (probe_logging.py)
```
secret-named values in JSON log line: 0 (password extra, dsn extra, password= in msg all [REDACTED])
typed usage preserved: {'input_tokens': 1300, 'output_tokens': 300, 'cached_input_tokens': 800, 'reported_cost': {'amount': '0.0123', 'currency': 'USD'}}
untyped prompt_tokens mapping value: [REDACTED] ; redact({'input_tokens': 5, 'api_key': …}) -> both [REDACTED]
UsageMetrics(input_tokens=-1 / True / 1.5 / "5" / 10**12+1) -> rejected, echo=False
bare 'key=<sk-…>' in message text -> not masked (ADR-0005 §3 scope; observation 3)
```

### Items 25–26
```
$ sha256sum tests/fixtures/events/reference-trace-v1.jsonl -> 0ee1ee7ee2a475df98f1e9053bd6b97b67ca16fd9ac2052b4bc5004332fa2e4b
$ sha256sum -c reference-trace-v1.sha256 -> reference-trace-v1.jsonl: OK
tests/unit/events/test_reference_trace.py:19: PINNED = "0ee1ee7ee2a475df98f1e9053bd6b97b67ca16fd9ac2052b4bc5004332fa2e4b"
lines 59 all accepted, re-serialised bytes identical: True ; event types: 16
(pristine clone) python -m tests.fixtures.events.reference -> rc=0 ; git status --porcelain -> (empty) ; same SHA-256
synthetic labels: README "(SYNTHETIC — no real data)" ; provider A/B/C files "_synthetic": true ; mappers.py/reference.py docstrings SYNTHETIC
```

### Item 11 and registers
```
$ python -I scripts/check-governance.py   (8dd7160)
required_files: ok / registers: ok / state: ok / adrs: ok / links: ok / secret_patterns: ok
info: register counts: assumptions=11, debt=24 (open debt=16)
info: secret pattern backstop scanned 515 index/history blobs
PASS
$ python -I scripts/check-artifacts.py    (8dd7160)
info: P1-tasks: 7 task(s), 6 handoff(s)
info: P2-tasks: 6 task(s), 6 handoff(s)
PASS
$ (p2/007-gate, with this report and handoff) check-governance.py -> PASS, same counts ; check-artifacts.py -> PASS,
  info: P1-tasks: 7 task(s), 6 handoff(s) / info: P2-tasks: 7 task(s), 7 handoff(s)
$ (scratch copy, P2 set to gate_review with gate_report = this file) check-governance.py -> the report parses: 12 rows,
  no row error; the only error is "claim AO-P2-007: phase P2 is not in_progress" (the coordinator releases the claim in the gate commit)
```

### Item 43 (rollback rehearsal, scratch clone, never pushed)
```
$ git revert --no-edit 8dd7160 a3cd5ed ce93f44 -> three revert commits
$ git diff 8b1cce4 HEAD -> (empty; 0 lines)
```

### Cleanup
`ao-gate-p2-pg` was removed (`docker rm -f -v`). The local redis on port 56379 was shut down. No `ao-gate-p2` container remains, and the shared daemon was not touched otherwise. The throwaway credential file was deleted, and no password appears in any evidence log.
