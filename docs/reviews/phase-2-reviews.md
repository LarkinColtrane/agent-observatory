# Phase 2 reviews

Independent reviews of Phase 2 work (plan: [P2-plan.md](../phases/P2-plan.md)).
Reviewer A covers security and privacy; Reviewer B covers protocol design,
methodology and temporal semantics, in addition to architecture and
concurrency (operating contract §2). Reviewers do not modify the author's
branch; reproductions run in their own clones. Each section lists findings
with their disposition and the final verdict.

## AO-P2-001 — TD-022 typed usage telemetry (ADR-0007) and P2 opening (coordinator; reviewers A and B)

**Reviewer A round 1** (`c059348`): REQUEST_CHANGES. Passed: ruff, format, mypy,
import-linter, bandit, 539 unit tests. Type and range checks held against bool,
float, Decimal, numeric strings, non-ASCII digits, huge, negative and
NaN/inf values, int/str subclasses, `model_construct`, `setattr`,
`UsageMetrics` subclasses and secret-named keys.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-P2-001-01 | blocker | A validated `Money` subclass with a relaxed `amount` passed un-revalidated, and its text reached JSON and console logs without the text backstop. This was a regression against `main`. | fixed (`cb299d6`): `_exact_money` before-validator rejects any non-exact model and re-validates an exact `Money` as a mapping; `usage_log_fields` returns None for any other money value; tests |
| R-A-P2-001-02 | minor | Nested console extras and the msg/args path rendered the raw usage object | fixed: `redact` resolves usage once into `_ValidatedUsage` on every path |
| R-A-P2-001-03 | minor | No `Money`-subclass test; TD-022 text over-claimed | fixed: tests added and text reworded |
| R-A-P2-001-04 | nit | An unusual exception could drop the record | fixed: fail closed on any exception |

**Reviewer A round 2** (`cb299d6`): APPROVE_WITH_NOTES. 01–04 verified fixed (probes p1–p4).

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-P2-001-05 | minor | A hand-built private `_ValidatedUsage` was trusted | fixed (`ea7be5b`): every `_ValidatedUsage` is re-validated in `redact`; test |
| R-A-P2-001-06 | nit | Pydantic errors echo a truncated rejected value | fixed: `hide_input_in_errors=True`; test |

**Reviewer A round 3** (`ea7be5b`): APPROVE. 582 unit tests; probes p1–p5 show
no leak and no accepted bad value. The subset rules have no security impact.

**Reviewer B round 1** (`c059348`): APPROVE_WITH_NOTES. Checker, artifacts, 212
governance tests, and backend L1 plus unit tests all pass in a fresh `uv sync`
venv. Setting TD-022 back to open makes the checker fail, so P2 cannot open
while TD-022 is open.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-P2-001-01 | major | Usage field semantics undefined (cache inclusion, reasoning, scope, cross-checks) | fixed: ADR-0007 Semantics paragraph; subset rules enforced with tests; scope belongs to the carrying record (ADR-0008) |
| R-B-P2-001-02 | major | The "sequential" argument does not satisfy rule 3 with two building agents | fixed: one implementer (W-P) owns 003–005, so exactly one agent builds against ADR-0008 before the end-of-P2 freeze; mechanism stated in the plan |
| R-B-P2-001-03 | major | Plan drafted ADR-0008 before P2 opened | fixed: the plan says ADR-0008 is drafted after AO-P2-001 merges and cites the owner's explicit kickoff request for the envelope proposal |
| R-B-P2-001-04 | minor | TD-022 repaid and ADR accepted before verdicts were recorded | merge condition: met by this record, the ADR Review line and the handoff, all written before merge |
| R-B-P2-001-05 | minor | `core/telemetry.py` had no P2 owner or freeze scope | fixed: plan routes changes through an ADR-0007 amendment; freeze scope includes it |
| R-B-P2-001-06 | minor | ADR-0005 amendment not visible in governance-state | fixed: comment on the `phase1-foundation` entry |
| R-B-P2-001-07 | minor | Writes outside `owned_paths`; no handoff; phase-opening task unclaimable | fixed: paths added, handoff written, plan explains the claim limitation |
| R-B-P2-001-08 | minor | Nested console usage was an inconsistent half-exemption | fixed by R-A-P2-001-02 |
| R-B-P2-001-09 | minor | Estimated cost has no pricing provenance | deferred to AO-P2-002 (acceptance criterion AC4; `pricing_ref` in the draft) |
| R-B-P2-001-10 | minor | 44-item checklist not in the repo | fixed: `docs/phases/P2-closure-checklist.md` |
| R-B-P2-001-11 | minor | 006 ownership and glob-like claims | fixed: follow-up tasks; coordinator records the freeze; whole prefixes |
| R-B-P2-001-12 | nit | Fixture points P2 at the P1 plan | fixed |
| R-B-P2-001-13 | nit | Reviewer B role wording | fixed |
| R-B-P2-001-14 | nit | import-linter core layering; optional-layer syntax | deferred to AO-P2-002 |

**Reviewer B round 2** (`ea7be5b`): APPROVE_WITH_NOTES. Checker, artifacts and
governance tests pass; backend L1, 582 unit tests and bandit pass. Probes: subset
violations rejected without echo; forged nested `Money` and hand-built
`_ValidatedUsage` are `[REDACTED]`.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-P2-001-15 | minor | With one implementer, the goldens lose their independent author | fixed: AO-P2-006 acceptance adds an independent derivation of canonical bytes and fingerprints from ADR-0008 alone |
| R-B-P2-001-16 | minor | AO-P2-002 task lacked the usage-scope and cost-provenance criterion | fixed: AC4 |

<!-- final-verdicts -->
- **Reviewer A final outcome:** APPROVE — AO-P2-001 round 3 (`ea7be5b`)
- **Reviewer B final outcome:** APPROVE_WITH_NOTES — AO-P2-001 round 2 (`ea7be5b`), notes 15 and 16 applied before merge
