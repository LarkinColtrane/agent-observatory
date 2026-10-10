# ADR-0002: Phase 1 technology stack — modular monolith

- Status: accepted
- Date: 2026-10-10
- Deciders: Coordinator (proposed); sign-off by Reviewer A and Reviewer B as recorded in `docs/reviews/pre-phase-1-review-resolution.md`
- Components: all (C1–C11 planned), primarily C11 Platform & tooling
- Related: A-004 (validated by this ADR), A-007, A-008, TD-001, ADR-0003

## Context

Phase 1 builds the engineering foundation: repository layout, toolchains,
local runtime, CI, and quality gates that let later phases ship safely. The
product will ingest high-volume, heterogeneous agent activity (Phase 2+),
derive state (Phase 4), stream it live (Phase 5) and render dashboards and a
2D office (Phases 6–8). None of those exist yet, and the event protocol is
deliberately undesigned until Phase 2.

The stack must therefore: be productive for a small multi-agent team; have
strong typing and schema validation at boundaries; support reversible
migrations; run fully locally; and avoid operational complexity we cannot yet
justify with measured load.

## Options considered

1. **Modular monolith (Python backend + TypeScript frontend, Postgres, Redis,
   Docker Compose)** — one deployable backend with enforced internal module
   boundaries; minimal ops; boundaries can later be split into services along
   the module seams if measured need appears.
2. **Microservices from day one** (separate ingest, state, API services;
   message bus) — independent scaling, but distributed-systems failure modes
   (partial failure, ordering across services, distributed transactions) before
   we have a single working path; multiplies CI, deploy, and review cost.
3. **Event-streaming platform first** (Kafka + ClickHouse) — strong at scale,
   but premature: no event schema exists, no measured throughput, heavy local
   footprint, and it would pre-empt Phase 2 design decisions.

## Decision

Option 1, with this stack:

| Layer | Choice | Notes |
|---|---|---|
| Backend language | Python ≥ 3.12 | Type hints everywhere; strict mypy |
| API framework | FastAPI | Async; OpenAPI generated from types |
| Validation / schemas | Pydantic v2 | All boundary input validated |
| ORM / DB access | SQLAlchemy 2.x | Typed 2.0 style |
| Migrations | Alembic | Every migration has a tested downgrade |
| Primary store | PostgreSQL | System of record |
| Cache / ephemeral | Redis | Cache, rate limits, short-lived pub/sub; **never** the system of record. Holds only already-redacted data; requires auth (and TLS outside local dev); persistence disabled or limited to redacted data (review N-07) |
| Frontend | Next.js + React + TypeScript (strict) | |
| Local runtime | Docker + Docker Compose | Single `compose` file for dev/test |
| Python quality | pytest, Ruff (lint + format), mypy `--strict` | |
| Frontend quality | ESLint, `tsc --noEmit` strict, Prettier, a unit test runner chosen in Phase 1 | |
| Realtime (Phase 5) | WebSockets or SSE — decided by ADR in Phase 5 | Not in Phase 1 |
| 2D office (Phase 8) | PixiJS or Phaser — decided by ADR in Phase 8 | Not in Phase 1 |

**Explicitly excluded from Phase 1:** Kafka, Kubernetes, ClickHouse, Three.js,
distributed databases, complex cloud infrastructure. Introducing any of them
later requires an ADR citing measured need.

Exact versions are pinned in lockfiles during Phase 1 (not in this ADR) and
must be at least two weeks old when adopted.

### Why a modular monolith

- **One failure domain while the core model is still forming.** Ordering,
  idempotency, and state-derivation bugs (the hardest data-integrity risks for
  this product) are far easier to reason about and test in one process with
  one database transaction boundary.
- **Boundaries without network hops.** Planned components (adapters SDK,
  ingest, store, state engine, API, UI) become Python packages / TS apps with
  enforced import rules (checked in CI from Phase 1). The dependency direction
  in `component-ownership.md` is enforced by tooling, not convention.
- **Cheaper for a multi-agent team.** One CI pipeline, one local `compose up`,
  one migration history: fewer integration conflicts between parallel agents.
- **Reversible.** Module seams are the future service seams. Extraction is an
  ADR-gated, evidence-driven step, not a day-one bet.

## Consequences

- Positive: fast local loop; strong typing at every boundary; tested
  reversible migrations; low operational surface; aligns with the security
  baseline (single auth boundary, single redaction point).
- Negative / accepted risk: vertical scaling limits for ingestion until a later
  phase measures load (tracked as assumption A-007); Python async throughput
  must be validated under realistic load before Phase 11 (A-008).
- Contracts affected: none frozen. This ADR does **not** define the event
  model; that is Phase 2.
- Rollback path: this ADR is superseded by a new ADR; no code depends on it
  until Phase 1 tasks start.

## Review

- Reviewer A (security + data integrity): APPROVE_WITH_NOTES (note N-07, Redis data rules, applied) — `docs/reviews/pre-phase-1-review-A.md`.
- Reviewer B (concurrency + architecture): APPROVE_WITH_NOTES — modular-monolith rationale and exclusions judged sound — `docs/reviews/pre-phase-1-review-B.md`.
