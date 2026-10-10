# Repository settings — `LarkinColtrane/agent-observatory`

Status: **applied and behaviourally verified** (TD-004 repaid). Last verified: 2026-10-10 20:10 UTC — evidence in [phases/P0-public-closure.md](phases/P0-public-closure.md).

The agent cannot change repository settings. Re-tried 2026-10-10 through
every legitimate mechanism available to the session; each was refused:

| Mechanism | Result |
|---|---|
| REST `PATCH /repos/{repo}` (merge methods, projects, auto-delete) | 403 — "Repository settings writes are not permitted through this proxy" |
| REST `POST /repos/{repo}/rulesets` | 403 — "Write access to this GitHub API path is not permitted through this proxy" |
| REST `PUT /repos/{repo}/branches/main/protection` | 403 — same |
| REST `PUT /repos/{repo}/vulnerability-alerts` | 403 — "Access to this GitHub API path is not permitted through this proxy" |
| REST `PUT/GET /repos/{repo}/actions/permissions/workflow` | 403 — "Access to this GitHub Actions path is not permitted through this proxy" |
| GraphQL | 403 — "GitHub GraphQL is not available from Claude Code sessions" |
| `gh` CLI | its configured token is invalid in this environment |
| GitHub Actions `GITHUB_TOKEN` | cannot be granted Administration (not an Actions permission) |

Independently of the proxy, GitHub itself answered "Resource not accessible
by integration" when the session tried to *read* branch protection: the
installed Claude GitHub App's token does not carry the repository
Administration permission. App permissions are defined by the app, not by
the installing user, so this is not something the owner can grant. The owner
applies the items marked **Owner** in the GitHub web UI (about 5 minutes);
the agent then verifies them (see "Verification").

## Current state (read via API, 2026-10-10 20:04 UTC)

| Setting | Value | Source |
|---|---|---|
| Visibility | **public** | API |
| Default branch | `main` | API |
| Wiki / Projects | disabled / disabled | API |
| Issues | enabled | API |
| Merge methods | **squash only** | API |
| Auto-delete head branches | **on** | API |
| Ruleset `main-protection` | **active**, empty bypass, `main` + `protection-probe` — verified behaviourally | rulesets API + probes |
| Dependency graph | **on** (`GET dependency-graph/sbom` → 200; Dependabot graph runs observed) | API |
| Secret scanning / push protection | **enabled** / **enabled** (`security_and_analysis`, verified 2026-10-10 21:22 UTC; TD-011 repaid) | API |
| Dependabot security updates | disabled (`security_and_analysis`) | API |
| Dependabot alerts, Actions default workflow permissions | NOT_VERIFIABLE_FROM_SESSION (proxy 403) | — |

Ruleset follow-ups applied by the owner and verified 2026-10-10 21:22 UTC:
allowed merge methods = squash only; dismiss stale approvals = on.

## Policy decisions

- **Squash merge only.** One reviewed commit per task on `main`, matching the
  task/handoff model; task branches are deleted after merge.
- **Wiki and Projects off.** Governance lives in `docs/` under review; no
  unreviewed side channels.
- **Issues on.** Used for the task board.

## Ruleset for `main` (Owner)

Use a **ruleset** (Settings → Rules → Rulesets → New branch ruleset) rather
than classic branch protection, so the same rules can also target the probe
branch used for verification.

- **Name:** `main-protection` · **Enforcement:** Active
- **Bypass list:** **empty** (no one bypasses — the agent pushes as the
  owner, so any owner bypass is an agent bypass)
- **Target branches:** `main` **and** `protection-probe`

| Rule | Value | Why |
|---|---|---|
| Restrict deletions | **on** | |
| Block force pushes | **on** | Rollback policy: never rewrite published history |
| Require a pull request before merging | **on** | All work arrives as PRs |
| — Required approvals | **0 for now** (see below) | Prevents lock-out on a single-human account |
| — Dismiss stale approvals on new commits | **on** | |
| — Require conversation resolution | **on** | |
| — Allowed merge methods | **squash** | |
| Require status checks to pass | **on**, check **`governance`** | This check exists and passes on `main` |
| — Require branches to be up to date | **on** | Checks run against current `main` |

