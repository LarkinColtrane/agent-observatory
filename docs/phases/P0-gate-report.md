# P0 Gate Report — Development governance baseline

- Phase: P0 · Date: 2026-10-10 · Tag: `gov-baseline-v1.0.0`
- Scope: governance documents, registers, ADRs, governance check script. No application code.

| # | Check | Command | Ran | Result | Notes |
|---|---|---|---|---|---|
| 1 | Full test suite | — | no | n/a | No application code exists (TD-001) |
| 2 | Lint / doc integrity | `python3 scripts/check-governance.py` | yes | pass | Required files, register schema, relative links |
| 3 | Format | — | no | n/a | No formatter configured until stack ADR (TD-001) |
| 4 | Strict typecheck | — | no | n/a | No typed code |
| 5 | Pre-commit | — | no | n/a | Not yet configured (TD-001) |
| 6 | Docker | — | no | n/a | No images |
| 7 | Migrations | — | no | n/a | No storage |
| 8 | Security checks | `python3 scripts/check-governance.py` (secret-pattern scan over tracked + untracked files) | yes | pass | Full gitleaks history scan deferred (TD-001) |
| 9 | Failure injection | Checker run against a copy with a deleted required doc, a broken link, an invalid register status, and a planted fake AWS key | yes | pass | All four detected; exit code 1 |
| 10 | Independent review | — | no | not_run | Single-agent bootstrap; first specialist review of governance docs is the first task of P1 |
| 11 | Registers | Manual review of `assumptions.yaml`, `technical-debt.yaml` | yes | pass | 6 assumptions, 2 debt items |
| 12 | Git checkpoint | `git tag -a gov-baseline-v1.0.0` | yes | pass | |

**Gate decision:** P0 closed with one recorded exception — item 10 (independent
review) did not run because the baseline was authored by the coordinator alone.
It is carried as the first task of Phase 1 (see TD-003).
