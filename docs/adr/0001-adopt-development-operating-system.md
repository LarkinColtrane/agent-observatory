# ADR-0001: Adopt the development operating system before product work

- Status: accepted
- Date: 2026-10-10
- Deciders: Coordinator
- Components: C12 (Governance), C11 (Platform & tooling)
- Related: A-004, A-005, A-006, TD-001, TD-002

## Context

`agent-observatory` will be built by a multi-agent team (1 coordinator, 5–6
implementers, 2 specialist reviewers, 1 integrator). Without agreed contracts,
parallel agents duplicate work, drift from shared interfaces, over-run
expensive test suites, and report unverified results. The product spans
adapters, an event model, a state engine, and several UIs, so boundaries and
shared contracts matter from the first line of code.

## Options considered

1. **Start building, add process later** — fastest first commit; high risk of
   duplicated abstractions and contract drift that is expensive to unwind.
2. **Governance baseline first (Phase 0)** — small up-front cost; every later
   task has a contract, an owner, a test level, and a review path.

## Decision

Option 2. Phase 0 delivers only governance documents, registers, ADRs, and a
lightweight governance check. No application functionality. Phase 1 opens only
on explicit coordinator decision, starting with a stack-selection ADR and the
universal event model contract.

## Consequences

- Positive: clear ownership, contract-first parallelism, tiered testing that
  controls cost, truthful reporting, rollback paths.
- Negative: L3 gate items (tests, Docker, migrations, failure injection) are
  `n/a` until a stack exists (TD-001).
- Contracts affected: operating, task, and handoff contracts frozen at 1.0.0.
- Rollback path: revert the governance commit; tag `gov-baseline-v1.0.0`
  remains as a historical reference.