If GitHub says rulesets/branch protection need a paid plan for private
repositories, report that back: TD-004 then becomes an owner decision
(upgrade, or accept the risk) and Phase 1 stays blocked until it is made.

**Why 0 required approvals today:** the agent pushes and opens PRs as the
owner's GitHub identity, and GitHub does not let an author approve their own
PR. Requiring 1 approval would make every PR unmergeable without a bypass,
and a bypass would also be available to the agent. Independent review stays
mandatory by governance (verdicts under `docs/reviews/`, enforced by the
checker). Known limits (TD-007): verdict lines are not authenticated, and the
required `governance` check runs the PR's *own* copy of the checker and
workflow, so a PR that weakens the checker could pass itself. Raise required
approvals to 1 and require Code Owner review as soon as a second human or a
separate reviewer identity exists.

## Other settings (Owner)

| Setting | Value | Where |
|---|---|---|
| Workflow permissions | **Read repository contents** (default `GITHUB_TOKEN` read-only) | Settings → Actions → General |
| Allowed actions | **Allow GitHub-created actions only**, or "selected": `actions/checkout`, `actions/setup-python` (the only ones used) | Settings → Actions → General |
| Dependabot alerts | **on** | Settings → Code security |
| Secret scanning / push protection | on **if offered** for this private repo on your plan (otherwise gitleaks in pre-commit and CI covers it) | Settings → Code security |

## Phase 0 tag (done)

`phase-P0-v1.1.0` (annotated, → `8ce0ed3`) was published on 2026-10-10 by a
temporary, owner-authorized `workflow_dispatch` workflow (`contents: write`,
no inputs, fixed tag/target/message, refused to replace an existing tag, no
force push), because the session's git proxy refuses tag pushes. The workflow
was removed immediately afterwards. It must not be re-added; future tags go
through the owner or a reviewed release process.

## Break-glass (review B-26)

The required `governance` check downloads pinned tooling (PyPI packages, the
gitleaks release, pinned actions). If an upstream outage makes it fail for
reasons unrelated to the change, every PR is blocked, including the fix. Then
the owner, and only the owner:

1. records the outage (date, failing step, upstream cause) in the PR;
2. temporarily sets the ruleset's enforcement to **Disabled**, merges the one
   PR, and immediately sets it back to **Active**;
3. the agent re-verifies the ruleset (below) and notes the event in the next
   gate report.

## Add when Phase 1 CI exists

Add each new CI job to the required status checks **only after** it has run
successfully at least once on `main` (a required check that never reports
blocks every merge). Expected Phase 1 checks: backend lint/format/typecheck,
backend tests, frontend lint/typecheck/tests, Docker build, migrations
(up/down, single head), dependency audit.

## Verification (agent)

The readable API (`GET /repos/LarkinColtrane/agent-observatory/branches/main`)
shows only `protected` and the required status checks — not bypass actors,
force-push, or deletion rules (review PM-02). So the agent verifies on the
**probe branch**, which the same ruleset targets:

1. The CI step "Repository protection matches TD-004" (`scripts/check-repo-protection.py`, run with the workflow token) reports `main` protected with `governance` required. It reads both `branches/main` and `rules/branches/main`, since ruleset-required checks may appear only in the latter (review N-B); this session's own token gets 403 on the rules endpoint.
2. `branches/protection-probe` reports `protected: true`.
3. A direct push of a new commit to `protection-probe` is **rejected**.
4. A force-push to `protection-probe` is **rejected**.
5. Deleting `protection-probe` is **rejected**.
6. Merge settings and visibility match this page (`GET /repos/...`).

Rejections in 3–5 prove that the rules apply to the identity the agent pushes
as (no bypass). `main` itself is never used for a test push. TD-004 is repaid
only when all six hold. CI also re-checks 1 on every run once TD-004 is
repaid (`scripts/check-repo-protection.py`), so a later removal of protection
fails the build.

Last read (2026-10-10, before owner action): `protected: false`, no required
checks.
