# Component Ownership

Single source of truth for who owns what and which shared contracts are
frozen. Updated by the coordinator only. An agent may write to a path only if
this file (or its active task contract) assigns it.

## Planned components

These are **planned** boundaries for the product; none exist yet. Paths are
provisional and will be confirmed by ADR when Phase 1 opens.

| ID | Component | Planned path | Responsibility | Depends on | Specialist focus |
|---|---|---|---|---|---|
| C1 | Universal event model | `contracts/events/` | Canonical event schema, versioning, validation | — | Data integrity, architecture |
| C2 | Adapter SDK | `adapters/sdk/` | Base interface every adapter implements; mapping to C1 | C1 | Architecture, security |
| C3 | Adapters | `adapters/<system>/` | One per agent system; normalize to C1 | C1, C2 | Security |
| C4 | Ingestion pipeline | `core/ingest/` | Receive, validate, redact, dedup, persist events | C1 | Concurrency, data integrity, security |
| C5 | Event store | `core/store/` | Append-only storage + migrations | C1 | Data integrity |
| C6 | State engine | `core/state/` | Derive agent/workflow state from event log | C1, C5 | Concurrency, data integrity |
| C7 | Query API | `api/` | Read API for UIs; authN/authZ | C5, C6 | Security, architecture |
| C8 | Dashboards & timelines | `ui/dashboards/` | Metrics, timelines | C7 | Security (XSS) |
| C9 | Dependency graph | `ui/graph/` | Agent/workflow dependency visualization | C7 | Architecture |
| C10 | Virtual office | `ui/office/` | Spatial visualization of agent activity | C7 | Architecture |
| C11 | Platform & tooling | `infra/`, `.github/`, tooling configs | CI, Docker, pre-commit, dev env | — | Security |
| C12 | Governance | `docs/` | Contracts, ADRs, registers | — | — |

Dependency direction is one-way as listed. Adapters depend on the event
model, never the reverse; UI depends on the API, never on storage.

## Current owners

| Component | Owner | Since |
|---|---|---|
| C12 Governance | Coordinator | P0 |
| C1–C11 | unassigned | — |

## Shared contract register

| Contract | Path | Version | Status | Consumers |
|---|---|---|---|---|
| Development operating contract | `docs/development-operating-contract.md` | 1.0.0 | **frozen** | all agents |
| Agent task contract | `docs/agent-task-contract.md` | 1.0.0 | **frozen** | all agents |
| Agent handoff contract | `docs/agent-handoff-contract.md` | 1.0.0 | **frozen** | all agents |
| Universal event model | `contracts/events/` | — | not drafted | C2–C10 |
| Adapter interface | `adapters/sdk/` | — | not drafted | C3 |
| Query API | `api/` | — | not drafted | C8–C10 |

Statuses: `not drafted` → `draft` → `in review` → `frozen` → `deprecated`.
Parallel implementation against a contract is allowed only at `frozen`.

## Active path claims

| Task | Owner | Paths | Opened |
|---|---|---|---|
| — | — | — | — |
