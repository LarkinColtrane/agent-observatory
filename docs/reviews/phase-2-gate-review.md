# Phase 2 gate review

Phase-level review of the Phase 2 Level 3 gate evidence
([P2-gate-report.md](../phases/P2-gate-report.md)): the validated commit
`8dd7160` (GitHub `main`, PR #11) and the gate branch `b57f38e`.
- **Reviewer A** covers security and privacy.
- **Reviewer B** covers protocol design, methodology, governance and
  closure.

Both reviewed independently, in their own fresh clones. Per-task and
contract reviews are in `phase-2-reviews.md` and
`phase-2-contract-review.md`.

## Reviewer A (security and privacy): APPROVE_WITH_NOTES

**Re-ran:**
- `git diff af8f58d 8dd7160` touches 6 docs files only, so the merged code
  is the code approved in AO-P2-006 round 3.
- The tag `contract-event-protocol-v1.0.0` is annotated and points at `8dd7160`.
- The validator's `fi_protocol.py` gives 505/505 with 0 mismatches and 0
  echoes, and `fi_internal_error.py` matches the report.
- 1319 unit tests passed. bandit exited 0, and gitleaks found no leaks.
- The governance and artifact checkers pass.
- Not re-run: the 1400-test integration suite. A relied on the report and CI.

Evidence for items 1, 8 and 9 and checklist items 3, 4, 21–24, 28 and 36 is
sufficient and honest. Item 9 is plainly scoped to protocol failure modes.
TD-026, TD-027 and TD-030 are correctly classified, and all three are
acceptable limitations for closing P2.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| GATE-01 | minor | TD-030 is too narrow and rated too low: `passphrase`, `pw`, `privkey`, `session_key`, `signing_key` and `jwt` keys are also accepted | applied: TD-030 widened and raised to medium; it blocks P3; Reviewer A rejects such keys in the P3 adapter review until it is repaid |
| GATE-02 | minor | `core.logging` has no credential-shape detection, so bare `sk-…` or JWT tokens pass in log text | applied: recorded in TD-012 (blocks P3) |
| GATE-03 | nit | An Id-shaped `stream_id` such as `password:x` can reach a quarantine record | already covered by TD-026 |

## Reviewer B (protocol, methodology, governance): APPROVE_WITH_NOTES

**Re-ran:**
- `af8f58d..8dd7160` touches docs only, and so does the gate branch.
- The contract tag is annotated, and the contract is recorded as `frozen` on the gate branch.
- The rollback rehearsal (item 43): reverting the three P2 commits gives a
  tree identical to `8b1cce4`.
- Spot checks: item 1 (1400 passed, 98.74%), item 9 (505 records, all ok),
  and the trace digest against B's independent derivation.

Evidence for L3 items 1, 6, 7, 9 and 11 and checklist items 5–19, 25–27, 29
and 39–44 is sufficient and honest. The scope limits are stated, and items
10, 12 and 44 were left open, not passed. The closure sequence is sound and
mirrors P1.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| B-G-01 | low | The report did not say that v1 freezes with A-001 open on synthetic evidence only | applied: gate report items 30 and 42, and an A-001 history entry (additive P3 needs are a minor version; a breaking need means v2) |
| B-G-02 | low | Observation 3 (log scrubber and credential shapes) needed an owner decision | applied: recorded in TD-012 (blocks P3) |
| B-G-03 | info | ADR-0008's Status line was edited after the freeze tag | accepted as metadata |
| B-G-04 | info | The rollback section should state the contract's governance status after a rollback | applied: `deprecated` (superseded), tags stay |

<!-- final-verdicts -->
- **Reviewer A final outcome:** APPROVE_WITH_NOTES — Phase 2 gate review on `b57f38e` (validated `8dd7160`), notes applied in the gate commit
- **Reviewer B final outcome:** APPROVE_WITH_NOTES — Phase 2 gate review on `b57f38e` (validated `8dd7160`), notes applied in the gate commit
