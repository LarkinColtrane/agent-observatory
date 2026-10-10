# Phase Quality Gates

Work proceeds in phases. A phase opens only when the coordinator says so and
closes only when its Level 3 gate passes. **Phase 1 has not been opened.**

## Phase register

| Phase | Name | Status | Gate tag |
|---|---|---|---|
| P0 | Development governance baseline | **closed** (review exception, TD-003) | `gov-baseline-v1.0.0` |
| P1 | _To be defined by coordinator_ (expected: universal event model contract + tooling skeleton) | not opened | — |

Phase scope is defined in a phase plan (`docs/phases/P<n>-plan.md`, created
when the phase opens) listing tasks, frozen contracts, and the team roster.

## Level 1 — during development (every change)

| Check | Requirement |
|---|---|
| Affected unit tests | All pass for packages touched |
| Lint | Zero errors on touched files |
| Typecheck | Zero errors on touched packages |

Run by: implementer. Cost: seconds to low minutes. Never run the full suite
at this level.

## Level 2 — before task handoff

| Check | Requirement |
|---|---|
| L1 | Passing |
| Task integration tests | Pass for the task's surface |
| Adversarial tests | Each `adversarial_cases` entry in the task contract has a test that passes |

Run by: implementer, re-run by integrator after merge.

## Level 3 — phase gate (phase closure only)

All items are required unless the phase plan marks one `n/a` with a reason
(e.g. no Docker image exists yet). `n/a` is not the same as "skipped".

| # | Check | Pass criterion |
|---|---|---|
| 1 | Full test suite | 100% pass, no skipped tests without a debt entry |
| 2 | Lint | Zero errors, whole repo |
| 3 | Format | Formatter reports no changes |
| 4 | Strict typecheck | Zero errors in strict mode |
| 5 | Pre-commit | `pre-commit run --all-files` passes |
| 6 | Docker | Images build; containers start and pass health checks |
| 7 | Migrations | Upgrade from empty and from previous gate tag; downgrade tested |
| 8 | Security checks | Secret scan clean; dependency audit no unaccepted high/critical; SAST clean |
| 9 | Failure injection | Adapter disconnect, malformed events, duplicate/out-of-order events, storage unavailable, slow consumer — each degrades safely as specified |
| 10 | Independent review | Phase-level review by both specialist reviewers; no open blocking findings |
| 11 | Registers | `assumptions.yaml` and `technical-debt.yaml` reviewed and current |
| 12 | Git checkpoint | Clean tree, commit, annotated tag `phase-P<n>-v<semver>` pushed |

Run by: integration/validation agent. Signed off by: coordinator.

## Gate report

The integrator writes `docs/phases/P<n>-gate-report.md` with, for each
check: the exact command, whether it ran, the real result, and evidence. A
gate with any `fail`, or any `not_run` that is not an approved `n/a`, does
**not** pass.

## Gate failure

1. Phase stays open; no tag.
2. Failing items become tasks in the same phase.
3. Re-run only the failed items plus anything their fixes touch, then a final
   full L3 run before tagging.
