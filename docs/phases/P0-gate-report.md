# P0 Gate Report — Governance

- Phase: P0 · Run 5 · Date: 2026-10-10 · Repository: `LarkinColtrane/agent-observatory` (private)
- Plan: [P0-plan.md](P0-plan.md) (approves n/a items 1, 3, 4, 6, 7, 9)
- Gate commit: **the commit that adds this run** (the post-migration review fixes). `phase-P0-v1.1.0` is created on exactly this commit after its CI run passes; the closure commit then records the tag, the CI run, and the independent re-validation.
- Run by: coordinator (items 2, 5, 8, 11 below, on the staged gate commit); GitHub Actions `governance` workflow (cited in the closure commit); independent validation agent (clean clone from GitHub of `254e400`: checker PASS, 68 tests OK, gitleaks 8 commits no leaks, pre-commit pass; re-run on the gate commit recorded in the closure commit).
- Environment: Linux x86_64, Python 3.13.16 (local) / 3.12 (CI), pre-commit 4.0.1, PyYAML 6.0.2 (hash-pinned), gitleaks 8.21.2 (checksum-verified).

| # | Check | Command | Ran | Result | Notes |
|---|---|---|---|---|---|
| 1 | Full test suite | — | no | not_applicable | Approved in P0 plan: no application code |
| 2 | Lint | `pre-commit run check-yaml --all-files` · `pre-commit run check-json --all-files` · `python -I scripts/check-governance.py` | yes | pass | check-yaml Passed; check-json Skipped (no JSON files); checker PASS |
| 3 | Format | — | no | not_applicable | Approved in P0 plan; whitespace/EOL hygiene covered by item 5 |
| 4 | Strict typecheck | — | no | not_applicable | Approved in P0 plan: no typed application code |
| 5 | Pre-commit | `SKIP=no-commit-to-branch pre-commit run --all-files` | yes | pass | Exit 0, no files modified (branch guard skipped because the gate runs on `main`, as in CI). CI on this commit: recorded in the closure commit |
| 6 | Docker | — | no | not_applicable | Approved in P0 plan: no images |
| 7 | Migrations | — | no | not_applicable | Approved in P0 plan: no database |
| 8 | Security checks | `scripts/secret-scan.sh` · `scripts/secret-scan.sh --working-tree` · `pip-audit -r requirements-governance.txt` · `bandit -r scripts/ tests/` | yes | pass | gitleaks: "8 commits scanned … no leaks found"; working tree: no leaks; pip-audit: no known vulnerabilities; bandit: HIGH 0, MEDIUM 0 (one B310 found during this run and fixed: https-only API URL), LOW 17 (B603×8, B607×7, B404×2) |
| 9 | Failure injection | — | no | not_applicable | Approved in P0 plan: product failure injection; no product |
| 10 | Independent review | Reviewer A + Reviewer B: initial review, two verification rounds, post-migration review (+ verification of its fixes) | yes | pass | Latest verdicts recorded in `docs/reviews/pre-phase-1-review-resolution.md` |
| 11 | Registers | `python -I scripts/check-governance.py` · `python -I -m unittest discover -s tests/governance -t . -v` | yes | pass | Checker prints `info: register counts: assumptions=8, debt=7 (open debt=4)`; Ran 79 tests … OK |
| 12 | Git checkpoint | `git tag -a phase-P0-v1.1.0` on this commit + `git push origin phase-P0-v1.1.0` | no | not_run | Next step of the closure sequence; recorded by the closure commit |

## Superseded runs

### Run 4 (commit `a1dc2db` — superseded)

**Correction (post-migration review PM-01 / B-28):** row 11 below recorded "Ran 68 tests … OK", but at `a1dc2db` one test (`test_invalid_ran_result_combination`) **failed**; the commit was pushed without gating on the test result. CI run #2 on `a1dc2db` failed accordingly. Fixed forward in `254e400` (no history rewrite). No tag was ever created on `a1dc2db`.

- Phase: P0 · Run 4 · Date: 2026-10-10 · Repository: `LarkinColtrane/agent-observatory` (private)
- Plan: [P0-plan.md](P0-plan.md) (approves n/a items 1, 3, 4, 6, 7, 9)
- Scope: the migrated history (`docs/migration-provenance.md`) plus the gate commit recording the migration. Content of commits 1–5 is tree-identical to run 3's validated commits.
- Run by: coordinator in the dedicated repository (items 2, 5, 8, 11), GitHub Actions `governance` workflow (CI), and an independent validation agent from a clean clone of GitHub (recorded in the closure commit).
- Environment: Linux x86_64, Python 3.13.16 (local) / 3.12 (CI), pre-commit 4.0.1, PyYAML 6.0.2 (hash-pinned), gitleaks 8.21.2 (checksum-verified).
- **Gate decision: items 1–11 complete; item 12 pending** (tag is created on this gate commit, then recorded by the closure commit — see the closure sequence in `phase-quality-gates.md`).

