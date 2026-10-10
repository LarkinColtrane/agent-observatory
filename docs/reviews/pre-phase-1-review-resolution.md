# Pre-Phase-1 review — resolution and verification

Reviews: [Reviewer A](pre-phase-1-review-A.md) (REQUEST_CHANGES) ·
[Reviewer B](pre-phase-1-review-B.md) (REQUEST_CHANGES).
Every finding was fixed; none was converted into debt to proceed. Where a
finding concerns work that physically cannot happen yet (dedicated repo,
branch protection), it is recorded as **blocking** debt for Phase 1, not
accepted.

## Resolutions

| ID | Sev | Resolution | Where |
|---|---|---|---|
| B-01 / A-01 | BLOCK / MAJOR | P0 no longer "closed with exception": status `gate_review`; P0 plan approves n/a items explicitly; "exception" route removed; coordinator cannot waive gate items; new tag `phase-P0-v1.1.0` only after gate passes in the dedicated repo; `gov-baseline-v1.0.0` recorded as local-only and superseded. TD-003 trigger corrected to "before Phase 1 opens". Checker rejects closed phases with non-pass rows (regression test). | `phase-quality-gates.md`, `phases/P0-plan.md`, `phases/P0-gate-report.md`, `governance-state.yaml`, ADR-0001 Review, `technical-debt.yaml` |
| B-02 / A-02 | MAJOR | Count corrected; checker now prints register counts and gate item 11 quotes that output. Original wrong row kept under "Superseded runs". | `P0-gate-report.md`, checker |
| B-03 / A-03 | MAJOR | Item 8 now runs pinned, checksum-verified gitleaks over full history of all refs, plus dependency audit and SAST of the governance tooling. Item 9 is approved n/a (product failure injection); checker adversarial tests reported under item 11. Checker secret backstop now scans working tree, index, and all reachable history blobs, decodes bytes (non-UTF-8 safe), adds 8 credential formats, and is labelled a backstop, not a full scan. | `scripts/secret-scan.sh`, checker, `security-baseline.md`, gate report |
| B-04 | MAJOR | Process contracts re-frozen at 1.1.0 only after both reviewers; checker requires `reviewed_by: [reviewer-a, reviewer-b]` for any frozen contract. | `governance-state.yaml`, `component-ownership.md` |
| B-05 / A-04 | MAJOR | ADR-0003 fixes the phase order and supersedes ADR-0001's P1 clause; checker hard-codes the canonical order and forbids drafting the event protocol before P2 starts; A-001 re-targeted to P2; event field classes and invariants marked provisional. | ADR-0003, `roadmap.md`, checker, `assumptions.yaml`, `security-baseline.md`, `review-checklist.md` |
| B-06 | MAJOR | ADR-0002 records the stack; A-004 validated. | ADR-0002, `assumptions.yaml` |
| B-07 | MAJOR | Component table marked logical/illustrative; no directory paths; added C13 Identity & access, C14 Realtime, C15 Analytics, C16 External integrations; mapped to phases. | `component-ownership.md`, `governance-state.yaml` |
| B-08 | MAJOR | Shared-file write protocol: coordinator records claims and pre-allocates register IDs (`allocated_ids`); hotspots serialised one task per integration window. Checker rejects overlapping/prefix claims. | operating contract §4, task contract, `parallel-work-policy.md`, checker |
| B-09 | MAJOR | Alembic `down_revision` rebase at merge; `alembic heads` = 1 at L2 and L3. | `parallel-work-policy.md`, `phase-quality-gates.md`, `review-checklist.md` |
| B-10 | MAJOR | Contract version = git tag + path; Reviewer B decides "breaking"; all open/in-review/queued consumers paused and re-checked; integrator rejects handoffs consuming a superseded tag. | `parallel-work-policy.md`, handoff contract |
| B-11 | MINOR | Separation of duties: one role per agent; coordinator-authored artefacts need both reviewers; coordinator never approves own work. | operating contract §2, `parallel-work-policy.md`, `review-checklist.md` |
| B-12 | MINOR | Non-complete handoff does not transfer claims; coordinator re-assigns; escalate after 2 rejections. | handoff contract |
| B-13 / A-15 | MINOR / NIT | Tag convention `phase-P<n>-v<semver>` incl. P0; item 12 requires "pushed". Checker invoked with `-I`; PyYAML pinned. | `phase-quality-gates.md`, `rollback-policy.md`, `requirements-governance.txt`, README |
| B-14 | MINOR | Checker rewritten: no tracebacks (malformed YAML, scalar entries, non-git dir all reported cleanly); validates enums, cross-refs, phases, gate reports, contracts, claims, ADR index/Related ids; 40+ adversarial tests. | checker, `tests/governance/` |
| B-15 | NIT | Single limit: hard 10, target 8. Outcome vocabulary aligned to APPROVE / APPROVE_WITH_NOTES / REQUEST_CHANGES / BLOCK. | operating contract, `parallel-work-policy.md`, `review-checklist.md` |
| A-05 | MAJOR | Secret-incident exception to "never rewrite history": rotate → record (no value) in incident log → purge → re-scan. | `rollback-policy.md`, `security-incident-log.md` |
| A-06 | MAJOR | Quarantine fails closed: content fields dropped/hashed before persistence; short retention; restricted access. A-003 extended. | `security-baseline.md`, `assumptions.yaml` |
| A-07 | MAJOR | Fixtures synthetic by default; recordings only after scrubbing + Reviewer A sign-off; recordings ignored. | `security-baseline.md`, `.gitignore`, `review-checklist.md` |
| A-08 | MAJOR | Every governance file change needs independent review + Reviewer A/B sign-off; CODEOWNERS added; branch protection is blocking debt TD-004 (needs dedicated repo). | operating contract rules 7–8, §9, `review-checklist.md`, `.github/CODEOWNERS`, TD-004 |
| A-09 | MAJOR | See B-14: checker validates governance state. | checker |
| A-10 | MINOR | Allowed (ran, result) combinations defined; enforced for gate reports by the checker; CI link required as evidence once CI exists; machine validation of handoffs tracked as TD-006. | handoff contract, `phase-quality-gates.md`, checker, TD-006 |
| A-11 | MINOR | `.gitignore` extended; every path the reviewer listed verified ignored with `git check-ignore`. | `.gitignore` |
| A-12 | MINOR | Adapter authentication on ingest, provenance, default-deny; auth on WebSocket/SSE. | `security-baseline.md`, `review-checklist.md` |
| A-13 | MINOR | Phase rollback is schema-first (downgrade/restore), then code; expand/contract migrations. | `rollback-policy.md` |
| A-14 | MINOR | A-006 invalidated; TD-002 rewritten for the dedicated private repo, made high severity and blocking for P1; migration replays only project commits and scans history before/after. | registers, ADR-0004, `migration/dedicated-repo-migration.md` |

