# P0 post-publication closure evidence (TD-004)

Date: 2026-10-10 (20:04–20:10 UTC). Phase 0 itself closed earlier at
`phase-P0-v1.1.0` → `8ce0ed3`; this records the branch-protection verification
that became possible once the repository was public.

## Repository

| Item | Evidence | Source |
|---|---|---|
| Visibility | `public` (`private: false`, `updated_at` 2026-10-10T20:04:11Z) | `GET /repos/LarkinColtrane/agent-observatory` |
| Default branch | `main` | same |
| Merge methods | squash only (merge commits and rebase disabled); auto-delete head branches on | same |
| Earlier read (20:02 UTC) | `private` — verification correctly stopped then | same |

## Ruleset `main-protection` (id 24851582)

Read via `GET /repos/{repo}/rulesets/24851582` and
`GET /repos/{repo}/rules/branches/{main,protection-probe}` (readable once public):

| Property | Value |
|---|---|
| Enforcement | `active` |
| Bypass actors | `[]`; `current_user_can_bypass: never` |
| Targets | `~DEFAULT_BRANCH` (= `main`), `refs/heads/protection-probe` |
| `deletion` | on |
| `non_fast_forward` (block force push) | on |
| `pull_request` | required approvals **0**, review-thread resolution **on**, Code Owner review off, dismiss-stale-reviews off |
| `required_status_checks` | `governance`, integration_id 15368 (GitHub Actions — the app that runs `.github/workflows/governance.yml` job `governance`); strict (branch up to date) **on** |
| Effective rules on `main` and `protection-probe` | identical 4 rules from this ruleset |

Deviations from the planned configuration, neither weakening protection:
the ruleset's allowed merge methods list merge/squash/rebase, but the
repository setting allows only squash, so squash-only is what is enforced;
dismiss-stale-reviews is off, which has no effect while 0 approvals are
required. (`docs/repository-settings.md` notes both for the owner.)

## Behavioural probes (`protection-probe` only; `main` never probed)

| Probe | Identity | Result | Evidence |
|---|---|---|---|
| A. Direct push of a new commit | agent session (owner identity via Claude GitHub App) | **REJECTED** by GitHub | `! [remote rejected] HEAD -> protection-probe (push declined due to repository rule violations)`; "Changes must be made through a pull request"; "Required status check \"governance\" is expected" |
| B. Force push (rewind to parent) | agent session | **REJECTED** by GitHub | `! [remote rejected] 254e400^ -> protection-probe (push declined due to repository rule violations)`; "Changes must be made through a pull request"; "Required status check \"governance\" is failing" |
| C. Deletion | GitHub Actions token (temporary PR-only job, never on `main`) | **REJECTED** by GitHub | `remote: error: GH013: Repository rule violations found for refs/heads/protection-probe` · `- Cannot delete this branch` · `! [remote rejected] protection-probe (push declined due to repository rule violations)` (PR #1, job 114302298098) |

`protection-probe` remained at `254e400` after every probe; `main` remained
at `8bd54c0` throughout. The session's own deletion attempts were refused by
the session git proxy (HTTP 403) before reaching GitHub, so they are not
counted as evidence; probe C supplies the GitHub-level evidence. The first
run of probe C (job 114301961360) aborted on the expected push failure
because the default shell uses `-e`; the branch was not deleted, and the
corrected run is the evidence above.

## Main protection without touching `main`

`main` is targeted by the same active ruleset (`GET rules/branches/main`
returns the same 4 rules) and `GET branches/main` reports `protected: true`.
CI's `scripts/check-repo-protection.py` reads `main` as protected with
`governance` required. Probes A–C demonstrate those rules are enforced
against both identities that can write to this repository.

## Workflow self-test

This evidence was merged through the protected path: feature branch
`verify/p0-public-closure` → PR #1 → `governance` check → squash merge into
`main` (no bypass). The temporary probe job was removed before the merge.

## Public-repository security settings

Dependency graph on; secret scanning and push protection **enabled** by the
owner after this closure (verified 21:22 UTC; TD-011 repaid), in addition to
gitleaks in pre-commit and CI; ruleset follow-ups applied (squash-only
allowed merge method, dismiss stale approvals on);
Dependabot alerts and Actions default token permissions not verifiable from
the session (proxy 403).

## Publication metadata (non-blocking)

Recorded as debt: TD-008 (no license — owner decision), TD-009 (root README,
SECURITY.md, CONTRIBUTING.md; Claude session identifiers in commit trailers
are now public metadata and are not removed; "Quant Autonomy" mention; unsigned
tag object), TD-010 (Node.js 20 action deprecation).
