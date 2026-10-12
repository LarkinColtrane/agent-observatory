# P2 Plan — Universal agent event protocol

- Phase: P2 · Opened: 2026-10-12 by owner instruction, once TD-022 was repaid (AO-P2-001) · Contract: ADR-0008 (AO-P2-002)
- Objective: a provider-neutral, versioned, immutable, deterministically serialised event protocol, with validation, canonical JSON, fingerprints, ordering and duplicate semantics, synthetic fixtures from three provider shapes, a versioned reference trace, and golden, property and adversarial tests.
- Out of scope (ADR-0003 order): adapters and SDK (P3), ingestion, event store and state engine (P4), realtime/WebSocket (P5), any UI or the visual office. Phase 2 defines what ingestion must do with duplicates, rejections and quarantine; it does not build ingestion.
- Team: Coordinator · W-P (the single protocol implementer: 003, 004, 005 in sequence) · Reviewer A (security and privacy) · Reviewer B (protocol, methodology and temporal semantics, in addition to architecture and concurrency) · Validation agent (gate). At most 3 agents are active at once.
- Closure checklist: the owner's 44-item list is [P2-closure-checklist.md](P2-closure-checklist.md); the gate report answers every item.
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

Why one implementer, in sequence (review R-B-P2-001-02): ADR-0003 §3 freezes the protocol only at the end of P2, after adversarial review by both reviewers. Operating-contract rule 3 forbids two or more agents building against a contract that is not frozen. Both rules hold because exactly **one** agent, W-P, builds against ADR-0008 during P2: 003 → 004 → 005, sequentially. Reviewers attack it but do not build on it, and the validation agent only runs checks. No governance rule is relaxed.

Mechanism:
- ADR-0008 reaches `status: approved` with `reviewed_by: [reviewer-a, reviewer-b]` in `governance-state.yaml` before 003 starts.
- 003–005 list ADR-0008 under `inputs.adrs`, not `frozen_contracts`, because it has no tag yet.
- Any ADR-0008 change after approval needs both reviewers, and W-P is notified.
- At 006 the coordinator records the final freeze: pending tag `contract-event-protocol-v1.0.0` (`commit: self`), then `status: frozen` once the tag exists.
- Phase 3 builds only against that tag.

The freeze scope is ADR-0008, `observatory.events`, `docs/contracts/event-protocol-v1.schema.json`, and `observatory.core.telemetry` (ADR-0007, which the usage event reuses). In P2, changes to `core/telemetry.py` go through the coordinator as an ADR-0007 amendment signed by both reviewers (R-B-P2-001-05).

ADR-0008 is drafted after AO-P2-001 merges (ADR-0003 §2). The only design shown before P2 opened is the envelope proposal the owner asked for at kickoff ("First show me … 4. proposed canonical event envelope"). It is an input to AO-P2-002, which opens it to full review. What runs in parallel: Reviewer A with Reviewer B at every review point.

Claims (R-B-P2-001-07, -11): a phase-opening task cannot be claimed under the current checker, because claims need an `in_progress` phase. AO-P2-001 was coordinator-held and is recorded by its task contract and handoff. Claims use whole concrete prefixes. Review fixes in 006 go through coordinator-issued follow-up tasks with fresh claims, and the coordinator records the freeze and pending tag.

| Task | Owner | Deps | Owned paths | Acceptance | Tests (L1/L2) | Reviewer | Risk |
|---|---|---|---|---|---|---|---|
| AO-P2-001 | Coordinator | — | ADR-0007 (+ ADR-0005 status line, ADR index, security baseline), `backend/src/observatory/core/{telemetry,logging}.py`, `backend/tests/unit/test_telemetry.py`, governance fixture tests, P2 records | ADR-0007 decisions 1–5; usage survives; secret redaction unchanged; adversarial tests | backend L1, unit | A + B | CRITICAL |
| AO-P2-002 | Coordinator | 001 | `docs/adr/0008-*`, `docs/contracts/`, `backend/pyproject.toml` (import-linter layer, optional-layer syntax) | contract covers every item in the owner's P2 brief, including usage scope and cost provenance (R-B-P2-001-01, -09); approved by A+B | governance checker | A + B | CRITICAL |
| AO-P2-003 | W-P | 002 approved | `backend/src/observatory/events`, `backend/tests/unit/events` (payloads left as a stub for 004) | ADR-0008 envelope, identity, time, codec limits, canonical JSON, fingerprint, validation codes, ordering, duplicates | backend L1, unit | A + B (006) | CRITICAL |
| AO-P2-004 | W-P | 003 | `backend/src/observatory/events/payloads.py`, `backend/tests/unit/events/test_payloads.py`, `docs/contracts/event-protocol-v1.schema.json` | 15 event types exactly as ADR-0008; schema golden | backend L1, unit | A + B (006) | HIGH |
| AO-P2-005 | W-P | 004 | `backend/tests/fixtures/events`, `backend/tests/unit/events` | providers A/B/C (synthetic) map to the same canonical trace; reference trace is versioned and byte-stable; bounded property and adversarial suites | unit | A + B (006) | HIGH |
| AO-P2-006 | Reviewer A, Reviewer B | 005 | `docs/reviews/phase-2-reviews.md` (verdicts) | adversarial review of contract + implementation; a reviewer derives canonical bytes and fingerprints for a small set from ADR-0008 alone and compares them with W-P's goldens (the independent check that a second fixture author would have given, R-B-P2-001-15); fixes via coordinator follow-up tasks; coordinator records the freeze | reviewers re-run checks | — | CRITICAL |
| AO-P2-007 | Validation agent | 006 | `docs/phases/P2-gate-report.md` | Level 3 gate items 1–11, plus the owner's 44-item closure checklist, from a fresh clone | L3 | A + B sign-off | CRITICAL |

Hotspots (single owner): `backend/pyproject.toml` and `uv.lock` (Coordinator), `.github/workflows/*` (Coordinator), `docs/governance-state.yaml` and registers (Coordinator).

Register IDs pre-allocated (use only if needed): 001 TD-025 · 002 A-013/TD-026 · 003 A-014/TD-027 · 004 TD-028 · 005 A-015/TD-029 · 007 TD-030.

## Gate items expected to be not applicable

None of the twelve Level 3 items. Item 9 (failure injection) applies to the protocol's own failure modes: malformed, oversized, duplicate, conflicting, out-of-order, future-version and secret-bearing events, run through the codec and validator. There is no running service to inject into until P4; that limitation is stated in the gate report. In the owner's 44-item checklist ([P2-closure-checklist.md](P2-closure-checklist.md)), item 33 (frontend checks) is not applicable unless the frontend changes. The reason is recorded in the gate report.