| # | Check | Command | Ran | Result | Notes |
|---|---|---|---|---|---|
| 1 | Full test suite | — | no | not_applicable | Approved in P0 plan: no application code |
| 2 | Lint | `pre-commit run check-yaml --all-files` · `pre-commit run check-json --all-files` · `python -I scripts/check-governance.py` | yes | pass | check-yaml Passed; check-json Skipped (no JSON files); checker PASS |
| 3 | Format | — | no | not_applicable | Approved in P0 plan; whitespace/EOL hygiene covered by item 5 |
| 4 | Strict typecheck | — | no | not_applicable | Approved in P0 plan: no typed application code |
| 5 | Pre-commit | `SKIP=no-commit-to-branch pre-commit run --all-files` (local, on `main`) · CI step "Pre-commit (all files)" | yes | pass | Local exit 0 (branch guard skipped because the gate runs on `main`, as in CI); CI run #1 on `061d004` success |
| 6 | Docker | — | no | not_applicable | Approved in P0 plan: no images |
| 7 | Migrations | — | no | not_applicable | Approved in P0 plan: no database |
| 8 | Security checks | `scripts/secret-scan.sh` · `scripts/secret-scan.sh --working-tree` · `pip-audit -r requirements-governance.txt` · `bandit -r scripts/ tests/` · CI step "Secret scan (full history)" | yes | pass | gitleaks: "6 commits scanned … no leaks found" (entire repository history — no practice-repo commits exist here); working tree: no leaks; pip-audit: no known vulnerabilities; bandit: HIGH 0, MEDIUM 0, LOW 15 (B603×7, B607×6, B404×2; subprocess with list args, no shell); CI secret scan success |
| 9 | Failure injection | — | no | not_applicable | Approved in P0 plan: product failure injection; no product |
| 10 | Independent review | Reviewer A + Reviewer B: initial review, two verification rounds; post-migration review recorded in closure commit | yes | pass | Final verdicts APPROVE_WITH_NOTES (A) and APPROVE_WITH_NOTES (B) recorded in `docs/reviews/pre-phase-1-review-resolution.md` |
| 11 | Registers | `python -I scripts/check-governance.py` · `python -I -m unittest discover -s tests/governance -t . -v` | yes | pass | Checker prints `info: register counts: assumptions=8, debt=7 (open debt=4)`; Ran 68 tests … OK |
| 12 | Git checkpoint | `git tag -a phase-P0-v1.1.0` on this gate commit + `git push origin phase-P0-v1.1.0` | no | not_run | Next step of the closure sequence; recorded by the closure commit |


### Run 3 (temporary session, practice-repository branch — superseded by run 4 after migration)

- Phase: P0 · Run 3 · Date: 2026-10-10
- Plan: [P0-plan.md](P0-plan.md) (approves n/a items 1, 3, 4, 6, 7, 9)
- Run by: **independent integration/validation agent** (not the coordinator) on commits `992eca2` and `368429f`, in its own clone, with its own venv installed via `pip install --require-hashes -r requirements-governance.txt`. Results below are from `368429f`.
- Commit `4b1b7d0` (host-anchored remote check, validation finding N4b) was added after validation; it was verified by the coordinator only (L1: checker PASS with identical counts, 68 tests OK, `pre-commit run --all-files` exit 0, bandit 15 LOW / 0 medium / 0 high).
- Environment: Linux x86_64, Python 3.13.16, pre-commit 4.0.1, PyYAML 6.0.2 (hash-pinned), gitleaks 8.21.2 (checksum-verified).
- **Gate decision: NOT PASSED — P0 remains `gate_review`.** Item 12 cannot run until the dedicated repository exists (TD-002).

| # | Check | Command | Ran | Result | Notes |
|---|---|---|---|---|---|
| 1 | Full test suite | — | no | not_applicable | Approved in P0 plan: no application code |
| 2 | Lint | `pre-commit run check-yaml --all-files` · `pre-commit run check-json --all-files` · `python -I scripts/check-governance.py` | yes | pass | Exit 0/0/0. check-yaml Passed; check-json Skipped (no JSON files exist); checker PASS. Scope: YAML + governance lint only |
| 3 | Format | — | no | not_applicable | Approved in P0 plan; whitespace/EOL hygiene covered by item 5 |
| 4 | Strict typecheck | — | no | not_applicable | Approved in P0 plan: no typed application code |
| 5 | Pre-commit | `pre-commit run --all-files` then `git status --porcelain` | yes | pass | Exit 0; 12 hooks Passed, check-json/check-toml Skipped; porcelain empty; the 4 practice-repo files byte-identical (sha256) before/after |
| 6 | Docker | — | no | not_applicable | Approved in P0 plan: no images |
| 7 | Migrations | — | no | not_applicable | Approved in P0 plan: no database |
| 8 | Security checks | `scripts/secret-scan.sh` · `scripts/secret-scan.sh --working-tree` · `pip-audit -r requirements-governance.txt` · `bandit -r scripts/ tests/` | yes | pass | gitleaks history (all refs): "8 commits scanned … no leaks found", exit 0 (gitleaks skips the 2 practice-repo merge commits; the checker backstop covers all reachable blobs); working tree: no leaks; pip-audit: no known vulnerabilities; bandit: HIGH 0, MEDIUM 0, LOW 15 (B603×7, B607×6, B404×2 — `subprocess` running `git`/`python` with list args, no shell) |
| 9 | Failure injection | — | no | not_applicable | Approved in P0 plan: product failure injection; no product |
| 10 | Independent review | Reviewer A + Reviewer B initial reviews and two verification rounds each | yes | pass | Final verdicts: Reviewer A APPROVE_WITH_NOTES, Reviewer B APPROVE_WITH_NOTES (recorded in `docs/reviews/pre-phase-1-review-resolution.md`); all notes fixed and confirmed by the validation agent |
| 11 | Registers | `python -I scripts/check-governance.py` · `python -I -m unittest discover -s tests/governance -t . -v` | yes | pass | Checker prints `info: register counts: assumptions=8, debt=7 (open debt=6)` on 368429f; Ran 68 tests … OK. After this records commit marks TD-003 repaid, the checker prints `open debt=5` |
| 12 | Git checkpoint | `git tag -a phase-P0-v1.1.0` + push in `agent-observatory` | no | not_run | Blocked: dedicated repository does not exist (TD-002). No tag created in the practice repository by design (ADR-0004); the checker forbids closing P0 outside it |

