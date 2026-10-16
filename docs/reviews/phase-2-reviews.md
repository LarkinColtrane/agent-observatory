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

## AO-P2-003..005 and AO-P2-008: event protocol implementation (w-p-protocol), AO-P2-006 adversarial review (reviewers A and B)

These are fresh reviewer agents: Reviewer A (security and privacy) and
Reviewer B (protocol, methodology and temporal semantics). Each reviewed in
an independent clone with a fresh `uv sync --locked` venv. Probes and
derivation scripts were kept outside the repository.

**Round 1** (`918050c`): Reviewer A REQUEST_CHANGES, Reviewer B APPROVE_WITH_NOTES.

Checks: ruff, format, mypy, import-linter and bandit clean; 1208 unit tests
passed with 98.9% coverage on `observatory.events`; the governance checker,
artifact checker, governance tests and gitleaks all clean.

Reviewer B's independent derivation from ADR-0008 alone reproduced every
pinned canonical byte string, both fingerprints, the derived event id and
the trace SHA-256. Every trace line was a fixed point, and B's own
`canonical_order` agreed with the code on 3000 of 3000 random sets.
Mutation testing killed 19 of 24 mutants.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-P2-006-01 | major | A value starting with `[REDACTED]` counted as already redacted (events and `core.logging`); partial detector masks left the rest of a secret | fixed: C18, an exact `[REDACTED]` rule and whole-value masking in both |
| R-A-P2-006-02 | major | Quadratic option scan (3.9 s for a 64 KiB event) | fixed: one tokenisation per string, about 30 ms; scaling test |
| R-A-P2-006-03 | major | CLI forms missed (mysql not as first word, short-option clusters, sshpass, redis-cli, `-passin pass:`, MYSQL_PWD, `=>`, wide spacing) | fixed: C20 |
| R-A-P2-006-04 | major | Quoted values masked only up to the first space | fixed: C19 |
| R-A-P2-006-05 | minor | Public `recorded_rules` could stamp a new event with older rules | fixed: C23, private and token-bound |
| R-A-P2-006-06 | minor | `model_validate_json` and `strict=False` bypassed parse checks | fixed: C22 |
| R-A-P2-006-07 | minor | A forbidden character could hide a secret and turn a drop into a quarantine | fixed: C21, the stripped-form scan |
| R-A-P2-006-08, R-B-P2-006-07 | minor | Duplicate `history:` key on A-001; the checker did not reject duplicate keys | fixed: the history is merged (`7c62318`) and the governance checker now rejects duplicate keys, with tests (`f8f6afd`) |
| R-A-P2-006-09 | nit | TD-026 did not cover RelPaths | fixed |
| R-A-P2-006-10, R-B-P2-006-09 | nit | Private `_normalize_key` imported across layers | fixed: public `normalize_key` |
| R-A-P2-006-11, R-B-P2-006-10 | nit / info | Events are process-local; the Unicode pin was only tested | fixed: C24, import-time assertion and documentation |
| R-A-P2-006-12 | nit | gitleaks `--working-tree` flags gitignored `.pyc` files | declined: the scanner config is not changed to quiet local noise; CI is unaffected; scan a clean tree |
| R-B-P2-006-01 | medium | `content_fingerprint` input with no `occurred_at` was ambiguous | fixed: C14 (`"time":{}` kept) |
| R-B-P2-006-02 | medium | The informative schema rejected every extension event | fixed: the schema admits the extension pattern; test; C26 |
| R-B-P2-006-03 | low | C10 named no code | fixed: C15 |
| R-B-P2-006-04 | low | The `X` exclusion dropped real currencies | fixed: C16, 164 codes |
| R-B-P2-006-05 | low | Tool names with spaces; loosening not classified | fixed: C17 and §16 |
| R-B-P2-006-06 | low | Three surviving mutants | fixed: tests kill them |
| R-B-P2-006-08 | low | Payload models not re-exported (§17) | fixed |
| R-B-P2-006-11 | info | Reference-trace narrative gaps | fixed: trace v1 regenerated (59 events, dependency order, coordinator terminated, one stream-less event without `occurred_at`) |
| R-B-P2-006-12 | info | Projection scope; combining duplicate checks; schema tooling regeneration; handoff commit ids | fixed: Id-only stripping, C25, C26, handoffs note the squash |

**Round 2** (`9eead67`): Reviewer A APPROVE_WITH_NOTES, Reviewer B APPROVE_WITH_NOTES.

- Reviewer A re-ran every probe. The quadratic cases now take 21–28 ms, 21
  new 64 KiB worst cases stay at or below 145 ms, and a 40,000-case
  `sanitize_text` fuzz found 0 failures.
- Reviewer B's derivation matched the regenerated trace (`0ee1ee7e…2e4b`),
  and 23 of 24 mutants were killed. The survivor is equivalent.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-P2-006-13 | minor | JSON mode was refused only on `Event`'s own methods; check 7 did not run at construction | fixed: refused on every route via `info.mode`; check 7 at construction; C22 clause |
| R-A-P2-006-14 | minor | `Cookie` and `Authorization` values were not whole-line in the events text tier | fixed: C18 whole-line rule |
| R-A-P2-006-15 | nit | A `RecordedEvent` subclass could downgrade rules | fixed: `Event` and `RecordedEvent` cannot be subclassed |
| R-B-P2-006-N1 | low | C17 was not injective for names starting with `h.` | fixed: C17 hashes those too |
| R-B-P2-006-N2 | info | In the trace, the coordinator terminates after `session.ended`, and a parent task completes before its subtask; both are legal | P4 replay note: neither is an error |

**Round 3** (`af8f58d`): Reviewer A APPROVE, Reviewer B APPROVE.

- Both reviewers re-ran their checks: 1319 unit tests passed, and coverage
  on `observatory.events` was 98.7–99%.
- Reviewer B's derivation was unchanged.
- Reviewer A's remaining nit is recorded as debt TD-027, which blocks P3: a
  whole-line value that starts with a quote ends at the closing quote, so
  `sanitize_text` can leave a trailing `sid=` value.
- Both reviewers state that ADR-0008 with clarifications C0–C26 can be frozen.

<!-- final-verdicts -->
- **Reviewer A final outcome:** APPROVE — AO-P2-001 round 3 (`ea7be5b`)
- **Reviewer B final outcome:** APPROVE_WITH_NOTES — AO-P2-001 round 2 (`ea7be5b`), notes 15 and 16 applied before merge
- **Reviewer A final outcome:** APPROVE — AO-P2-003..005 and AO-P2-008 implementation, AO-P2-006 round 3 (`af8f58d`)
- **Reviewer B final outcome:** APPROVE — AO-P2-003..005 and AO-P2-008 implementation, AO-P2-006 round 3 (`af8f58d`)
