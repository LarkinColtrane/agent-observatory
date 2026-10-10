# Phase Quality Gates

Work proceeds in phases ([roadmap.md](roadmap.md)). A phase opens only when the
coordinator says so and its predecessor is closed. It closes only when its
Level 3 gate passes. The authoritative phase register is
[`governance-state.yaml`](governance-state.yaml); the governance checker
enforces its consistency with gate reports and the debt register.

## Phase register (summary — see governance-state.yaml)

| Phase | Name | Status |
|---|---|---|
| P0 | Governance | **closed** — `phase-P0-v1.1.0` → `8ce0ed3` |
| P1 | Engineering foundation | **in_progress** — opened 2026-10-10 by owner ([plan](phases/P1-plan.md)) |
| P2 | Universal agent event protocol | not_started |
| P3 | Adapter / SDK layer | not_started |
| P4 | Agent state engine | not_started |
| P5 | Realtime observability | not_started |
| P6 | Operations dashboard | not_started |
| P7 | Analytics / scorecards | not_started |
| P8 | 2D virtual office | not_started |
| P9 | External integrations | not_started |
| P10 | Control room / workflow graph | not_started |
| P11 | Production hardening | not_started |

Phase statuses: `not_started` → `in_progress` → `gate_review` → `closed`.
Each phase has a plan (`docs/phases/P<n>-plan.md`) written when it opens,
listing tasks, frozen contracts consumed, team roster, and any gate items
**approved as not applicable** with reasons. Both reviewers sign off the plan.

## Result vocabulary

Every gate row and handoff check records `ran` and `result`:

| ran | allowed results |
|---|---|
| yes | `pass`, `fail` |
| no | `not_run`, `not_applicable` |

`not_applicable` is valid only if the phase plan approves that item number
(recorded as `approved_not_applicable` in `governance-state.yaml`). A partially
executed check is reported as `fail` with its scope stated, never `pass`.

## Level 1 — during development (every change)

| Check | Requirement |
|---|---|
| Affected unit tests | All pass for packages touched |
| Lint | Zero errors on touched files |
| Typecheck | Zero errors on touched packages |

Run by: implementer. Never run the full suite at this level.

## Level 2 — before task handoff

| Check | Requirement |
|---|---|
| L1 | Passing |
| Task integration tests | Pass for the task's surface |
| Adversarial tests | Each `adversarial_cases` entry in the task contract has a test that passes |
| Migrations (if touched) | Upgrade + downgrade pass; `alembic heads` = 1 |

Run by: implementer; re-run by integrator after merge.

## Level 3 — phase gate (phase closure only)

| # | Check | Pass criterion |
|---|---|---|
| 1 | Full test suite | 100% pass; no skipped tests without a debt entry |
| 2 | Lint | Zero errors, whole repo |
| 3 | Format | Formatter reports no changes |
| 4 | Strict typecheck | Zero errors in strict mode |
| 5 | Pre-commit | `pre-commit run --all-files` passes |
| 6 | Docker | Images build; containers start and pass health checks |
| 7 | Migrations | Upgrade from empty and from the previous phase tag; downgrade tested; exactly one head |
| 8 | Security checks | `scripts/secret-scan.sh` (gitleaks, full history, all refs) clean; dependency audit with no unaccepted high/critical; SAST clean |
| 9 | Failure injection | Adapter disconnect, malformed events, duplicate/out-of-order events, storage unavailable, slow consumer — each degrades safely |
| 10 | Independent review | Both reviewers review the phase; no open BLOCKING/MAJOR findings |
| 11 | Registers | `scripts/check-governance.py` passes; register counts quoted from its output |
| 12 | Git checkpoint | Clean tree; annotated tag `phase-P<n>-v<semver>` created **and pushed** to the dedicated repository (see closure sequence) |

Run by: integration/validation agent. Signed off by: both reviewers (item 10)
and recorded by the coordinator. The coordinator cannot waive any item.

## Gate report

The integrator writes `docs/phases/P<n>-gate-report.md` with one row per item:
`| # | Check | Command | Ran | Result | Notes |`. The checker parses it. A
phase can be recorded `closed` only if every row is `pass` or an approved
`not_applicable`. There is no "closed with exception" state.

Superseded gate runs are kept in the report under a "Superseded runs" heading
(never deleted), with what was wrong.

## Closure sequence (avoids a circular "pushed" record)

1. Gate commit: report with items 1–11 final and item 12 `not_run`; phase
   status `gate_review`.
2. Create the annotated tag `phase-P<n>-v<semver>` on that commit and push it.
3. Follow-up commit: item 12 → `pass` (citing the pushed tag), phase status
   `closed`, `gate_tag` set. The checker verifies the tag exists as an
   annotated tag.

## Gate failure

1. Phase stays in `gate_review`; no tag.
2. Failing items become tasks in the same phase.
3. Re-run failed items plus anything their fixes touch, then a final full L3
   run before tagging.

## Tag convention

- Phase gates: `phase-P<n>-v<semver>` (P0 included).
- Frozen contracts: `contract-<id>-v<semver>`.
- Tags are immutable; a wrong tag is superseded by a new one, never moved.
