# Security Baseline

`agent-observatory` ingests activity from many agent systems. That data can
contain prompts, tool outputs, file contents, and credentials. Treat every
adapter as a potential source of hostile or sensitive input.

## Secrets

- **Never committed.** No secrets in source, tests, fixtures, docs, ADRs,
  handoffs, commit messages, or CI config. Use environment variables or a
  secret manager; commit only `*.example` files with placeholder values.
- **Never logged.** Loggers must redact known secret fields
  (`token`, `secret`, `password`, `api_key`, `authorization`, `cookie`,
  `private_key`, …). Exceptions must not embed credentials.
- `.gitignore` excludes `.env*` (except `.env.example`), key files, and local
  credential stores.
- Pre-commit includes a secret scanner (gitleaks or equivalent) once tooling
  is introduced; the L3 gate runs a full-history scan.
- **If a secret leaks:** revoke/rotate it first, then remove it, then record
  the incident in the gate report. Assume anything pushed is compromised.

## Untrusted input (adapters)

- All adapter payloads are validated against the universal event schema
  before entering the core; invalid events are quarantined, not dropped
  silently and not partially ingested.
- Enforce size limits, depth limits, and rate limits per adapter.
- No dynamic code execution or unsafe deserialization of adapter data.
- Agent-supplied text rendered in dashboards / virtual office is escaped
  (XSS); never interpreted as HTML or markup by default.

## Sensitive data in events

- Classify event fields: `metadata` (safe), `content` (may be sensitive),
  `credential` (never stored).
- Redaction runs at ingestion, before persistence, with a configurable policy.
- Store the minimum needed for observability; retention is configurable.

## Access

- Least privilege for every credential an adapter uses (read-only where
  possible).
- Every API/UI endpoint is authenticated; authorization checked per
  workspace/tenant.
- Audit log for configuration and access-control changes.

## Dependencies & supply chain

- Pin versions with a lockfile; review new dependencies (security reviewer).
- Dependency audit at L3; no unaccepted high/critical vulnerabilities.
- CI uses pinned action/tool versions; no untrusted scripts piped to shell.

## Agents working on this repo

- Agents never print environment variables, tokens, or credential files.
- Agents never paste secrets into handoffs, reviews, or issues.
- Agents do not disable TLS verification or security checks to make a task
  pass; that requires an ADR.