#### Adversarial evidence (supporting items 8 and 11)

- **Bypass probes (validation agent, 368429f):** Reviewer B's N1–N4 and a
  case-differing claim overlap each FAIL (rc=1) with the expected message;
  the validation agent's own variant N4b initially PASSED and was fixed in
  4b1b7d0 (regression tests added).
- **Migration rehearsal (validation agent):** `format-patch df5f2a0..368429f`
  → `git am` onto an empty `main`: 3 patches applied; path filter printed
  nothing; only project commits with identical author/date/message; clean
  tree; gitleaks "3 commits scanned … no leaks found"; checker PASS and 68
  tests OK in a fresh hash-pinned venv. Tree = 368429f minus exactly the 4
  practice-repo files.

##### Coordinator's earlier adversarial evidence (still valid)

- **Checker mutation testing (final 68-test suite, coordinator):** nine
  broken checker variants — always exit 0; state check removed; secret
  matching disabled; closed-with-unrun allowed; rejecting verdict ignored;
  phase-tag existence skipped; claim case-folding removed; event-protocol
  deferral hard-code removed; HTML-comment stripping removed — each detected
  (72, 36, 14, 1, 1, 2, 1, 1, 1 failing tests).

- **Checker mutation testing (on the 46-test suite):** six deliberately broken checker variants
  (always exit 0; state check removed; secret check removed; secret matching
  disabled; "closed with unrun item" allowed; phase-transition rule disabled)
  were each run against the test suite in a scratch copy. Every mutant was
  detected (48, 17, 11, 10, 1, 1 failing tests respectively).
- **secret-scan.sh:** in a scratch repository, random-format AWS and GitHub
  tokens committed then deleted (history-only) → gitleaks `leaks found: 2`,
  exit 1, values not printed. A low-entropy synthetic key was *not* flagged by
  gitleaks (its entropy filter) — the checker's pattern backstop covers that
  case (test `test_history_only_secret`). Tampered checksum → exit 1, no
  binary installed.



### Run 2 (coordinator self-run on the staged tree — superseded)

Drafted by the coordinator before independent validation. The validation
agent found these errors in it: item 11 quoted `open debt=4` (checker printed
5); item 8 reported bandit "9 LOW" for `scripts/ tests/` (actual 13 then);
environment listed pre-commit 4.6.2 (pinned is 4.0.1); item 2 called a
skipped check-json a pass. Item 10 had been pre-recorded as `pass` before
any verdict existed (review N-01/B-16) and was reverted. Run 3 replaces it.


### Run 1 (2026-10-10, tag `gov-baseline-v1.0.0`, local only — never pushed)

Recorded P0 as "closed with one recorded exception". Independent review found
it invalid (B-01/A-01, B-02/A-02, B-03/A-03):

- item 10 was `not_run`, which the gate rules say fails the gate; there was no
  phase plan approving n/a items;
- item 8 was reported `pass` on a working-tree regex scan only (no history
  scan, no dependency audit/SAST);
- item 9 was reported `pass` for checker tests, which are not the defined
  failure-injection check;
- item 11 reported "2 debt items" when the register held 3.

Original rows (for history; not evaluated by the checker):

    1 Full test suite: n/a · 2 Lint/doc integrity: pass · 3 Format: n/a ·
    4 Typecheck: n/a · 5 Pre-commit: n/a · 6 Docker: n/a · 7 Migrations: n/a ·
    8 Security: pass (regex scan only) · 9 Failure injection: pass (checker
    tests) · 10 Independent review: not_run · 11 Registers: pass ("6
    assumptions, 2 debt items" — actually 3) · 12 Git checkpoint: pass (tag
    local only)
