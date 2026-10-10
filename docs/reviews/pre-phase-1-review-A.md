# Pre-Phase-1 governance review — Reviewer A (Security + Data integrity)

- Reviewer: independent agent, did not author the baseline
- Target: snapshot of tag `gov-baseline-v1.0.0` (commit e4d3154)
- Date: 2026-10-10
- Outcome: **REQUEST_CHANGES**
- Resolution of each finding: see [pre-phase-1-review-resolution.md](pre-phase-1-review-resolution.md)

Findings are recorded verbatim from the reviewer's report. No secret values
appear here; demonstrations used synthetic patterns only.

## Findings

**A-01 MAJOR** — `phase-quality-gates.md:10`, `P0-gate-report.md:17,21–23`, TD-003. Failure mode: gate report records item 10 `not_run` yet P0 is marked **closed** and tagged — violating the gates doc's own rule (`phase-quality-gates.md:62–64`: "any `not_run` that is not an approved `n/a` does not pass"), and `n/a` requires a phase plan (lines 39–40) that doesn't exist. The coordinator authored, approved and closed its own work (operating contract :31, rule 7). Tags are immutable (`rollback-policy.md:20`), so `gov-baseline-v1.0.0` permanently certifies an unreviewed baseline as gated, and sets precedent for "closed with exception" on any future phase. TD-003's trigger ("First task of Phase 1") lets P1 open pre-review. Fix: set P0 to `open (pending review)`; only close + tag a new version (`gov-baseline-v1.0.1` or `phase-P0-v1.0.0`) after both reviews; remove or formally define the "exception" path (who approves; coordinator can't approve own); change TD-003 trigger to "before Phase 1 opens".

**A-02 MAJOR** — `P0-gate-report.md:18`. Failure mode: row 11 claims manual register review "pass" with "2 debt items"; `technical-debt.yaml` actually has 3 (TD-003). The truthful-reporting artifact itself contains a false fact, so a gate check claimed "registers current" was not. Fix: correct; have the checker emit register counts and the gate report quote that output.

**A-03 MAJOR** — `P0-gate-report.md:15`; `check-governance.py:52–58,105–121`; `security-baseline.md:17–18`. Failure mode: row 8 "Security checks: pass" rests on a working-tree regex scan that (demonstrated) misses history-only secrets, staged-but-clean content, non-UTF-8 files, and most common credential formats. Migrating to the private repo with history would carry a leaked secret across while the gate says "clean". L3 item 8 also requires dependency audit + SAST, neither run. Fix: mark row 8 `partial` with scope; before migration run gitleaks (or equivalent) over full history of all refs and record command/result; in the checker scan index (`git grep --cached`) and history, decode with `errors="replace"`, add patterns for `github_pat_`, credentialed URLs, JWTs, Slack webhooks, `AIza` keys and generic `(password|secret|token|api_key)\s*[:=]`; rename the checker output so it doesn't read as a full secret scan.

**A-04 MAJOR** — Premature event-model commitments: ADR-0001:29–30 ("Phase 1 … universal event model contract"); `phase-quality-gates.md:11`; `assumptions.yaml:19` (A-001 "Phase 1"); `security-baseline.md:34–35` (fixes `metadata/content/credential` field classes); `review-checklist.md:60–61` (fixes invariants). Failure mode: ADR-0001 is accepted and ADRs are append-only — a Phase 1 agent following it will design/freeze the event model in P1, contradicting the planned reorder. Fix: a superseding ADR (or ADR-0002) amends phase sequence (P1 foundation, P2 event protocol); update phase register and A-001; mark field classification and invariants "provisional — defined by Phase 2 contract".

**A-05 MAJOR** — `rollback-policy.md:17–20,43` vs `security-baseline.md:19–20`. Failure mode: a token is committed to `main`; rollback policy mandates revert and forbids history rewriting, so the token stays in history permanently and the baseline's "then remove it" is impossible; the incident is recorded "in the gate report" (late, committed, invites pasting the value). Fix: explicit exception permitting history purge for secret incidents (coordinator-approved), ordering: revoke/rotate → purge (or archive repo) → re-scan → record incident immediately, without the value, in a dedicated incident log.

**A-06 MAJOR** — `security-baseline.md:24–26` vs `:36`. Failure mode: an adapter sends a malformed event containing an `authorization` header; schema validation fails → event is "quarantined"; redaction is only defined for parsed events, so the raw credential is persisted at rest. Fix: quarantine is redacted fail-closed (content fields dropped/hashed), short retention, restricted access.

**A-07 MAJOR** — `security-baseline.md` has no test-fixture rule. Failure mode: adapter authors record real agent transcripts (prompts, file contents, tokens) as fixtures; the regex scan misses most (A-03). Fix: fixtures must be synthetic or scrubbed + security-reviewed; real recordings never committed; add fixture/recording directories to scan and `.gitignore`.

**A-08 MAJOR** — `review-checklist.md:7`; operating contract :115–117. Failure mode: only the operating contract requires ADR + specialist sign-off to change; someone can weaken `security-baseline.md` or `rollback-policy.md` (e.g. delete "never logged") as a "docs only" change where review is optional. Fix: all governance files under `docs/` require independent review + Reviewer A or B sign-off; add CODEOWNERS/branch protection in the new repo.

