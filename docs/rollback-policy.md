# Rollback Policy

Every change must be reversible, and every agent must know how to reverse it
before making it.

## Checkpoints

| Checkpoint | When | Form |
|---|---|---|
| Task commit | Every task completion (and partial handoff) | Commit on task branch, message `AO-<task_id>: <summary>` |
| Integration commit | After each task merges and L1/L2 pass | Merge/commit on integration branch |
| Phase tag | After L3 gate passes | Annotated tag `phase-P<n>-v<semver>` |
| Governance tag | After a governance contract version change | Annotated tag `gov-baseline-v<semver>` |

## Rules

- Never rewrite published history (`main`, integration branch, tags). Revert
  with `git revert`, not reset/force-push.
- Force-push is allowed only on an agent's own unshared task branch.
- Tags are immutable. A bad tag is superseded by a new one, not moved.
- Every task contract declares its rollback path; every handoff confirms it.
- Destructive operations (dropping data, deleting branches/tags, irreversible
  migrations) require coordinator approval and an ADR.

## Rollback levels

1. **Task rollback** — `git revert <task commit(s)>` on the integration branch;
   re-run L1/L2 for affected components.
2. **Phase rollback** — reset integration work to the previous phase tag by
   reverting the phase's merges; re-run L3 on the result before re-tagging.
3. **Contract rollback** — revert to the previous frozen contract version;
   notify every consuming owner; dependent tasks re-verify.
4. **Data/migration rollback** — run the tested down-migration. If a migration
   is irreversible, a backup/restore procedure must exist and have been
   exercised in the gate's failure-injection step.

## Triggers

Roll back immediately (then investigate) when:

- a merged change breaks L1/L2 on the integration branch and a fix is not
  ready within the same working session;
- a secret is committed (also follow `security-baseline.md` — rotate first,
  revoking a leaked credential matters more than removing it from history);
- data corruption or silent wrong state is detected;
- a frozen contract was changed without an ADR.

## Recording

Every rollback gets a short entry in the next handoff or gate report: what was
reverted, why, the commit/tag restored, and checks re-run with real results.
