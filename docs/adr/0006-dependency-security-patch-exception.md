# ADR-0006: Security-patch exception to the dependency age cutoff

- Status: proposed
- Date: 2026-10-11
- Deciders: Coordinator (proposed); Reviewer A and Reviewer B (sign-off)
- Components: C11
- Related: ADR-0005, ADR-0002

## Context

ADR-0005 §6 resolves every dependency with a cutoff at least two weeks old,
so that a compromised or broken release has time to be noticed and yanked
before we install it. ADR-0005 §5 also makes `npm audit --audit-level=high`
(and `pip-audit`) part of the required gate. The two rules can conflict: on
2026-10-11, the Phase 1 frontend lock (cutoff 2026-09-25) carried high
advisories whose only fixes were published after the cutoff. Keeping the
cutoff would mean shipping known-vulnerable runtime dependencies or keeping
the gate red. Narrowing the audit (`--omit=dev`, blanket allowlists) was
rejected: it weakens a gate.

## Decision

A dependency version newer than the cutoff is allowed only when **all** hold:

1. It is the **minimal** version (normally a patch release) that fixes a
   high or critical advisory reported by the gate's audit tool for the
   currently locked version.
2. It was published at least **7 days** before it is locked (install with
   `--before` / `--exclude-newer` set to that date, not "now").
3. Nothing else in the lock moves past the regular cutoff; the PR shows that
   every other entry is unchanged.
4. The exception is recorded in the table below (package, from → to,
   advisory IDs, publish date), and reviewed like any other change.

When the regular cutoff later passes the recorded versions, the exception
lapses and the row is kept for history. A vulnerability with **no fixed
version** is not covered: the dependency must be removed or replaced; if
that is impossible, it is a blocker for the owner, not an allowlist entry.

### Recorded exceptions

| Package | From → to | Advisories | Published | Lock |
|---|---|---|---|---|
| (filled from the AO-P1-003 handoff) | | | | `frontend/package-lock.json` |

## Consequences

- Positive: the audit gate stays complete and strict, and known high
  advisories are patched as soon as a fix has aged a week.
- Negative: a 7-day-old fix has had less public scrutiny than a 14-day-old
  one; accepted because the alternative is a known vulnerability.
- Rollback: revert the version bump; the gate then shows the advisory again.

## Review

- Pending: Reviewer A and Reviewer B, with the AO-P1-006 integration PR.
