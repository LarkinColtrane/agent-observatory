# Security Baseline

`agent-observatory` ingests activity from many agent systems. That data can
contain prompts, tool outputs, file contents, and credentials. Treat every
adapter as a potential source of hostile or sensitive input.

## Repository

- **In force:** the project lives in the dedicated **private** repository
  `LarkinColtrane/agent-observatory`
  ([ADR-0004](adr/0004-dedicated-private-repository.md)).
- **Target state (not yet in force — TD-004):** branch protection on `main`
  requires review and passing CI; CODEOWNERS covers governance paths. See
  [repository-settings.md](repository-settings.md).
- Only history that has passed a full secret scan is migrated in.

## Secrets

- **Never committed.** No secrets in source, tests, fixtures, docs, ADRs,
  handoffs, commit messages, or CI config. Use environment variables or a
  secret manager; commit only `*.example` files with placeholder values.
- **Never logged.** Loggers must redact known secret fields
  (`token`, `secret`, `password`, `api_key`, `authorization`, `cookie`,
  `private_key`, …). Exceptions must not embed credentials. The only
  exception is typed usage telemetry (`UsageMetrics`, ADR-0007): an exact,
  re-validated type, never a key name, so `input_tokens: 5` in a plain
  mapping is still redacted.
- `.gitignore` excludes env files, credential stores, key files, cloud/tool
  configs, database dumps, local data directories, and recordings.
- Tooling (all run without printing matched values):
  - pre-commit: `gitleaks` + `detect-private-key` on every commit;
  - `scripts/check-governance.py`: fast pattern scan of working tree, index,
    and all reachable history blobs (a backstop, **not** a full scanner);
  - `scripts/secret-scan.sh`: pinned, checksum-verified gitleaks over the full
    history of all refs — this is the authoritative scan for L3 item 8 and
    before any repository migration. Gitleaks does not scan merge-commit
    diffs; the checker backstop covers every blob reachable from any ref,
    including merges.
- **If a secret leaks:** follow the secret-incident procedure in
  [rollback-policy.md](rollback-policy.md): rotate → record (no value) in
  [security-incident-log.md](security-incident-log.md) → purge → re-scan.

## Test fixtures and recordings

- Fixtures are **synthetic** by default. Recorded agent sessions may be used
  only after scrubbing and Reviewer A sign-off; raw recordings are never
  committed.
- Recordings live under ignored paths (`recordings/`, `*.recording.*`) until
  scrubbed. Fixture directories are included in all secret scans.

## Untrusted input (adapters)

- Adapters **authenticate** on ingest with per-adapter credentials; ingest is
  default-deny. Each event records its provenance (adapter identity and
  version) so spoofed or fabricated events are attributable and rejectable.
- All adapter payloads are validated against the event protocol schema before
  entering the core.
- Invalid events go to **quarantine, which fails closed**: content-bearing
  fields are dropped or replaced with a hash before anything is persisted;
  quarantine has short retention and restricted access. A payload that fails
  validation is never stored raw.
- Enforce size limits, depth limits, and rate limits per adapter.
- No dynamic code execution or unsafe deserialization of adapter data.
- Agent-supplied text rendered in dashboards / virtual office is escaped
  (XSS); never interpreted as HTML or markup by default.

## Sensitive data in events

*Provisional — the field classification is defined by the Phase 2 event
protocol contract.* The requirement it must satisfy now: sensitive content is
distinguishable from metadata, credentials are never stored, and redaction runs
at ingestion **before** persistence (including quarantine), under a
configurable policy. Store the minimum needed; retention is configurable.

## Access

- Least privilege for every credential an adapter uses (read-only where
  possible).
- Every API/UI endpoint, including WebSocket/SSE streams, is authenticated;
  authorization checked per workspace/tenant. **Exception (ADR-0005):** the
  operational endpoints `/healthz`, `/readyz`, `/version` are
  unauthenticated and may expose only status booleans, check names, the
  version and the git SHA — never secrets, hostnames, or error details.
- Audit log for configuration and access-control changes.

## Dependencies & supply chain

- Pin versions with a lockfile; review new dependencies (Reviewer A).
- CI actions and pre-commit hooks pinned to commit SHAs (tags are mutable);
  Python tooling installed with `--require-hashes`; downloaded binaries are
  checksum-verified.
- Dependency audit and SAST at L3 once dependencies exist; no unaccepted
  high/critical vulnerabilities.
- No untrusted scripts piped to a shell.

## Agents working on this repo

- Agents never print environment variables, tokens, or credential files.
- Agents never paste secrets into handoffs, reviews, issues, or incident logs.
- Agents do not disable TLS verification or security checks to make a task
  pass; that requires an ADR.
