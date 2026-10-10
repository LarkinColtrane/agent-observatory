# Pre-Phase-1 governance review — Reviewer B (Concurrency + Architecture)

- Reviewer: independent agent, did not author the baseline
- Target: snapshot of tag `gov-baseline-v1.0.0` (commit e4d3154)
- Date: 2026-10-10
- Outcome: **REQUEST_CHANGES**
- Resolution of each finding: see [pre-phase-1-review-resolution.md](pre-phase-1-review-resolution.md)

Findings are recorded verbatim from the reviewer's report.

## Findings

**B-01 BLOCKING** — `docs/phases/P0-gate-report.md:17,21-23` + `phase-quality-gates.md:10` vs `phase-quality-gates.md:39-40,62-64`. Item 10 is `not_run`; the gate's own rule says that fails. n/a is only valid when "the phase plan marks" it — no `P0-plan.md` exists, so items 1, 3–7 are unapproved n/a too. Yet the register says P0 **closed** and immutable tag `gov-baseline-v1.0.0` was cut. Failure mode: P1 opens on an unreviewed baseline; any fixes from this review make the immutable v1.0.0 tag disagree with approved content, and the precedent "close with exception" lets any future gate close by coordinator fiat. Fix: set P0 to `open — pending review`; add a P0 plan approving n/a items; after both reviews re-run the gate and tag a new version (v1.0.1/v1.1.0); do not reuse v1.0.0.

**B-02 MAJOR** — `P0-gate-report.md:18` claims "6 assumptions, 2 debt items"; `technical-debt.yaml` has 3 (TD-001..003). The register check was not re-run after TD-003 was added — reported evidence that isn't real (contract rule 12). Fix: correct and re-do item 11.

**B-03 MAJOR** — Items 8 and 9 (`P0-gate-report.md:15-16`) are marked `pass` against criteria they don't meet. Item 8 requires a full-history scan (`security-baseline.md:17-18`), which was deferred; item 9 is defined as product failure injection (adapter disconnect, …), not checker tests. Failure mode: a secret in git history passes (demonstrated below). Fix: mark n/a-approved with debt link, not pass.

**B-04 MAJOR** — `component-ownership.md:41-43` vs `parallel-work-policy.md:32-36` and ADR-0001:5. Three contracts are `frozen@1.0.0` without step 2 of the freeze protocol (architecture + specialist review); the only decider was the Coordinator and the ADR has no Review section. Fix: set to `in review` until this and Reviewer A's review resolve.

**B-05 MAJOR** — P1 scope conflicts with the new phase order: `phase-quality-gates.md:11` ("universal event model contract"), ADR-0001:29-30 ("Phase 1 opens … starting with … the universal event model"), `assumptions.yaml:19-20` (A-001 validated "Phase 1"). Failure mode: the P1 opener follows the accepted ADR and freezes C1 before P2. Fix: full P0–P11 register in phase-quality-gates.md; ADR-0002 must supersede ADR-0001's P1 clause (ADRs are append-only); re-target A-001 to P2.

**B-06 MAJOR** — `assumptions.yaml:45-53` (A-004) and TD-001:19 say stack "not yet chosen"; the planned stack is decided. Fix: record in an ADR at P1 opening; update A-004.

**B-07 MAJOR** — `component-ownership.md:14-25`: planned paths (`contracts/events/`, `core/*`, `api/`, `ui/dashboards/`) presuppose a separate schema-first contracts tree and a non-modular-monolith layout; missing components for realtime (P5), analytics (P7), integrations (P9), control room (P10), auth. Failure mode: P1 scaffolds these paths and gives C1 a home before P2 decides its form. Fix: mark table illustrative, paths decided by the P1 stack ADR (e.g. `backend/src/observatory/<module>/`, `frontend/`); add missing components.

**B-08 MAJOR** — Shared hotspot files have no write protocol: `development-operating-contract.md:90`, `component-ownership.md:4`, `agent-task-contract.md:79`. Lifecycle says the owner "claims paths" in component-ownership.md but the file is "coordinator only"; DoD requires every task to append to assumptions/technical-debt YAML (owned by C12, outside owned_paths). Failure mode: two parallel branches both add `A-007`; integrator's "mechanical" resolution keeps both → duplicate id/ambiguous handoff references (checker catches only after the fact). Same for pyproject.toml/lockfiles/docker-compose under vague C11 "tooling configs". Fix: coordinator pre-allocates register IDs in the task contract (or IDs namespaced by task_id); claims recorded by coordinator at assignment; single-file hotspots serialized through one owner per integration window.

**B-09 MAJOR** — `parallel-work-policy.md:46-47`: Alembic orders migrations by a `down_revision` chain, not sequence numbers. Two parallel tasks both set `down_revision` = current head → multiple heads on merge; allocated "sequence numbers" don't prevent this. Fix: integrator rebases `down_revision` at merge; L2/L3 gate requires `alembic heads` == 1.