## Verification round 1 (both reviewers: REQUEST_CHANGES)

Reviewer A: A-02..A-13, A-15 RESOLVED; A-01, A-14 PARTIALLY_RESOLVED; new
findings N-01..N-08. Reviewer B: B-02, B-03, B-06, B-07, B-09, B-10, B-12..B-15
RESOLVED; B-01, B-04, B-05, B-08, B-11 PARTIALLY_RESOLVED; new findings
B-16..B-22. Bypass probes the reviewers demonstrated are now regression tests.

| ID | Sev | Finding (summary) | Resolution |
|---|---|---|---|
| N-01 / B-16 | MAJOR | Review recorded as passed (gate item 10, TD-003 repaid, `reviewed_by`, ADR-0002 header) before verdicts existed — the B-01 pattern again | All reverted to pending (item 10 `not_run`, TD-003 `open` and blocking P1, contracts `in_review` with empty `reviewed_by`). Checker now requires recorded approving final verdicts from **both** reviewers (latest verdict wins) before gate item 10 may be `pass` or any contract may claim review/`approved`/`frozen`. |
| N-02 | MAJOR | Pre-commit `--all-files` rewrote practice-repo `README.md`/`test.txt`; migration `git am` would fail | Both files restored byte-identical to `HEAD`; top-level `exclude:` for practice files in `.pre-commit-config.yaml`; migration rehearsal re-run on the new commit by the independent validation agent. |
| B-17 | MAJOR | Event-protocol deferral bypassable by deleting the entry or dropping `not_before_phase` | Checker hard-codes `event-protocol → P2`: entry must exist with that deferral. |
| B-18 / N-05 | MAJOR / MINOR | Claim overlap missed via globs, `./`, trailing `/`; duplicate task ids; claims for phases not in progress | Globs rejected; paths `normpath`-normalised; absolute/`..` rejected; duplicate task ids rejected; claim's phase (from `AO-P<n>-<nnn>`) must be `in_progress`. |
| B-19 / N-05 | MAJOR / MINOR | Closure self-attested: nonexistent tag, `dedicated: true` without remote, fake table above early "Superseded runs" | `closed` requires `gate_tag` of form `phase-P<n>-v<semver>` existing as an **annotated** tag; `dedicated: true` requires a git remote named `agent-observatory`; more than one "Superseded runs" heading rejected; frozen contracts require an existing annotated `contract-<id>-v<version>` tag. A control test proves legitimate closure still passes (no deadlock). |
| B-20 | MINOR | Contract tag names inconsistent | All docs use `contract-<id>-v<semver>`; checker enforces it. New `approved` status distinguishes "reviewed" from "tagged". |
| B-21 | MINOR | Roadmap allowed overlap; checker forbids it | Roadmap now says strictly sequential; overlap needs ADR + checker change. |
| B-22 | NIT | P0 closure circular ("pushed" recorded in the tagged commit) | Closure sequence documented: gate commit → tag+push → follow-up commit records `closed`. |
| B-11 (partial) | MINOR | Coordinator acted as integrator for P0 | An independent integration/validation agent re-ran the applicable gate items and the migration rehearsal; its results are what the gate report records. |
| N-03 | MINOR | Commit/tag messages unscanned; >5 MB blobs silently skipped; prefixed `*_PASSWORD=` assignments and user-less credentialed `redis://` URLs missed | Checker scans commit and annotated-tag messages; oversize blobs are reported as errors; generic pattern accepts prefixed names; credentialed-URL pattern accepts empty usernames. Tests added for each. |
| N-04 | MINOR | Pre-commit revs on mutable tags; no hashes; pre-commit version mismatch | Hooks pinned to commit SHAs; `requirements-governance.txt` fully pinned with hashes (resolved with an upload-date cutoff two weeks back); CI and docs use `--require-hashes`; gate re-run with the pinned pre-commit 4.0.1. |
| N-06 | MINOR | Branch protection/CODEOWNERS described as in force | Marked "target state — not yet in force (TD-002, TD-004)". |
| N-07 | MINOR | ADR-0002 silent on Redis data | Redis holds only redacted data; auth (+TLS outside local dev); persistence off or redacted-only. |
| N-08 | NIT | secret-scan prints only a count | Writes a redacted JSON report and prints rule/file/line/commit for each finding (never values). |

