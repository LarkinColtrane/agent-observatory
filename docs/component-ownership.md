# Component Ownership

Who owns what, which shared contracts are frozen, and which paths are claimed.
The **machine-readable source of truth** is
[`governance-state.yaml`](governance-state.yaml) (`components`, `contracts`,
`claims`), maintained by the coordinator only and validated by
`scripts/check-governance.py`. This page explains it.

## Planned components (illustrative — not a layout)

These are **logical** boundaries, not directories. Per
[ADR-0002](adr/0002-phase-1-technology-stack.md) the system is a modular
monolith: backend modules are expected to live under
`backend/src/observatory/<module>/` and the UI under `frontend/`, but **exact
paths are decided by Phase 1 tasks**, not here. Nothing here gives the event
protocol a home before Phase 2 decides its form.

| ID | Component | Responsibility | Depends on | Built in phase | Specialist focus |
|---|---|---|---|---|---|
| C1 | Event protocol | Canonical event contract, versioning, validation | — | P2 | Data integrity, architecture |
| C2 | Adapter SDK | Interface every adapter implements; mapping to C1 | C1 | P3 | Architecture, security |
| C3 | Adapters | One per agent system; normalize to C1 | C1, C2 | P3, P9 | Security |
| C4 | Ingestion | Authenticate, validate, redact, quarantine, dedup, persist | C1, C13 | P3–P4 | Concurrency, data integrity, security |
| C5 | Event store | Append-only storage + migrations | C1 | P2–P4 | Data integrity |
| C6 | State engine | Derive agent/workflow state from the event log | C1, C5 | P4 | Concurrency, data integrity |
| C7 | Query API | Read API for UIs | C5, C6, C13 | P4–P6 | Security, architecture |
| C8 | Operations dashboard | Dashboards, timelines | C7, C14 | P6 | Security (XSS) |
| C9 | Control room / workflow graph | Dependency and workflow graph | C7 | P10 | Architecture |
| C10 | 2D virtual office | Spatial visualisation of agent activity | C7, C14 | P8 | Architecture |
| C11 | Platform & tooling | CI, Docker/Compose, pre-commit, dev env, import-boundary checks | — | P1 | Security |
| C12 | Governance | Contracts, ADRs, registers, governance tooling | — | P0 | — |
| C13 | Identity & access | AuthN/AuthZ for users, adapters, streams | — | P1–P5 | Security |
| C14 | Realtime | Live streaming to clients (WebSockets or SSE — ADR in P5) | C6, C13 | P5 | Concurrency |
| C15 | Analytics / scorecards | Aggregates, scorecards, trends | C5, C6 | P7 | Data integrity |
| C16 | External integrations | Outbound integrations, export, notifications | C7 | P9 | Security |

Dependency direction is one-way as listed: adapters depend on the protocol,
never the reverse; UI depends on the API, never on storage. From Phase 1 this
is enforced by an import-boundary check in CI.

## Shared contract register (summary)

| Contract | Version | Status | Tag |
|---|---|---|---|
| Development operating contract | 1.1.0 | **approved** (A + B verdicts recorded); frozen when tagged in the dedicated repo | `contract-operating-contract-v1.1.0` (planned) |
| Agent task contract | 1.1.0 | **approved** (A + B verdicts recorded); frozen when tagged in the dedicated repo | `contract-task-contract-v1.1.0` (planned) |
| Agent handoff contract | 1.1.0 | **approved** (A + B verdicts recorded); frozen when tagged in the dedicated repo | `contract-handoff-contract-v1.1.0` (planned) |
| Universal event protocol | — | not_drafted — **not before P2** | — |
| Adapter interface | — | not_drafted — not before P3 | — |
| Query API | — | not_drafted | — |

Statuses: `not_drafted` → `draft` → `in_review` → `approved` → `frozen` → `deprecated`.
Parallel implementation against a contract is allowed only at `frozen`.
`approved` = both reviewers' approving verdicts are recorded; `frozen` =
additionally an annotated tag `contract-<id>-v<version>` exists. Contract tags
are created only in the dedicated repository; the process contracts are frozen
when their tags are created there. The checker enforces all of this.

## Current owners and claims

| Component | Owner |
|---|---|
| C12 Governance | Coordinator |
| All others | unassigned |

Active path claims: none (see `claims` in `governance-state.yaml`).
