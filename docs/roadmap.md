# Roadmap — phase order

Authoritative, machine-checked phase state lives in
[`governance-state.yaml`](governance-state.yaml). This page explains intent.
Each phase opens only on an explicit coordinator decision and closes only when
its Level 3 gate passes ([phase-quality-gates.md](phase-quality-gates.md)).

| Phase | Name | Purpose | Must not start before |
|---|---|---|---|
| P0 | Governance | Development operating system, registers, ADR process, governance tooling | — |
| P1 | Engineering foundation | Repo layout, backend/frontend skeletons with no product logic, toolchains (Ruff, mypy strict, pytest, ESLint, tsc, Prettier), Docker Compose (Postgres, Redis), Alembic baseline, CI gates, import-boundary enforcement | P0 closed **and** dedicated repository in place |
| P2 | Universal agent event protocol | Design, adversarially review, then **freeze** the event contract | P1 closed |
| P3 | Adapter / SDK layer | Adapter SDK and first adapters against the frozen protocol | P2 closed (contract frozen) |
| P4 | Agent state engine | Deterministic state derivation from the event log | P3 closed |
| P5 | Realtime observability | Live streaming to clients (WebSockets or SSE — ADR) | P4 closed |
| P6 | Operations dashboard | Dashboards and timelines | P5 closed |
| P7 | Analytics / scorecards | Aggregates, scorecards, trends | P6 closed |
| P8 | 2D virtual office | Spatial visualisation (PixiJS or Phaser — ADR) | P7 closed |
| P9 | External integrations | Third-party integrations, export, notifications | P8 closed |
| P10 | Control room / workflow graph | Dependency and workflow graph, control-room views | P9 closed |
| P11 | Production hardening | Load, resilience, security hardening, ops runbooks | P10 closed |

Phases are strictly sequential: the governance checker allows at most one
active phase and requires the predecessor to be `closed`. Allowing overlap
would need an ADR **and** a reviewed change to the checker.

## Universal event protocol — deferred to Phase 2

The event model is **not designed and not frozen** before Phase 2, and must not
be frozen before the Phase 1 engineering foundation exists. No task before
Phase 2 may create files under the event-contract path or define event types.

High-level requirements recorded now as **inputs** to Phase 2 (not a design):

1. Represent heterogeneous agent systems without losing information needed
   for observability (assumption A-001; validated against ≥ 2 structurally
   different systems before freeze).
2. Every event carries enough identity and provenance (source system, adapter
   version, schema version) to deduplicate and audit.
3. Ordering, late, and duplicate delivery are expected; derived state must be
   reproducible from the stored log (A-002).
4. Content that may be sensitive is distinguishable from metadata so
   redaction can run before persistence (A-003, security baseline).
5. Explicit versioning and a compatibility policy are part of the contract.
6. Freeze only after independent adversarial review by both specialist
   reviewers.
