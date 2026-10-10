# Review Checklist

## When review is required

| Change | Independent review | Specialist review |
|---|---|---|
| Docs typo / formatting only | optional | — |
| Any code, config, schema, CI, or dependency change | **required** | if triggered below |
| Touches auth, secrets, input parsing from adapters, network, file I/O, dependency additions | required | **Security** |
| Touches event storage, migrations, normalization, dedup, ordering, state derivation | required | **Data integrity** |
| Touches async code, queues, workers, locks, shared mutable state, retries | required | **Concurrency** |
| Adds/changes a shared contract, cross-component interface, new abstraction, new runtime dependency | required | **Architecture** |

Reviewer A covers **security + data integrity**; Reviewer B covers
**concurrency + architecture**. A reviewer never reviews their own work. If
the only qualified reviewer authored the change, the coordinator assigns
another agent and records it.

## Review outcomes

- **Approve** — no blocking findings.
- **Approve with nits** — non-blocking findings; author may fix in this task
  or record as debt.
- **Request changes** — at least one blocking finding. Each finding states
  the concrete failing scenario (input/state → wrong result).
- **Escalate** — design question that needs an ADR or the coordinator.

Findings without a concrete scenario are advisory, not blocking.

## General checklist (every review)

- [ ] Handoff is complete and the claimed checks reproduce when re-run.
- [ ] Change stays inside the task's `owned_paths`; no frozen contract altered
      without an ADR.
- [ ] Acceptance criteria are each demonstrably met.
- [ ] Code was searched for existing abstractions; no duplicate helper/type.
- [ ] Naming, structure, and idiom match surrounding code.
- [ ] Errors are handled; failure degrades safely (explicit unknown/degraded
      state, no silent wrong data).
- [ ] Tests cover the happy path **and** at least one adversarial case.
- [ ] No dead code, commented-out code, or TODO without a debt entry.
- [ ] New assumptions/debt are recorded in the YAML registers.
- [ ] No secrets, tokens, or sensitive payloads in code, tests, fixtures, or
      logs.

## Security specialist

- [ ] All adapter input treated as untrusted: validated against schema, size
      limits enforced, no `eval`/deserialization of arbitrary types.
- [ ] Secrets loaded from environment/secret store only; never logged,
      never in exceptions, never in event payloads stored at rest.
- [ ] AuthN/AuthZ on every new endpoint; least privilege for credentials.
- [ ] New dependencies: pinned, maintained, license-compatible, no known
      critical CVEs.
- [ ] Injection (SQL, shell, path traversal, HTML/XSS in dashboards) ruled out.
- [ ] Rendering of agent-supplied text in UI is escaped.

## Data integrity specialist

- [ ] Event model invariants preserved (IDs unique, timestamps normalized,
      source + adapter version recorded).
- [ ] Idempotency: replaying the same event does not double-count.
- [ ] Out-of-order and late events handled deterministically.
- [ ] Migrations are reversible (or the irreversibility is ADR-approved) and
      tested up/down.
- [ ] No lossy transformation without recording the original or the loss.
- [ ] Derived state can be recomputed from the event log.

## Concurrency specialist

- [ ] Shared mutable state identified; access is synchronized or eliminated.
- [ ] No unbounded queues, retries, or fan-out; backpressure exists.
- [ ] Timeouts and cancellation on every external call.
- [ ] Retries are idempotent and use bounded backoff.
- [ ] Ordering guarantees stated and tested; race-prone paths have a test or a
      written argument.
- [ ] Shutdown is graceful; no lost in-flight events.

## Architecture specialist

- [ ] Change respects component boundaries in `component-ownership.md`.
- [ ] Dependency direction is correct (adapters → core model, never reverse;
      UI never reads storage directly).
- [ ] New abstraction justified: it has ≥ 2 real call sites or an ADR.
- [ ] Shared contracts versioned; breaking changes have an ADR and migration.
- [ ] Observability of the observability platform itself: logs, metrics, and
      health for the new component.
