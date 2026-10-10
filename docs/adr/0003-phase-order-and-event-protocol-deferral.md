# ADR-0003: Phase order and deferral of the universal event protocol

- Status: accepted
- Date: 2026-10-10
- Deciders: Coordinator (proposed); Reviewer A and Reviewer B (sign-off)
- Components: C1, C11, C12
- Related: ADR-0001 (partially superseded), ADR-0002, A-001, A-002, A-003

## Context

ADR-0001 stated that Phase 1 would start with the universal event model
contract. Both independent reviewers (B-05, A-04) showed the failure mode: a
Phase 1 agent following the accepted ADR would design and freeze the event
model before an engineering foundation exists to test it against (no schema
tooling, no storage, no CI). Freezing a contract without the ability to
validate it adversarially invites a breaking change in Phase 3+.

## Decision

1. The phase order is: P0 Governance · P1 Engineering foundation · P2
   Universal agent event protocol · P3 Adapter/SDK layer · P4 Agent state
   engine · P5 Realtime observability · P6 Operations dashboard · P7
   Analytics/scorecards · P8 2D virtual office · P9 External integrations ·
   P10 Control room/workflow graph · P11 Production hardening.
   It is recorded in `docs/governance-state.yaml` and enforced by the
   governance checker.
2. The universal event protocol contract is **not drafted, designed, or
   frozen before Phase 2**. The checker rejects any non-`not_drafted` status
   for it while P2 has not started. Only high-level requirements may be
   recorded earlier (`docs/roadmap.md`).
3. The event protocol is frozen only after adversarial review by both
   reviewers, at the end of Phase 2.
4. This supersedes the Phase 1 scope clause of ADR-0001; the rest of ADR-0001
   stands.

## Consequences

- Positive: the protocol is designed against real tooling and storage; no
  premature freeze.
- Negative: Phase 1 delivers no user-visible capability.
- Provisional statements about event fields/invariants in the security
  baseline and review checklist are marked provisional until P2.
- Rollback path: superseding ADR.

## Review

- Reviewer A: APPROVE_WITH_NOTES · Reviewer B: APPROVE_WITH_NOTES — see `docs/reviews/pre-phase-1-review-resolution.md`.
