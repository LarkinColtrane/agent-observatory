# Migration to the dedicated private repository

Status: **BLOCKED — awaiting project owner** (TD-002, TD-004, ADR-0004).

The agent cannot create repositories. Everything below is non-destructive for
the practice repository: nothing there is deleted or rewritten.

## Source

| | |
|---|---|
| Source repository | `LarkinColtrane/Og-Repo` (public practice repo) |
| Source branch | `claude/agent-observatory-governance` |
| Base commit (last practice-repo commit, **excluded**) | `df5f2a0` |
| Commits to migrate | every commit in `df5f2a0..origin/claude/agent-observatory-governance` |

Every commit in that range touches only project paths (`docs/`, `scripts/`,
`tests/governance/`, `.github/`, `.gitignore`, `.pre-commit-config.yaml`,
`requirements-governance.txt`, `requirements-governance.in`); step 3 verifies this before anything is
pushed.

> Note: the pre-Phase-1 cleanup commit may exist only in the agent's session
> (not pushed to the practice repo — see "Branch state" in the final report).
> If so, the owner first authorises pushing it, or the agent pushes directly
> to the new repository once it exists.

## Step 1 — owner: create the repository

On GitHub: **New repository** → owner `LarkinColtrane`, name
`agent-observatory`, **Private**, **no** README/.gitignore/license (must be
empty). Then grant the Claude GitHub App access to it
(https://github.com/apps/claude/installations/select_target) so the agent can
push.

## Step 2 — replay project commits onto an empty `main`

`git format-patch`/`git am` replays each commit with its original author,
date, and message, without any practice-repo history.

```sh
git clone --branch claude/agent-observatory-governance https://github.com/LarkinColtrane/Og-Repo.git og-src
mkdir agent-observatory && cd agent-observatory
git init -b main
git -C ../og-src format-patch df5f2a0..HEAD -o ../ao-patches
git am ../ao-patches/*.patch
```

## Step 3 — verify before pushing (all must pass)

```sh
# a) No practice-repo files came across (must print nothing):
git ls-files | grep -Ev '^(docs/|scripts/|tests/|\.github/|\.gitignore$|\.pre-commit-config\.yaml$|requirements-governance\.(txt|in)$)'
# b) No practice-repo commits (must print only project commits):
git log --oneline
# c) Clean tree:
git status --porcelain            # must print nothing
# d) Secrets — full history, all refs (must report no leaks):
scripts/secret-scan.sh
# e) Governance state + adversarial tests:
pip install --require-hashes -r requirements-governance.txt
python3 -I scripts/check-governance.py
python3 -I -m unittest discover -s tests/governance -t . -v
```

The agent ran steps 2–3 (a–c) against a scratch copy during pre-Phase-1
cleanup; see the gate report.

## Step 4 — push and protect

```sh
git remote add origin https://github.com/LarkinColtrane/agent-observatory.git
git remote -v                      # confirm it is agent-observatory, NOT Og-Repo
git push -u origin main
```

Then in the new repository's **Settings → Branches**, protect `main`:
require a pull request with 1 approval and CODEOWNERS review, require the
`governance` status check, block force-pushes and deletions (TD-004).

## Step 5 — checkpoint

After the push, update `docs/governance-state.yaml` (`repository.dedicated:
true`, remove TD-002/TD-004 from `blocked_by` once repaid), re-run the P0 gate
items 5, 8, 11, 12 in the new repository, then:

```sh
git tag -a phase-P0-v1.1.0 -m "agent-observatory Phase 0 governance baseline (reviewed)"
git push origin phase-P0-v1.1.0
```

## Practice repository

Leave `LarkinColtrane/Og-Repo` as is. The branch
`claude/agent-observatory-governance` there is public; it contains no secrets
(full-history gitleaks scan clean). Deleting it is the owner's decision. The
local-only tag `gov-baseline-v1.0.0` was never pushed and is superseded.
