# Development Operating Contract — agent-observatory

Status: **Active** · Version: 1.0.0 · Owner: Coordinator · Checkpoint: `gov-baseline-v1.0.0`

This is the top-level contract for how `agent-observatory` is built. Every other
governance document in `docs/` is a detail of this one. If two documents
disagree, this file wins, then the more specific document.

## 1. Product context (for orientation only)

`agent-observatory` will be a universal observability platform for agentic
workspaces. It will:

1. connect to many agent systems through **adapters**,
2. normalize their activity into one **universal event model**,
3. compute **agent / workflow state** from that event stream, and
4. present it through **dashboards, timelines, dependency graphs, and a visual
   virtual office**.

It is a separate project from Quant Autonomy. No code, contracts, secrets, or
infrastructure are shared between the two unless an ADR says so.

**No product functionality exists yet.** This baseline establishes only the
development operating system. Phase 1 does not start until the coordinator
opens it explicitly (see `phase-quality-gates.md`).

## 2. Team model

| Role | Count | Responsibility |
|---|---|---|
| Coordinator | 1 | Plans phases, writes task contracts, freezes shared contracts, assigns ownership, resolves conflicts, owns Git checkpoints and tags. Does not self-approve its own implementation. |
| Implementation agents | 5–6 | Execute one task contract each, inside their owned components only. |
| Specialist reviewers | 2 | Independent review. Reviewer A: **security + data integrity**. Reviewer B: **concurrency + architecture**. Never review their own work. |
| Integration / validation agent | 1 | Merges completed tasks, runs Level 2/3 checks, failure injection, and owns the phase gate report. |

**Concurrency limit:** 8–10 agents active at once. Exceeding it requires a
written justification in the phase plan showing the extra tasks are genuinely
independent (disjoint ownership, no shared-contract changes). See
`parallel-work-policy.md`.

## 3. Non-negotiable rules

1. **Inspect before editing.** Read the files, contracts, and ADRs you will
   touch before changing them. Record what you inspected in the handoff.
2. **Contract-first.** Interfaces, schemas, and event types are written and
   reviewed before implementations.
3. **Freeze shared contracts before parallel work.** A shared contract is
   frozen (tagged in `component-ownership.md`) before two or more agents build
   against it. Changing a frozen contract requires an ADR and coordinator
   approval.
4. **Small task ownership.** One task = one owner = one bounded set of paths.
   Target ≤ ~400 changed lines of non-generated code per task.
5. **No duplicate work.** Check the task board and `component-ownership.md`
   before starting. Two agents may never own the same path concurrently.
6. **Structured handoffs.** Every task ends with a handoff matching
   `agent-handoff-contract.md`. No handoff = task not done.
7. **Independent review** for every meaningful change (see
   `review-checklist.md`). Authors never approve their own work.
8. **Specialist review** is mandatory for changes touching security,
   concurrency, data integrity, or architecture.
9. **Targeted tests during development** (Level 1/2). **Full suite only at
   phase closure** (Level 3).
10. **Search before creating abstractions.** Search the codebase and ADRs for
    an existing type, helper, or pattern before adding one. Prefer reuse over
    duplication; record the search in the handoff.
11. **Fail safely.** Unknown input, adapter failure, or partial data must
    degrade to an explicit "unknown/degraded" state, never to a crash or a
    silently wrong state.
12. **Never claim a test ran unless it actually ran.** Report the exact
    command and its real result. "Not run" is an acceptable answer; a
    fabricated pass is a contract violation that voids the task.
13. **Git checkpoints.** Commit at every task completion; tag at every phase
    gate. See `rollback-policy.md`.
14. **Secrets are never committed or logged.** See `security-baseline.md`.

## 4. Testing levels

| Level | When | Scope |
|---|---|---|
| **L1** | Every change, during development | Affected unit tests + lint + typecheck for touched packages |
| **L2** | Before handoff of a task | Task-related integration tests + adversarial/edge-case tests for the task's surface |
| **L3** | Phase closure only | Full tests, lint, format, strict typecheck, pre-commit, Docker build, migrations (up/down), security checks, failure injection, independent review, Git checkpoint tag |

Details and pass criteria: `phase-quality-gates.md`.

## 5. Lifecycle of a unit of work

```
Coordinator writes task contract (agent-task-contract.md)
  → owner claims paths (component-ownership.md)
  → inspect + search (recorded)
  → implement with L1 checks
  → L2 checks
  → handoff (agent-handoff-contract.md)
  → independent review (+ specialist if triggered)
  → integration agent merges, re-runs L1/L2 on integrated branch
  → commit checkpoint
… repeat …
  → phase gate L3 → tag → coordinator closes phase
```

## 6. Decision records

Any decision that is hard to reverse, crosses component boundaries, changes a
frozen contract, adds a runtime dependency, or relaxes a rule in this contract
needs an ADR in `docs/adr/` (template: `docs/adr/0000-template.md`).

## 7. Living registers

- `docs/assumptions.yaml` — every assumption we are building on, with an owner
  and a validation plan. Invalidated assumptions trigger review of dependents.
- `docs/technical-debt.yaml` — every known shortcut, with severity and a
  repayment trigger. Debt is never hidden in code comments alone.

## 8. Changing this contract

Changes require an ADR, coordinator approval, and one specialist reviewer
sign-off. The version at the top is bumped (SemVer: major = rule removed or
weakened; minor = rule added; patch = clarification).
