# agent-observatory — development governance

Universal observability platform for agentic workspaces (adapters → universal
event protocol → state engine → dashboards, timelines, dependency graphs, 2D
virtual office). **Governance only — no application code yet.**

Start here: [development-operating-contract.md](development-operating-contract.md) ·
Phase order: [roadmap.md](roadmap.md) · Current state: [governance-state.yaml](governance-state.yaml)

| Doc | Purpose |
|---|---|
| [development-operating-contract.md](development-operating-contract.md) | Top-level rules, roles, separation of duties |
| [agent-task-contract.md](agent-task-contract.md) | Template + rules for assigning work |
| [agent-handoff-contract.md](agent-handoff-contract.md) | Template + rules for finishing/transferring work |
| [review-checklist.md](review-checklist.md) | Independent + specialist review, outcomes |
| [parallel-work-policy.md](parallel-work-policy.md) | Concurrency limits, claims, hotspots, contract freeze |
| [phase-quality-gates.md](phase-quality-gates.md) | L1 / L2 / L3 testing levels and phase gates |
| [rollback-policy.md](rollback-policy.md) | Checkpoints, tags, reverting, secret incidents |
| [security-baseline.md](security-baseline.md) | Secrets, untrusted input, fixtures, supply chain |
| [security-incident-log.md](security-incident-log.md) | Incident log (never contains secret values) |
| [agent-efficiency.md](agent-efficiency.md) | Credit efficiency, turn budgets |
| [component-ownership.md](component-ownership.md) | Components, owners, contract register |
| [roadmap.md](roadmap.md) | Phase order P0–P11; event protocol deferred to P2 |
| [governance-state.yaml](governance-state.yaml) | Machine-checked phases, contracts, components, claims |
| [assumptions.yaml](assumptions.yaml) | Assumption register |
| [technical-debt.yaml](technical-debt.yaml) | Debt register |
| [adr/](adr/README.md) | Architecture decision records |
| [reviews/](reviews/pre-phase-1-review-resolution.md) | Independent governance reviews and resolutions |
| [phases/P0-plan.md](phases/P0-plan.md) · [phases/P0-gate-report.md](phases/P0-gate-report.md) | Phase 0 plan and gate |
| [migration/dedicated-repo-migration.md](migration/dedicated-repo-migration.md) | Moving to the dedicated private repository |

## Commands

```sh
pip install --require-hashes -r requirements-governance.txt
python3 -I scripts/check-governance.py                              # governance + state check
python3 -I -m unittest discover -s tests/governance -t . -v         # checker adversarial tests
scripts/secret-scan.sh                                              # gitleaks, full history, all refs
pre-commit run --all-files                                          # hygiene + gitleaks + governance
```