**A-09 MAJOR** — Checker validates no governance state. Failure mode: frozen-contract register points to a nonexistent path and parallel work starts against a "frozen" contract that doesn't exist, checker PASS. Fix: verify frozen-register paths exist; cross-reference `affects`/`component` against C-ids and ADR `Related` against A-/TD- ids; validate enum fields (confidence, severity); verify phase register vs gate report consistency (closed ⇒ report exists with no `fail`/unapproved `not_run`); require ADR files and gate reports.

**A-10 MINOR** — Handoff contract :53–57 and gate report columns. Failure mode: `ran: false` + `result: pass` is a legal entry; reviewers re-run only L1 (line 73), so L2 claims are unchecked. Fix: constrain allowed combinations (validate once handoffs are machine-readable); require CI run link as evidence once CI exists.

**A-11 MINOR** — `.gitignore:1–13` misses `.envrc`, `.netrc`, `.npmrc`, `.pypirc`, `*.tfstate*`, `kubeconfig`, `.aws/`, `id_ecdsa*`, `service-account*.json`, `*.dump`/`*.sql.gz`, local Postgres/Redis data dirs, `*.log` — relevant given the Postgres/Redis stack.

**A-12 MINOR** — `security-baseline.md:41–45`. Failure mode: ingest path not covered by authentication; an unauthenticated/spoofed adapter can inject fabricated agent events (integrity failure). Fix: adapter identity/auth on ingest, provenance recorded per event, default-deny; auth on WebSocket/SSE streams.

**A-13 MINOR** — `rollback-policy.md:29–30`. Failure mode: phase rollback reverts code while Postgres is migrated forward → app runs against an unknown schema. Fix: down-migrate (or restore) before reverting code; require expand/contract migrations.

**A-14 MINOR** — `assumptions.yaml:67–76`, `technical-debt.yaml:22–32`: A-006/TD-002 are Og-Repo-specific; update for the dedicated private repo; migrate with fresh/scanned history (A-03) and re-tag there.

**A-15 NIT** — README runs the checker without `-I`; PyYAML unpinned. Phase 0 tag name `gov-baseline-*` deviates from the `phase-P<n>-v*` convention (`phase-quality-gates.md:55`).

## Checker gaps demonstrated by the reviewer (`python3 -I scripts/check-governance.py` on `git init`+commit copies)

Unmodified baseline: PASS (exit 0). Then:

- Secret only in history (AKIA committed then `git rm`+commit): PASS, exit 0.
- Staged secret (AKIA staged; working tree overwritten clean): PASS, exit 0.
- Common formats (`github_pat_…`, credentialed `postgres://` URL [example value redacted], AWS secret access key, JWT, Slack webhook URL, `AIza…` key in a tracked config.yaml): PASS, exit 0 — none detected.
- Non-UTF-8 file containing an AKIA key: PASS, exit 0 (silently skipped).
- Bad register data (`affects: [C99, TD-777]`, `confidence: banana`, `owner: ""`, `severity: catastrophic`, `component: C42`, `repayment_trigger: null`, ADR Related `A-999, TD-404`): PASS.
- Empty registers (`assumptions: []`, `debt: []`): PASS.
- Inconsistent phase state (gate row 8 → FAIL, P1 marked open, frozen contract path → `docs/does-not-exist.md`): PASS.
- Missing records (gate report and ADR-0001 deleted, index rows removed): PASS.
- Bad links (`../../…/etc/passwd`, reference-style `[y][ref]` → nowhere.md, `<missing.md>`): PASS.
- Register entry that is a plain string: `AttributeError` traceback (exit 1) — should be a clean FAIL.
- Not a git repo: `CalledProcessError` traceback (exit 1).
- `.gitignore`: `.envrc`, `.netrc`, `.npmrc`, `.pypirc`, `.aws/credentials`, `kubeconfig`, `id_ecdsa`, `secrets.yaml`, `service-account.json`, `terraform.tfstate` all addable (not ignored).

Positive: the checker never prints matched values (file + truncated pattern only).

## Verification rounds (Reviewer A's own results)

**Round 1 (staged tree) — REQUEST_CHANGES.** A-02..A-13, A-15 resolved; A-01,
A-14 partial. New: N-01 (MAJOR, review recorded before it happened), N-02
(MAJOR, pre-commit rewrote practice-repo files, migration `git am` failed),
N-03..N-08 (MINOR/NIT). Demonstrated: commit-message and tag-message
secrets, 6 MB blob, prefixed password variable, user-less credentialed URL,
self-attested closure (s1/s2) and claim globs (s3) all passed the checker.

**Round 2 (commit 992eca2) — APPROVE_WITH_NOTES.** N-01..N-08, A-01, A-14
resolved. Re-ran all round-1 attacks on clones: each now fails (rc=1) with
the expected message; no secret value echoed. Notes (MINOR): pasted verdict
lines are indistinguishable from real ones (→ TD-007, enforced by TD-004);
claim overlap was case-sensitive (fixed in 368429f).
