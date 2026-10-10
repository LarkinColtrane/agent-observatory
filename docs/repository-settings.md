# Repository settings — `LarkinColtrane/agent-observatory`

Status: **partially applied** (TD-004). Last verified: 2026-10-10.

The agent cannot change repository settings: the session proxy rejects
settings writes (HTTP 403, "Repository settings writes are not permitted
through this proxy") and the Claude GitHub App lacks the *Administration*
permission needed for branch protection or rulesets (HTTP 403, "Resource not
accessible by integration"). The owner applies the items marked **Owner**.

## Current state (read via API, 2026-10-10)

| Setting | Value | Source |
|---|---|---|
| Visibility | **private** | created by owner; verified via API |
| Default branch | `main` | verified via API |
| Wiki | disabled | verified via API |
| Issues | enabled (kept) | verified via API |
| Projects | enabled → **Owner: disable** (unused) | |
| Merge methods | merge, squash, rebase all enabled → **Owner: squash only** | |
| Auto-delete head branches | off → **Owner: enable** | |
| Branch protection / rulesets on `main` | none → **Owner: configure (below)** | |

## Policy decisions

- **Squash merge only.** One reviewed commit per task on `main`, matching the
  task/handoff model; task branches are deleted after merge.
- **Wiki and Projects off.** Governance lives in `docs/` under review; no
  unreviewed side channels.
- **Issues on.** Used for the task board.

## Branch protection for `main` (Owner)

Settings → Branches → Add branch protection rule (or Settings → Rules →
Rulesets → New branch ruleset targeting `main`):

| Rule | Value | Why |
|---|---|---|
| Require a pull request before merging | **on** | All future work arrives as reviewed PRs |
| Required approvals | **0 for now** (see below) | Prevents lock-out on a single-human account |
| Dismiss stale approvals on new commits | **on** | Approvals apply to the reviewed diff only |
| Require conversation resolution | **on** | No unresolved review threads at merge |
| Require status checks to pass | **on**, require **`governance`** | This check exists and passes on `main` |
| Require branches to be up to date | **on** | Checks run against current `main` |
| Allow force pushes | **off** | Rollback policy: never rewrite published history |
| Allow deletions | **off** | |
| Do not allow bypassing / include administrators | **on** | Rules apply to everyone, including agents pushing as the owner |

**Why 0 required approvals today:** the agent pushes and opens PRs as the
owner's GitHub identity, and GitHub does not let an author approve their own
PR. Requiring 1 approval would make every PR unmergeable unless rules are
bypassed. Independent review is still mandatory by governance (reviewer
verdicts recorded under `docs/reviews/`, enforced by the checker); its
authenticity gap is TD-007. Raise required approvals to 1 and enable
"Require review from Code Owners" as soon as a second human (or a separate
reviewer identity) exists.

**Lock-out check:** with these rules the owner can still merge a PR whose
`governance` check passes. Direct pushes to `main` (including the agent's)
are rejected, which is the intended end state.

## Add when Phase 1 CI exists

Add each new CI job to the required status checks **only after** it has run
successfully at least once on `main` (a required check that never reports
blocks every merge). Expected Phase 1 checks: backend lint/format/typecheck,
backend tests, frontend lint/typecheck/tests, Docker build, migrations
(up/down, single head), dependency audit.

## Verification after the owner applies settings

The agent can read, but not write, protection state:
`GET /repos/LarkinColtrane/agent-observatory/branches/main` returns
`protected` and `protection.required_status_checks` (readable without the
Administration permission; the detailed protection and rules endpoints return
403 to the agent). Merge settings and visibility are read from
`GET /repos/LarkinColtrane/agent-observatory`. TD-004 is repaid only when
`protected: true`, `governance` is listed as a required check, and the merge
settings match this page. A test push to `main` is **not** used for
verification: if protection were missing it would modify `main`.

Last read (2026-10-10, before owner action): `protected: false`, no required
checks.
