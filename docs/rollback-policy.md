# Rollback Policy

Every change must be reversible, and every agent must know how to reverse it
before making it.

## Checkpoints

| Checkpoint | When | Form |
|---|---|---|
| Task commit | Every task completion (and partial handoff) | Commit on task branch, message `AO-<task_id>: <summary>` |
| Integration commit | After each task's PR passes L1/L2 and review | Squash-merge commit on `main` (the handoff records the PR head SHA; the integrator records the resulting squash SHA) |
| Phase tag | After the L3 gate passes | Annotated tag `phase-P<n>-v<semver>` (P0 included) |
| Contract tag | When a shared contract is frozen | Annotated tag `contract-<id>-v<semver>` |

Tags are created in, and pushed to, the dedicated `agent-observatory`
repository only. A tag that exists only locally is not a checkpoint.

## Rules

- Never rewrite published history (`main`, tags). Revert
  with `git revert`, not reset/force-push — **except** for a secret incident
  (below).
- Force-push is allowed only on an agent's own unshared task branch.
- Tags are immutable. A bad tag is superseded by a new one, not moved.
- Every task contract declares its rollback path; every handoff confirms it.
- Destructive operations (dropping data, deleting branches/tags, irreversible
  migrations) require coordinator approval, both reviewers' sign-off, and an
  ADR.

## Rollback levels

1. **Task rollback** — `git revert <squash commit>` on `main` (via a PR);
   re-run L1/L2 for affected components. If the task added a migration, run its
   downgrade first.
2. **Phase rollback** — **schema first, then code**: run the tested
   downgrades (or restore the pre-phase backup) to the schema of the previous
   phase tag, verify `alembic current` matches, then revert the phase's merges.
   Re-run L3 before re-tagging. Migrations follow expand/contract so code from
   the previous tag tolerates the expanded schema during the transition.
3. **Contract rollback** — revert to the previous frozen contract tag; notify
   every consuming owner; dependent tasks re-verify.
4. **Data/migration rollback** — run the tested downgrade. If a migration is
   irreversible, a backup/restore procedure must exist and have been exercised
   in the gate's failure-injection step.

## Secret incident (exception to "never rewrite history")

If a secret reaches any commit, in this order:

1. **Revoke/rotate** the credential immediately. Assume it is compromised.
2. **Record** the incident in [security-incident-log.md](security-incident-log.md)
   at once: date, credential *type*, location (path/commit), who rotated it.
   **Never** record the value.
3. **Purge** it from history (`git filter-repo` or equivalent) with
   coordinator approval and one reviewer's sign-off; force-push; re-create
   affected tags under new names. If purging is impractical, archive the repo
   and migrate clean history to a new one.
4. **Re-scan** the full history of all refs with `scripts/secret-scan.sh` and
   record the result in the incident entry.
5. Notify everyone with a clone to re-clone.

## Triggers

Roll back immediately (then investigate) when:

- a merged change breaks L1/L2 on `main` and a fix is not
  ready within the same working session;
- a secret is committed (follow the incident procedure above);
- data corruption or silently wrong state is detected;
- a frozen contract was changed without an ADR.

## Recording

Every rollback gets a short entry in the next handoff or gate report: what was
reverted, why, the commit/tag restored, and checks re-run with real results.