**B-10 MAJOR** — `parallel-work-policy.md:38-39`: no rule for who decides "breaking", nor for tasks already in review/integration queue consuming the old version; versions are table cells, not tied to a commit/tag. Failure mode: a handoff built against `events@1.0.0` merges after `1.1.0` frozen; L1/L2 pass on stale fixtures. Fix: version = git tag + path; integrator rejects handoffs whose `contracts.consumed` is superseded; every freeze change re-checks open tasks.

**B-11 MINOR** — Review deadlock/self-approval: `parallel-work-policy.md:34,63-64`, `development-operating-contract.md:31`. The coordinator drafts contracts, approves changes, and is final arbiter of design disputes; "architecture reviewer + relevant specialist" can be the same person (Reviewer B for concurrency-heavy contracts). Fix: coordinator-authored contracts need both reviewers' sign-off; no single person holds two roles.

**B-12 MINOR** — `agent-handoff-contract.md:25,65`, review `:74-75`: `partial`/`abandoned` doesn't transfer/release the path claim (successor writes unassigned paths); "reject → back to owner" has no round limit. Fix: coordinator re-assigns claim on any non-complete handoff; escalate after 2 rejections.

**B-13 MINOR** — Tag naming inconsistent: gate requires `phase-P<n>-v…` (`phase-quality-gates.md:55`) but P0 used `gov-baseline-v1.0.0`; item 7 "from previous gate tag" becomes ambiguous. Item 12 requires "pushed"; evidence only shows created.

**B-14 MINOR** — `scripts/check-governance.py:79-92`: a non-mapping YAML entry or top-level list crashes with AttributeError traceback rather than a reported error. Checker only validates presence/form, not governance state: does not check the gate report (not even that it exists), ADR-0001, `affects` references, severity/confidence enums, overlapping path claims, or freeze statuses. Fix: add, or stop citing the checker as gate evidence for state.

**B-15 NIT** — "8–10 agents" (`development-operating-contract.md:36`) is not a single limit; state one number. Outcome vocabulary in `review-checklist.md:21-26` differs from the reviewer outcomes used here.

## Checker runs performed by the reviewer (on scratchpad copies, `git init` + `git add -A`)

- Unmodified baseline: all four ok, PASS, rc=0.
- Scalar `- just-a-string` entry in technical-debt.yaml: AttributeError traceback, rc=1.
- assumptions.yaml replaced by a top-level list: AttributeError traceback, rc=1.
- Single copy with all of: P0-gate-report.md + ADR-0001 deleted (and their links), gate item 2 set not_run, overlapping claims on `core/` and `core/ingest/`, `affects: [C99, TD-999]`, severity `catastrophic`, repayment_trigger `""`, frozen contract status `wibble@9.9.9`: **PASS, rc=0**.
- AKIA-pattern key committed then `git rm`'d (history-only): **PASS**.
- Duplicate A-001 id: FAIL, detected.

## Verification rounds (Reviewer B's own results)

**Round 1 (staged tree) — REQUEST_CHANGES.** B-02, B-03, B-06, B-07, B-09,
B-10, B-12..B-15 resolved; B-01, B-04, B-05, B-08, B-11 partial. New: B-16
(MAJOR, review recorded before verdicts), B-17 (MAJOR, event-protocol
deferral removable by YAML edit), B-18 (MAJOR, claim overlap via globs/`./`,
duplicate tasks), B-19 (MAJOR, self-attested closure), B-20, B-21 (MINOR),
B-22 (NIT). Bypass probes b1, b1b, b3, b4, b5, b6 all passed the checker.

**Round 2 (commit 992eca2) — APPROVE_WITH_NOTES.** B-16..B-18, B-20..B-22 and
partials B-01, B-04, B-05, B-08 resolved; b1..b6 now fail. B-19 partial and
B-11 partial pending independent gate results. Notes (MINOR): B-23 verdict
check is consistency not authenticity (verdicts in HTML comments/fences or a
record outside `docs/reviews/` were accepted); B-24 P0 closable outside the
dedicated repo (local tag / look-alike remote). Both fixed in 368429f;
the independent validation agent confirmed the probes now fail.

## Post-migration review (dedicated repository)

**Review of 254e400 — APPROVE_WITH_NOTES.** Checker PASS, 68 tests OK;
legitimate closure sequence verified to pass on a local annotated tag (no
deadlock). Notes: B-25 (TD-004 repayable by YAML edit), B-26 (break-glass),
B-27 (up-to-date requirement × parallel PRs), `cancel-in-progress` on `main`,
B-28 (run 4 test claim), B-29 ("integration branch" stale), stale-doc list.
