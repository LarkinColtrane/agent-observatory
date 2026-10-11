# Phase 1 task reviews

Independent, risk-scaled reviews of the Phase 1 task branches (plan:
[P1-plan.md](../phases/P1-plan.md)). Reviewer A covers security and data
integrity; Reviewer B covers concurrency, architecture and governance tooling.
Each section lists the rounds, every finding with its disposition, and the
final verdict. Reviewers did not modify authors' branches; reproductions ran in
their own copies.

## AO-P1-005 — governance tooling (W4; reviewer B)

**Round 1** (`8c2a1b6..a898954`) — REQUEST_CHANGES. Passed: checker PASS, hostile
YAML (alias bomb, python tags, binary, 50k nesting, directory named like a task
file) all exit 1 cleanly, usage errors exit 2; the AO-P1-006 aggregator judged
correct by eye.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-005-01 | major | aggregator "success-only" check was a substring heuristic; 5 never-failing aggregators passed | fixed: the aggregator step is executed against synthetic `needs` (success, failure, cancelled, skipped, empty) |
| R-B-005-02 | major | `continue-on-error` on a member job not rejected | fixed: rejected anywhere (job and step level) |
| R-B-005-03 | major | unregistered or `..`-aliased contract refs passed | fixed: normalised path, registered contract, equal tag |
| R-B-005-04 | minor | list fields given as strings; empty nested strings passed | fixed |
| R-B-005-05 | minor | `complete` with no L1 check that ran passed | fixed |
| R-B-005-06 | minor | task-id phase not compared with directory | fixed |
| R-B-005-07 | minor | `owned_paths: ["."]` passed | fixed: normalised paths only |
| R-B-005-08 | minor | pre-aggregation skip could become a permanent escape hatch | coordinator: removed in AO-P1-006 (acceptance criterion) |
| R-B-005-09 | minor | checker stricter than the task-contract template (`<path or glob>`) | coordinator: template amended; task-contract version 1.1.0 → 1.1.1 (R-B-005-14) |
| R-B-005-10 | nit | duplicate YAML keys silently accepted | fixed: strict loader rejects them |
| R-B-005-11 | nit | small divergences between task files and P1-plan.md | coordinator: plan updated |
| R-B-005-12 | nit | 32 s subprocess-heavy test file | fixed: in-process tests, 6.6 s |

**Round 2** (`a898954..c35e7c2`, PR branch at `a123eb1`): all 19 saved
adversarial cases now fail cleanly; workflow counterexamples C1–C6, C9, C10 and
new D1–D5 rejected, control D6 passes; 203 governance tests OK (1 skip, removed
in AO-P1-006); the AO-P1-006 workflow passes the executed aggregator test.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-005-13 | nit | a step written to detect the host vs the runner could pass the executed test | accepted: deliberate subversion is for code review; no change |
| R-B-005-14 | nit | template changed in place without a contract version bump | fixed: task-contract 1.1.1 |

<!-- final-verdicts -->
- **Reviewer B final outcome:** APPROVE — AO-P1-005 round 2 (`c35e7c2`, PR #5 head `a123eb1`)
