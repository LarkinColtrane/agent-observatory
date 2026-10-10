# ADR-0004: Dedicated private repository

- Status: accepted — implementation blocked on project owner (TD-002)
- Date: 2026-10-10
- Deciders: Project owner (direction); Coordinator; Reviewer A and Reviewer B (sign-off)
- Components: C11, C12
- Related: A-006, TD-002, TD-004

## Context

Phase 0 was developed on branch `claude/agent-observatory-governance` of
`LarkinColtrane/Og-Repo`, a **public** practice repository containing
unrelated files. Mixing projects risks shipping unrelated content, makes
history and tags ambiguous, and exposes governance and future code publicly.

## Decision

1. `agent-observatory` lives in its own **private** GitHub repository named
   `agent-observatory`, default branch `main`.
2. Only the project's own commits are migrated, by replaying them with
   `git format-patch`/`git am` onto an empty repository so no practice-repo
   files or history come across. History is secret-scanned before and after
   migration.
3. Nothing further is pushed to the practice repository for this project. The
   existing branch there is left as-is (not deleted or rewritten) unless the
   owner decides otherwise.
4. Branch protection on `main` (review required, CI required, no force-push)
   and CODEOWNERS are configured in the new repository (TD-004).
5. The Phase 0 checkpoint tag is created in the new repository only.

Procedure: [`docs/migration/dedicated-repo-migration.md`](../migration/dedicated-repo-migration.md).

## Consequences

- Phase 1 is blocked until the repository exists and the migration is
  verified (TD-002, TD-004).
- The practice repo retains a public copy of the Phase 0 governance branch
  pushed before this decision (no secrets — full-history gitleaks scan clean).
  Deleting that branch is the owner's call.
- Rollback path: none needed; the source branch is untouched.

## Review

- Reviewer A / Reviewer B: see `docs/reviews/pre-phase-1-review-resolution.md`.
