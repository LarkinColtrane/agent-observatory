# Parallel Work Policy

Goal: maximum throughput **without** duplicate work, merge thrash, or wasted
credits. Parallelism is a tool, not a target.

## Concurrency limits

- Default team: 1 coordinator, 5–6 implementers, 2 specialist reviewers,
  1 integration/validation agent.
- **Maximum 8–10 concurrently active agents.** Going above requires a written
  justification in the phase plan demonstrating that the extra tasks:
  1. have disjoint `owned_paths`,
  2. depend on no unfrozen contract,
  3. will not land in the same integration window as conflicting work.
- Reviewers and the integrator count toward the limit only while active.

## Preconditions for parallel tasks

Two tasks may run in parallel only if **all** hold:

1. Every shared contract they consume is **frozen** (status `frozen` in
   `component-ownership.md`, with a version).
2. Their `owned_paths` are disjoint (no shared files, no shared generated
   outputs, no shared migration sequence numbers).
3. Neither depends on the other's output.
4. Each has its own task contract and branch.

If any precondition fails, the tasks run **sequentially**.

## Contract freeze protocol

1. Coordinator (or a designated contract owner) drafts the contract: schema,
   interface, or event type definition — no implementation.
2. Architecture reviewer + the relevant specialist review it.
3. On approval, the coordinator marks it `frozen@<version>` in
   `component-ownership.md` and commits.
4. Only then may parallel implementation tasks start.
5. Changes to a frozen contract: stop dependent tasks if breaking, write an
   ADR, bump version, notify all consuming owners, then resume.

## Branching and integration

- One branch per task: `ao/<task_id>-<slug>`.
- Implementers never merge to the integration branch themselves; the
  integration agent does, one task at a time, re-running L1/L2 after each.
- Migrations: sequence numbers are allocated by the coordinator in the task
  contract to avoid collisions.
- Integration order follows the `depends_on` graph; ties broken by smallest
  change first.

## Duplicate-work prevention

- Before starting, the owner checks the task board and
  `component-ownership.md` for overlapping scope.
- Before creating any new type/helper/module, the owner searches the codebase
  and ADRs and records the search in the handoff.
- If two agents discover they are solving the same problem, both stop and the
  coordinator picks one owner; the other's work is discarded or folded in.

## Conflict resolution

- Path conflict → coordinator reassigns ownership; the later claimant yields.
- Design disagreement → escalate to architecture reviewer; unresolved →
  coordinator decides and records an ADR.
- Merge conflict at integration → integrator resolves mechanical conflicts;
  semantic conflicts go back to the owners of both tasks.
