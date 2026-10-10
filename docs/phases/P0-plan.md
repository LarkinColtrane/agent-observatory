# P0 Plan — Governance

- Phase: P0 · Opened: 2026-10-10 (retroactively documented during pre-Phase-1 cleanup, per review B-01/A-01)
- Scope: development operating system — governance documents, registers, ADRs, governance tooling (checker, adversarial tests, secret scanning, pre-commit, CI skeleton), repository isolation decision. **No application functionality.**
- Team: Coordinator (author) · Reviewer A (security + data integrity) · Reviewer B (concurrency + architecture) · independent integration/validation agent (gate run and migration rehearsal).
- Contracts produced: operating, task, handoff contracts v1.1.0 — `approved` once both reviewers' final verdicts are recorded; `frozen` when tagged `contract-<id>-v1.1.0` in the dedicated repository.
- Sign-off: Reviewer A and Reviewer B (see `docs/reviews/pre-phase-1-review-resolution.md`).

## Gate items approved as not applicable

Recorded in `governance-state.yaml` (`approved_not_applicable`) and enforced by
the checker. Each becomes applicable in Phase 1 (TD-001).

| # | Item | Reason not applicable in P0 |
|---|---|---|
| 1 | Full test suite | No application code. The only code is governance tooling, whose tests run under item 11. |
| 3 | Format | No source language formatter applies to docs/YAML; whitespace/EOL hygiene runs in pre-commit (item 5). |
| 4 | Strict typecheck | No typed application code. |
| 6 | Docker | No images or services exist. |
| 7 | Migrations | No database or Alembic history exists. |
| 9 | Failure injection | Defined as product failure injection (adapter disconnect, malformed events, storage loss); no product exists. Checker adversarial tests are reported under item 11, not here (review B-03). |

Items 2, 5, 8, 10, 11, 12 **are applicable** and must pass for P0 to close.
