# ADR-0006: Security-patch exception to the dependency age cutoff

- Status: proposed
- Date: 2026-10-11
- Deciders: Coordinator (proposed); Reviewer A and Reviewer B (sign-off)
- Components: C11
- Related: ADR-0005, ADR-0002, A-010, TD-013

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
| `next` (+ `@next/env`, `@next/swc-*` binaries) | 16.3.6 → 16.3.8 | GHSA-3w37-wq28-93x7, GHSA-4jqv-mc3x-m676, GHSA-39w2-rjm5-chcv, GHSA-f87g-xv8r-7p7x, GHSA-mcj8-r9mp-w47p, GHSA-cjq9-62q9-8jv4 | 2026-09-30 | `frontend/package-lock.json` |
| `sharp` (+ `@img/sharp-*` 0.35.5, `@img/sharp-libvips-*` 1.3.4), via `overrides` | 0.35.4 → 0.35.5 | GHSA-wq5f-xc86-pv6w | 2026-09-27 | `frontend/package-lock.json` |
| `source-map-js`, via `overrides` | 1.2.1 → 1.2.2 | GHSA-68fv-2mgg-jv7q | 2026-09-30 | `frontend/package-lock.json` |

Lock produced with `npm install --before=2026-10-04`; every other entry is
unchanged from the 2026-09-25 lock (checked by name, version and integrity in
AO-P1-003). A fourth advisory, GHSA-vfj7-8cjw-p6xm in `braces` (no fixed
version), reached the tree only through `eslint-config-next` →
`@next/eslint-plugin-next` → `fast-glob`; per the rule above it was removed,
not allowlisted: ESLint now uses `@eslint/js`, `typescript-eslint`, and the
React, React Hooks and jsx-a11y plugins (TD-013 tracks the lost Next-specific
rules).

## Consequences

- Positive: the audit gate stays complete and strict, and known high
  advisories are patched as soon as a fix has aged a week.
- Negative: a 7-day-old fix has had less public scrutiny than a 14-day-old
  one; accepted because the alternative is a known vulnerability.
- Rollback: revert the version bump; the gate then shows the advisory again.

## Review

- Pending: Reviewer A and Reviewer B, with the AO-P1-006 integration PR.