## Verification round 2 (both reviewers: APPROVE_WITH_NOTES)

| ID | Sev | Note | Resolution |
|---|---|---|---|
| A-note-1 / B-23 | MINOR | Verdict check is consistency, not authenticity; verdicts inside HTML comments/fences or in a record outside `docs/reviews/` were accepted | Verdicts parsed only after the `final-verdicts` marker with comments and fences stripped; record must be under `docs/reviews/`; operating contract states the limitation; authenticity tracked as TD-007 (enforced by branch protection, TD-004). Commit 368429f. |
| A-note-2 | MINOR | Claim overlap case-sensitive | Case-folded comparison + test. Commit 368429f. |
| B-24 | MINOR | P0 closable outside the dedicated repo | `closed` requires `dedicated: true`, an annotated gate tag that is an ancestor of HEAD, and a remote matching `LarkinColtrane/agent-observatory`. Commit 368429f. |
| N4b (validation agent) | MINOR | Remote regex not anchored to host | Host-anchored match + tests. Commit 4b1b7d0. |
| B-11 | MINOR | Coordinator acted as integrator | Gate items 2, 5, 8, 11 and the migration rehearsal were run by an independent integration/validation agent on 992eca2 and 368429f; the gate report records its results, including the corrections it found in the coordinator's draft. |
| B nit | NIT | Gate report environment line said pre-commit 4.6.2 | Corrected to the pinned 4.0.1 used by the validation agent. |

Reviewer reports with their own verification results:
[pre-phase-1-review-A.md](pre-phase-1-review-A.md) ·
[pre-phase-1-review-B.md](pre-phase-1-review-B.md).

## Final verdicts

Recorded in the form the checker parses (latest line per reviewer counts).
Each verdict was returned by the reviewer for commit 992eca2; its notes were
then fixed in 368429f/4b1b7d0 and confirmed by the independent validation
agent. The checker verifies consistency, not authorship (TD-007).

<!-- final-verdicts -->
- **Reviewer A final outcome:** APPROVE_WITH_NOTES — see [pre-phase-1-review-A.md](pre-phase-1-review-A.md), verification round 2
- **Reviewer B final outcome:** APPROVE_WITH_NOTES — see [pre-phase-1-review-B.md](pre-phase-1-review-B.md), verification round 2
