# Development Operating Contract — agent-observatory

Status: **Active** · Version: 1.1.0 · Owner: Coordinator
Machine-checked state: [`governance-state.yaml`](governance-state.yaml) · Validate: `python3 -I scripts/check-governance.py`

This is the top-level contract for how `agent-observatory` is built. Every other
governance document in `docs/` is a detail of this one. If two documents
disagree, this file wins, then the more specific document.

## 1. Product context (for orientation only)

`agent-observatory` will be a universal observability platform for agentic
workspaces. It will connect to many agent systems through **adapters**,
normalize their activity into one **universal event protocol**, derive
**agent / workflow state**, and present it through **dashboards, timelines,
dependency graphs, and a 2D virtual office**.

It is a separate project from Quant Autonomy and lives in its own dedicated
private repository ([ADR-0004](adr/0004-dedicated-private-repository.md)). No
code, contracts, secrets, or infrastructure are shared with any other project
unless an ADR says so.

Phase order is defined in [roadmap.md](roadmap.md) and
[ADR-0003](adr/0003-phase-order-and-event-protocol-deferral.md). The universal
event protocol is designed and frozen in **Phase 2**, never earlier. Phase 1 is
the engineering foundation.

## 2. Team model

| Role | Count | Responsibility |
|---|---|---|
| Coordinator | 1 | Plans phases, writes task contracts, records path claims, pre-allocates register IDs, owns Git checkpoints. **Never approves its own work.** |
| Implementation agents | 5–6 | Execute one task contract each, writing only inside their claimed paths. |
| Reviewer A | 1 | Independent specialist review: **security + data integrity**. |
| Reviewer B | 1 | Independent specialist review: **concurrency + architecture**. |
| Integration / validation agent | 1 | Sole merger to `main` (squash-merged pull requests, one at a time); runs L2/L3, failure injection; writes gate reports. |

**Separation of duties.** One agent holds one role at a time. No agent reviews,
integrates, or approves work it authored. Anything the coordinator authors
(contracts, governance changes, ADRs) requires sign-off from **both** Reviewer A
and Reviewer B. A gate is closed only after the integrator's gate report shows
it passing; the coordinator cannot waive a failing or unrun gate item.

**Concurrency limit: at most 10 concurrently active agents** (target ≤ 8).
Exceeding the target of 8 requires a written justification in the phase plan
showing the extra tasks are genuinely independent; exceeding 10 is not allowed
without an ADR. See [parallel-work-policy.md](parallel-work-policy.md).

## 3. Non-negotiable rules

1. **Inspect before editing.** Read the files, contracts, and ADRs you will
   touch before changing them. Record what you inspected in the handoff.
2. **Contract-first.** Interfaces, schemas, and event types are written and
   reviewed before implementations.
3. **Freeze shared contracts before parallel work.** A shared contract is
   frozen (git tag + path, recorded in `governance-state.yaml`) before two or
   more agents build against it. Changing a frozen contract requires an ADR
   and sign-off by both reviewers.
4. **Small task ownership.** One task = one owner = one claimed set of paths.
   Target ≤ ~400 changed lines of non-generated code per task.
5. **No duplicate work.** The coordinator records every claim before work
   starts; claims never overlap. Check claims and the task board first.
6. **Structured handoffs.** Every task ends with a handoff matching
   [agent-handoff-contract.md](agent-handoff-contract.md). No handoff = not done.
7. **Independent review** for every change to code, configuration, CI,
   dependencies, **and every governance file** (all of `docs/` except typo-only
   fixes in non-governance prose). Authors never approve their own work.
8. **Specialist review** is mandatory for changes touching security,
   concurrency, data integrity, or architecture, and for every governance
   document change (Reviewer A or B, as relevant; both for this contract).
9. **Targeted tests during development** (Level 1/2). **Full suite only at
   phase closure** (Level 3).
10. **Search before creating abstractions.** Search code and ADRs for an
    existing type, helper, or pattern first. Prefer reuse; record the search.
11. **Fail safely.** Unknown input, adapter failure, or partial data degrades
    to an explicit "unknown/degraded" state — never a crash or silently wrong
    state. Sensitive data fails closed (see security baseline).
12. **Never claim a check ran unless it actually ran.** Report the exact
    command and its real result. `not_run` and `not_applicable` are honest
    answers; a fabricated or unverified `pass` voids the task or gate.
13. **Git checkpoints.** Commit at every task completion; annotated tag at
    every phase gate. See [rollback-policy.md](rollback-policy.md).
14. **Secrets are never committed or logged.** See
    [security-baseline.md](security-baseline.md).

## 4. Shared files (write protocol)

Some files are written by many tasks. To prevent races and duplicate IDs:

- **Registers** (`assumptions.yaml`, `technical-debt.yaml`): the coordinator
  pre-allocates IDs in each task contract (`allocated_ids`). A task may only
  add entries using its allocated IDs. Edits to existing entries go through
  the coordinator.
- **`governance-state.yaml`** (claims, phases, contracts): coordinator only.
- **Single-file hotspots** (lockfiles, `pyproject.toml`, `package.json`,
  Compose files, CI workflows, Alembic head): at most one open task may claim
  each per integration window; others queue.

## 5. Testing levels

| Level | When | Scope |
|---|---|---|
| **L1** | Every change, during development | Affected unit tests + lint + typecheck for touched packages |
| **L2** | Before handoff of a task | Task integration tests + adversarial/edge-case tests for the task's surface |
| **L3** | Phase closure only | Full tests, lint, format, strict typecheck, pre-commit, Docker, migrations, security checks, failure injection, independent review, Git checkpoint |

Details and pass criteria: [phase-quality-gates.md](phase-quality-gates.md).

## 6. Lifecycle of a unit of work

```
Coordinator writes task contract (agent-task-contract.md),
  records claim + allocated IDs in governance-state.yaml
  → owner inspects + searches (recorded)
  → implement with L1 checks
  → L2 checks
  → handoff (agent-handoff-contract.md)
  → independent review (+ specialist if triggered)
  → integrator squash-merges the PR into `main`, re-runs L1/L2 on `main`
  → commit checkpoint; coordinator releases claim
… repeat …
  → integrator runs L3, writes gate report → reviewers sign off
  → annotated tag → coordinator records phase closed
```

## 7. Decision records

Any decision that is hard to reverse, crosses component boundaries, changes a
frozen contract, adds a runtime dependency, or relaxes a rule in any governance
document needs an ADR in `docs/adr/` (template: [0000-template.md](adr/0000-template.md)).
ADRs are append-only; changing a decision means a new ADR that supersedes it.

## 8. Living registers

- [`assumptions.yaml`](assumptions.yaml) — every assumption, with owner and
  validation plan. Invalidated assumptions trigger review of dependents.
- [`technical-debt.yaml`](technical-debt.yaml) — every known shortcut, with
  severity, repayment trigger, and the phases it blocks. Entries are never
  deleted; repaid debt keeps its history.

## 9. Changing governance

Any change to a governance document requires an ADR when it relaxes a rule,
plus independent review with Reviewer A and/or B sign-off; changes to this
contract require both. This contract's version is bumped (SemVer: major = rule
removed or weakened; minor = rule added; patch = clarification).
Branch protection and CODEOWNERS enforce this in the dedicated repository
(TD-004). The governance checker verifies that recorded reviewer verdicts are
*consistent* with the recorded state; it cannot verify *who wrote* them
(TD-007).
