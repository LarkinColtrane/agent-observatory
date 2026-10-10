# Agent Handoff Contract

A handoff is the only accepted way to finish, pause, or transfer a task. It
lets the next agent (reviewer, integrator, or successor) continue **without
re-deriving context**. Handoffs are factual; claims must be verifiable.

## Rules

- Every task ends with a handoff — including failed or abandoned tasks.
- **Truthful test reporting.** For each check list the exact command, whether
  it ran, and the real outcome. If a check did not run, say `not_run` and why.
  Never summarise unrun checks as passing.
- Paste only the relevant tail of failing output, not whole logs.
- Never include secrets, tokens, credentials, or raw customer/agent payloads
  that may contain them. Redact as `[REDACTED]`.
- Reference code as `path:line`.
- Keep it short: a handoff a reviewer cannot read in 5 minutes is too long.

## Template

```yaml
task_id: AO-<phase>-<seq>
from: <agent id>
to: <reviewer | integrator | successor agent id>
status: complete | partial | blocked | abandoned
commit: <sha>                        # checkpoint containing the work
branch: <branch>

summary: >
  2–4 sentences: what changed and why.

inspected:                           # proof of "inspect before editing"
  - <path / ADR / contract read before editing>
searched_for_reuse:                  # proof of "search before creating"
  - query: <what was searched>
    result: <reused X | nothing suitable, created Y because ...>

changes:
  - path: <path>
    kind: added | modified | deleted
    note: <one line>

contracts:
  consumed: [<path@version>]
  changed: []                        # must be empty unless an ADR authorised it

acceptance_criteria:
  - id: AC1
    met: true | false
    evidence: <test name / output excerpt>

checks:
  - level: L1 | L2
    command: <exact command>
    ran: true | false
    result: pass | fail | not_run
    note: <reason if fail/not_run>

risks_and_open_questions:
  - <anything the reviewer should look at hardest>
new_assumptions: [<id added to docs/assumptions.yaml>]
new_debt: [<id added to docs/technical-debt.yaml>]
specialist_review_needed: [security|data-integrity|concurrency|architecture]
rollback: <how to revert this change>
next_steps: <for partial/blocked: exactly what the successor should do first>
```

## Receiving a handoff

The receiver must:

1. Check that `commit` exists and contains the listed `changes`.
2. Re-run at least the L1 commands listed (reviewers) or L1+L2 (integrator).
3. Reject the handoff (status back to owner) if any check claimed `pass` cannot
   be reproduced, or any required field is missing.
