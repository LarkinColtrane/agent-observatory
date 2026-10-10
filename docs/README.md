# agent-observatory — development governance

Universal observability platform for agentic workspaces (adapters → universal
event model → state engine → dashboards, timelines, dependency graphs, virtual
office). **Phase 0 (governance) only — no application code yet.**

Start here: [development-operating-contract.md](development-operating-contract.md)

| Doc | Purpose |
|---|---|
| [agent-task-contract.md](agent-task-contract.md) | Template + rules for assigning work |
| [agent-handoff-contract.md](agent-handoff-contract.md) | Template + rules for finishing/transferring work |
| [review-checklist.md](review-checklist.md) | Independent + specialist review |
| [parallel-work-policy.md](parallel-work-policy.md) | Concurrency limits, contract freeze, branching |
| [phase-quality-gates.md](phase-quality-gates.md) | L1 / L2 / L3 testing levels and phase gates |
| [rollback-policy.md](rollback-policy.md) | Checkpoints, tags, reverting |
| [security-baseline.md](security-baseline.md) | Secrets, untrusted input, supply chain |
| [agent-efficiency.md](agent-efficiency.md) | Credit efficiency, turn budgets |
| [component-ownership.md](component-ownership.md) | Components, owners, frozen contracts |
| [assumptions.yaml](assumptions.yaml) | Assumption register |
| [technical-debt.yaml](technical-debt.yaml) | Debt register |
| [adr/](adr/README.md) | Architecture decision records |
| [phases/P0-gate-report.md](phases/P0-gate-report.md) | Phase 0 gate result |

Governance check: `python3 scripts/check-governance.py`
