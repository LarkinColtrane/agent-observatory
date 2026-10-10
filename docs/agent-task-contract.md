# Agent Task Contract

Every unit of work assigned to an agent is described by a task contract. The
coordinator writes it; the assignee confirms it before starting. An agent must
not start work without one, and must not work outside it.

## Rules

- One task, one owner. The owner is the only agent that writes to the task's
  `owned_paths` while the task is open.
- A task may **read** anything, but may only **write** to `owned_paths`.
- If the task turns out to need a write outside `owned_paths` or a change to a
  frozen contract, the agent **stops and escalates** to the coordinator; it does
  not expand scope on its own.
- Size target: ≤ ~400 changed non-generated lines, ≤ 1 day of agent effort. If
  larger, the coordinator splits it.
- Acceptance criteria must be testable. "Works well" is not a criterion.

## Template

Copy into the task board / issue verbatim and fill every field. Use `n/a`
rather than deleting a field.

```yaml
task_id: AO-<phase>-<seq>            # e.g. AO-P1-007
title: <imperative, ≤ 70 chars>
phase: <phase id>
owner: <agent id>
reviewers:
  independent: <agent id>            # never the owner
  specialist: [security|data-integrity|concurrency|architecture]  # if triggered, else []
depends_on: [<task_id>, ...]         # must be merged before start
blocks: [<task_id>, ...]

objective: >
  One paragraph: what outcome this task produces and why.

inputs:
  frozen_contracts: [<path@version>] # contracts this task builds against (read-only)
  adrs: [<docs/adr/NNNN-*.md>]
  assumptions: [<assumption id>]     # from docs/assumptions.yaml

owned_paths:                         # exclusive write scope
  - <path or glob>
read_only_paths:                     # explicitly may not modify
  - <path or glob>

out_of_scope:
  - <things explicitly NOT to do>

acceptance_criteria:
  - id: AC1
    statement: <observable, testable outcome>
    verified_by: <test name / command / manual step>

testing:
  level_1: <exact commands: affected unit tests, lint, typecheck>
  level_2: <exact commands: integration/adversarial tests for this task>
  adversarial_cases:
    - <malformed input / timeout / duplicate event / out-of-order event / ...>

security_notes: <secrets, untrusted input, auth surface touched — or "none">
failure_mode: <how this component fails safely>
rollback: <how to revert: e.g. "revert commit; no migration">
budget:
  max_agent_turns: <n>
  escalate_if: <condition, e.g. "2 failed approaches" or "scope > owned_paths">
```

## Definition of done

A task is done only when **all** are true:

1. Every acceptance criterion is met and its verification actually ran.
2. L1 and L2 checks pass (real commands, real output in the handoff).
3. Handoff submitted per `agent-handoff-contract.md`.
4. Independent review approved; specialist review approved if triggered.
5. Integration agent merged it and L1/L2 pass on the integrated branch.
6. Any new assumption or debt is recorded in the YAML registers.
7. Git checkpoint commit exists.
