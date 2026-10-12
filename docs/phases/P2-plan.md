# P2 Plan — Universal agent event protocol

- Phase: P2 · Opened: 2026-10-12 by owner instruction, once TD-022 was repaid (AO-P2-001) · Contract: ADR-0008 (AO-P2-002)
- Objective: a provider-neutral, versioned, immutable, deterministically serialised event protocol, with validation, canonical JSON, fingerprints, ordering and duplicate semantics, synthetic fixtures from three provider shapes, a versioned reference trace, and golden, property and adversarial tests.
- Out of scope (ADR-0003 order): adapters and SDK (P3), ingestion, event store and state engine (P4), realtime/WebSocket (P5), any UI or the visual office. Phase 2 defines what ingestion must do with duplicates, rejections and quarantine; it does not build ingestion.
- Team: Coordinator · W-P (protocol implementation, 003 then 004) · W-F (fixtures and tests, 005) · Reviewer A (security and privacy) · Reviewer B (protocol, methodology and temporal semantics) · Validation agent (gate). At most 3 agents are active at once.
- Dependency cutoff: no new dependencies are planned. The protocol uses Pydantic and the standard library; property tests are seeded and bounded, without a new library.

## Task graph

```
AO-P2-001 TD-022 (ADR-0007, core.telemetry, logging) ─> P2 opens
  └─> AO-P2-002 event-protocol contract (ADR-0008), approved by A+B
        └─> AO-P2-003 protocol core: ids, text/path safety, envelope, bounded codec, canonical JSON, fingerprint, validation, ordering, duplicates
              └─> AO-P2-004 taxonomy payloads, usage event, JSON Schema golden
                    └─> AO-P2-005 synthetic providers A/B/C, multi-agent reference trace, golden, property and adversarial tests
                          └─> AO-P2-006 adversarial review A+B; contract frozen (contract-event-protocol-v1.0.0)
                                └─> AO-P2-007 Level 3 gate (validation agent) ─> phase-P2-v1.0.0
```

Why the implementation is sequential: the envelope, payloads and codec share one package and its validation types. ADR-0003 freezes the protocol only at the end of P2, after adversarial review. Operating-contract rule 3 forbids two agents building against an unfrozen contract. So 003 → 004 → 005 run one after another, and 005 is written by a different agent from 003/004, so the fixtures independently check the contract. What does run in parallel: Reviewer A with Reviewer B at every review point, and the coordinator drafting ADR-0008 while AO-P2-001 is under review. The draft is committed only after P2 opens.

| Task | Owner | Deps | Owned paths | Acceptance | Tests (L1/L2) | Reviewer | Risk |
|---|---|---|---|---|---|---|---|
| AO-P2-001 | Coordinator | — | `docs/adr/0007-*`, `backend/src/observatory/core/{telemetry,logging}.py`, `backend/tests/unit/test_telemetry.py`, P2 records | ADR-0007 decisions 1–5; usage survives; secret redaction unchanged; adversarial tests | backend L1, unit | A + B | CRITICAL |
| AO-P2-002 | Coordinator | 001 | `docs/adr/0008-*`, `docs/contracts/`, `backend/pyproject.toml` (import-linter layer) | contract covers every item in the owner's P2 brief; approved by A+B | governance checker | A + B | CRITICAL |
| AO-P2-003 | W-P | 002 approved | `backend/src/observatory/events/` except `payloads.py`, `backend/tests/unit/events/` | ADR-0008 envelope, identity, time, codec limits, canonical JSON, fingerprint, validation codes, ordering, duplicates | backend L1, unit | A + B (006) | CRITICAL |
| AO-P2-004 | W-P | 003 | `backend/src/observatory/events/payloads.py`, `backend/tests/unit/events/test_payloads.py`, `docs/contracts/event-protocol-v1.schema.json` | 15 event types exactly as ADR-0008; schema golden | backend L1, unit | A + B (006) | HIGH |
| AO-P2-005 | W-F | 004 | `backend/tests/fixtures/events/`, `backend/tests/unit/events/test_{fixtures,golden,property,adversarial}.py` | providers A/B/C (synthetic) map to the same canonical trace; reference trace is versioned and byte-stable; bounded property and adversarial suites | unit | A + B (006) | HIGH |
| AO-P2-006 | Reviewer A, Reviewer B | 005 | `docs/reviews/phase-2-reviews.md` (verdicts) | adversarial review of contract + implementation; findings fixed by owners; contract frozen | reviewers re-run checks | — | CRITICAL |
| AO-P2-007 | Validation agent | 006 | `docs/phases/P2-gate-report.md` | Level 3 gate items 1–11, plus the owner's 44-item closure checklist, from a fresh clone | L3 | A + B sign-off | CRITICAL |

Hotspots (single owner): `backend/pyproject.toml` and `uv.lock` (Coordinator), `.github/workflows/*` (Coordinator), `docs/governance-state.yaml` and registers (Coordinator).

Register IDs pre-allocated (use only if needed): 001 TD-025 · 002 A-013/TD-026 · 003 A-014/TD-027 · 004 TD-028 · 005 A-015/TD-029 · 007 TD-030.

## Gate items expected to be not applicable

None of the twelve Level 3 items. Item 9 (failure injection) applies to the protocol's own failure modes: malformed, oversized, duplicate, conflicting, out-of-order, future-version and secret-bearing events, run through the codec and validator. There is no running service to inject into until P4; that limitation is stated in the gate report. In the owner's 44-item checklist, item 33 (frontend checks) is not applicable unless the frontend changes. The reason is recorded in the gate report.
