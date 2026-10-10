# P0 Gate Report — Governance

- Phase: P0 · Run 2 (pre-Phase-1 cleanup) · Date: 2026-10-10
- Plan: [P0-plan.md](P0-plan.md) (approves n/a items 1, 3, 4, 6, 7, 9)
- Run by: Coordinator acting as integrator for this docs-only phase. Every row is re-runnable with the command shown.
- Environment: Linux x86_64, Python 3.13, pre-commit 4.6.2, gitleaks 8.21.2 (checksum-verified).
- **Gate decision: NOT PASSED — P0 remains `gate_review`.** Item 12 cannot run until the dedicated repository exists (TD-002).

| # | Check | Command | Ran | Result | Notes |
|---|---|---|---|---|---|
| 1 | Full test suite | — | no | not_applicable | Approved in P0 plan: no application code |
| 2 | Lint | `pre-commit run check-yaml --all-files && pre-commit run check-json --all-files && python3 -I scripts/check-governance.py` | yes | pass | Scope: YAML/JSON syntax + governance lint; no source code exists |
| 3 | Format | — | no | not_applicable | Approved in P0 plan; whitespace/EOL hygiene covered by item 5 |
| 4 | Strict typecheck | — | no | not_applicable | Approved in P0 plan: no typed application code |
| 5 | Pre-commit | `pre-commit run --all-files` | yes | pass | All hooks incl. gitleaks, detect-private-key, governance check, checker tests |
| 6 | Docker | — | no | not_applicable | Approved in P0 plan: no images |
| 7 | Migrations | — | no | not_applicable | Approved in P0 plan: no database |
| 8 | Security checks | `scripts/secret-scan.sh` · `scripts/secret-scan.sh --working-tree` · `pip-audit -r requirements-governance.txt` · `bandit -r scripts/ tests/` | yes | pass | gitleaks full history all refs: no leaks; working tree: no leaks; pip-audit: no known vulnerabilities; bandit: 0 medium/high, 9 LOW (B404/B603/B607: `subprocess` running `git` with list args, no shell — intentional) |
| 9 | Failure injection | — | no | not_applicable | Approved in P0 plan: product failure injection; no product |
| 10 | Independent review | Reviewer A + Reviewer B reviews, then verification of resolutions by the same reviewers | no | not_run | Pending final verdicts — recorded only once they exist in `docs/reviews/pre-phase-1-review-resolution.md` (review N-01/B-16) |
| 11 | Registers | `python3 -I scripts/check-governance.py` · `python3 -I -m unittest discover -s tests/governance -t . -v` | yes | pass | Checker output: `register counts: assumptions=8, debt=6 (open debt=4)`; adversarial tests all pass |
| 12 | Git checkpoint | `git tag -a phase-P0-v1.1.0` + push in `agent-observatory` | no | not_run | Blocked: dedicated repository does not exist (TD-002). No tag created in the practice repository by design (ADR-0004) |

## Adversarial evidence (supporting items 8 and 11)

- **Checker mutation testing:** six deliberately broken checker variants
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

## Migration rehearsal (supporting evidence, not a gate item)

Replayed the project commits onto an empty repository in a scratch directory
using the procedure in `docs/migration/dedicated-repo-migration.md`. Result:
only project files present, author/date/message preserved, clean tree.

## Superseded runs

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
