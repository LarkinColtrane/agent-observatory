# Agent Efficiency

Quality first, then credit efficiency. Wasted agent turns are the main cost
driver; most waste comes from re-deriving context, duplicate work, and running
expensive checks too often.

## Principles

1. **Right-size the team.** Spawn an agent only for a task that has its own
   contract and disjoint ownership. A task a single agent finishes in a few
   turns is not split. Hard limit 10 concurrent agents, target ≤ 8
   ([parallel-work-policy.md](parallel-work-policy.md)).
2. **Context is handed over, not rediscovered.** Task contracts list the exact
   files, contracts, and ADRs to read. Handoffs carry what was learned.
3. **Read narrowly.** Search for symbols, then read the relevant ranges; do not
   read whole trees "for context".
4. **Test at the right level.** L1 on every change, L2 before handoff, L3 only
   at phase closure. Running the full suite mid-task is waste.
5. **Fail fast and escalate.** After two failed approaches, or when scope
   exceeds `owned_paths`, stop and escalate instead of looping.
6. **Reuse before you write.** Search existing code/ADRs before new
   abstractions; record the search in the handoff.
7. **One reviewer pass, done well.** Reviewers re-run claimed checks and give
   concrete findings once, rather than many shallow rounds.

## Turn budgets (defaults; the task contract may override)

| Task size | Max agent turns before escalation |
|---|---|
| Small (≤ 100 lines) | 15 |
| Medium (≤ 400 lines) | 40 |
| Review | 15 |
| Integration of one task | 10 |

Exceeding the budget is not a failure, but it requires a short note to the
coordinator explaining why and what remains.

## Model / effort selection

- Coordinator, specialist reviewers, and contract design: highest-capability
  model.
- Well-specified implementation tasks against frozen contracts: a standard
  model is acceptable.
- Mechanical work (formatting, renames, boilerplate from templates): the
  cheapest capable model.

## Anti-patterns

- Spawning agents to "explore" without a question to answer.
- Two agents reading the same large context for overlapping tasks.
- Re-running passing checks with no intervening change.
- Long narrative handoffs; use the YAML template.
- Speculative abstractions "for future adapters" with one call site.

## Metrics (tracked per phase in the gate report)

- Tasks completed / tasks reopened after review.
- Average turns per task vs budget.
- Review findings per task (blocking vs nit).
- Duplicate-work incidents (target: 0).
