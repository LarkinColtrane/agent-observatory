# Parallel Work Policy

Goal: maximum throughput **without** duplicate work, merge thrash, or wasted
credits. Parallelism is a tool, not a target.

## Concurrency limits

- Default team: 1 coordinator, 5–6 implementers, Reviewer A, Reviewer B,
  1 integration/validation agent.
- **Hard limit: 10 concurrently active agents. Target: ≤ 8.** Running more than
  8 requires a written justification in the phase plan demonstrating that the
  extra tasks:
  1. have disjoint claimed paths and no shared hotspot,
  2. depend on no unfrozen contract,
  3. will not land in the same integration window as conflicting work.
- Reviewers and the integrator count toward the limit only while active.

## Preconditions for parallel tasks

Two tasks may run in parallel only if **all** hold:

1. Every shared contract they consume is **frozen** (`status: frozen` in
   `governance-state.yaml`, with a git tag).
2. Their claimed paths are disjoint — no shared files, no path that is a
   prefix of another's, no shared generated output, no shared hotspot.
3. Neither depends on the other's output.
4. Each has its own task contract, branch, and pre-allocated register IDs.

If any precondition fails, the tasks run **sequentially**.

## Path claims

- The **coordinator** records each claim in `governance-state.yaml` (`claims`)
  when assigning a task, and releases it after integration or on a
  non-complete handoff. Implementers never edit claims.
- The governance checker rejects overlapping claims (including prefix overlap).

## Shared-file hotspots

Lockfiles, `pyproject.toml`, `package.json`, Compose files, CI workflows,
`.pre-commit-config.yaml`, the Alembic migration head, and the registers are
**hotspots**. At most one open task may claim a given hotspot per integration
window; others queue behind it. Register IDs are pre-allocated by the
coordinator in task contracts so parallel tasks never mint the same ID.

## Contract freeze protocol

1. A contract author (never the same agent that will approve it) drafts the
   contract: schema, interface, or protocol definition — no implementation.
2. **Reviewer B** (architecture) and the relevant specialist review it. If the
   coordinator authored it, **both** Reviewer A and Reviewer B must approve.
   No single agent may fill both approval roles.
3. On approval, the integrator creates an annotated tag
   `contract-<id>-v<semver>` and the coordinator records `status: frozen`,
   `version`, and `tag` in `governance-state.yaml`.
4. Only then may parallel implementation tasks start against it. Tasks
   reference it as `<path>@<tag>`.

### Changing a frozen contract

1. **Reviewer B decides** whether the change is breaking (escalation to the
   coordinator only on disagreement, recorded in an ADR).
2. Breaking: write an ADR, pause every open task (in progress, in review, or
   queued for integration) that consumes the contract, bump the major version.
3. New tag is created; `governance-state.yaml` records the new version.
4. Every open task consuming the old tag is re-checked by its owner; the
   integrator **rejects any handoff whose `contracts.consumed` tag is
   superseded**, even if its L1/L2 checks pass.

## Branching and integration

- One branch per task: `ao/<task_id>-<slug>`.
- Implementers never merge; the integration agent merges one task at a time,
  re-running L1/L2 after each.
- **Migrations (Alembic):** ordering is the `down_revision` chain, not file
  numbers. Each task sets `down_revision` to the head named in its contract;
  at merge the integrator rebases `down_revision` onto the current head if it
  moved. L2 (after each merge) and L3 require `alembic heads` to report exactly
  one head.
- Integration order follows the `depends_on` graph; ties broken by smallest
  change first.

## Duplicate-work prevention

- Before starting, the owner checks the task board and claims in
  `governance-state.yaml` for overlapping scope.
- Before creating any new type/helper/module, the owner searches the codebase
  and ADRs and records the search in the handoff.
- If two agents discover they are solving the same problem, both stop and the
  coordinator picks one owner; the other's work is discarded or folded in.

## Conflict resolution

- Path conflict → coordinator reassigns the claim; the later claimant yields.
- Design disagreement → Reviewer B; unresolved → coordinator decides and
  records an ADR, which both reviewers sign off.
- Merge conflict at integration → integrator resolves mechanical conflicts
  only; semantic conflicts (including register entries) go back to the owners.
