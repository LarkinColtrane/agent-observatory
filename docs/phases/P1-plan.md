# P1 Plan — Engineering foundation

- Phase: P1 · Opened: 2026-10-10 by owner instruction · Contract: [ADR-0005](../adr/0005-phase-1-foundation-contract.md)
- Objective: a runnable, reproducible, fully gated foundation (backend, frontend, data, containers, CI) with **no product behaviour**; repay TD-001 (and TD-006 where cheap).
- Out of scope: event protocol, adapters, ingestion, state engine, UI features, visualisation, realtime, integrations (ADR-0003).
- Team (max 6 active): Coordinator · W1 backend-core · W2 frontend · W3 data+containers · W4 governance tooling · Reviewer A · Reviewer B · Validation agent (gate).
- Dependency cutoff: 2026-09-25 (≥ 2 weeks old).

## Task graph

```
AO-P1-001 contract+bootstrap ──┬─> AO-P1-002 backend-core ─┐
   (freeze, tag automation)    ├─> AO-P1-003 frontend ─────┤
                               ├─> AO-P1-004 data+containers┼─> AO-P1-006 integration+CI ─> AO-P1-007 L3 gate
                               └─> AO-P1-005 gov tooling ──┘
```

| Task | Owner | Deps | Owned paths | Interfaces | Acceptance | Tests (L1/L2) | Reviewer | Risk |
|---|---|---|---|---|---|---|---|---|
| AO-P1-001 | Coordinator | — | `docs/**` (P1 records), `backend/pyproject.toml`, `backend/uv.lock`, `backend/src/observatory/__init__.py`, `.github/workflows/release-tags.yml` | ADR-0005 | contract approved by A+B, tagged, frozen; lock resolves with cutoff | checker, governance tests | A + B | CRITICAL |
| AO-P1-002 | W1 | 001 frozen | `backend/src/observatory/{core,api}/**`, `backend/tests/unit/**` | config, logging, errors, health, app factory | ADR-0005 §3 exactly; 100% of listed behaviours tested incl. redaction, request-id validation, fail-closed checks | ruff, mypy --strict, pytest unit | A (logging/errors) | STANDARD |
| AO-P1-003 | W2 | 001 frozen | `frontend/**` | ADR-0005 §4 | strict TS; lint/typecheck/format/test/build pass from `npm ci`; Dockerfile builds | npm scripts | B | STANDARD |
| AO-P1-004 | W3 | 001 frozen | `backend/src/observatory/{db,cache}/**`, `backend/migrations/**`, `backend/alembic.ini`, `backend/tests/integration/**`, `backend/Dockerfile`, `backend/.dockerignore`, `compose.yaml` | db/cache seams, Alembic baseline | upgrade/downgrade/upgrade on Postgres 16; one head; checks fail closed; compose stack healthy; non-root images | integration tests vs real Postgres/Redis | A (data integrity) + B (concurrency) | CRITICAL |
| AO-P1-005 | W4 | 001 frozen | `scripts/check-artifacts.py`, `tests/governance/test_check_artifacts.py`, `docs/phases/P1-tasks/**` | task/handoff YAML schema | invalid (ran,result) combos, missing fields, unknown claims rejected; adversarial tests | unittest | B | STANDARD |
| AO-P1-006 | Coordinator | 002–005 | `backend/src/observatory/main.py`, `Makefile`, `.github/workflows/governance.yml`, `.pre-commit-config.yaml`, `.gitignore`, `requirements-governance.*` | composition root, CI aggregator | all jobs green; aggregator `governance` fails on any failure/skip | full L2 | A + B | CRITICAL |
| AO-P1-007 | Validation agent | 006 | none (read-only) | — | Level 3 gate executed from a clean clone; report | L3 | A + B sign-off | CRITICAL |

Hotspots (single owner): `backend/pyproject.toml` + `uv.lock` (Coordinator; workers request dependency changes in their handoff), `.github/workflows/*`, `.pre-commit-config.yaml`, `compose.yaml` (W3), `frontend/package*.json` (W2).

Register IDs pre-allocated: W1 A-009/TD-012 · W2 A-010/TD-013 · W3 A-011/TD-014 · W4 A-012/TD-015 (use only if needed).

## Gate items expected to be not applicable

None. Phase 1 must execute every Level 3 item; item 9 (failure injection) applies to the foundation's own failure modes (database/Redis down → readiness fails closed; malformed request IDs; bad configuration).
