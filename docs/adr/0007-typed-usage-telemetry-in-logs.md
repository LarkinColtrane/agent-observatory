# ADR-0007: Typed usage telemetry survives log redaction

- Status: accepted
- Date: 2026-10-12
- Deciders: Coordinator (proposed); Reviewer A and Reviewer B (sign-off)
- Components: C11, C1
- Related: ADR-0005 §3 (amended, not weakened), TD-022, review R-A-002-205

## Context

ADR-0005 §3 treats a log key as secret if its normalised name *contains*
`token`. That is correct for `access_token`, `refresh_token` or `x-auth-token`,
but it also redacts `input_tokens`, `prompt_tokens` or `max_tokens` everywhere
(mapping keys, `(key, value)` pairs, `key=value` text, and the JSON backstop).
An agent observatory must be able to log usage. TD-022 blocks P2 until this is
resolved, because the event protocol carries usage.

## Options considered

1. **Key-pattern exemption** (keys ending in `_tokens` with integer values) —
   rejected: any field named `*_tokens` would pass (`session_tokens`,
   `refresh_tokens` holding a list of credentials), the decision depends on the
   caller's choice of name, and the text scrubber would need the same hole.
2. **Typed allowlist** — chosen: only a value of one specific, validated type
   is exempt, never a name.

## Decision

1. `observatory.core.telemetry.UsageMetrics` is the **only** usage data that
   redaction preserves. It is a frozen, strict Pydantic model with
   `extra="forbid"` and exactly these optional fields:
   - `input_tokens`, `output_tokens`, `cached_input_tokens`,
     `reasoning_tokens`, `total_tokens`: `int`, `0 ≤ n ≤ 10^12`; `bool`,
     floats (even `1.0`), strings (even `"5"`) and anything else are rejected;
   - `reported_cost` (reported by the provider) and `estimated_cost`
     (computed by Observatory): `Money{amount, currency}`, where `amount` is a
     canonical non-negative decimal *string* (`0`, `12.5`, at most 9 integer
     and 12 fraction digits, no sign, exponent, leading zero or trailing
     fraction zero; binary floats are never money) and `currency` matches
     `^[A-Z]{3}$`.
   At least one field must be present. Unknown values stay absent: nothing is
   defaulted to 0, no total or cost is derived, and the two cost kinds are
   never merged.
2. The log pipeline exempts a value only when **`type(value) is UsageMetrics`**
   (subclasses do not qualify) and it is passed as a structured field
   (`extra={...}`, at any depth in JSON output, top level in console output).
   The cost fields accept only an exact `Money` (subclasses are rejected at
   construction, and an exact instance is re-validated as a mapping).
   `redact` resolves the object once, on every path (extras at any depth,
   message, arguments): it re-validates the fixed field names (this catches
   `model_construct`, post-construction mutation and nested model swaps) and
   keeps only those names with validated numbers or decimal strings; any
   failure makes the whole value `[REDACTED]`. Rendered usage contains no
   caller-supplied text, so structured output may skip the text backstop;
   usage rendered into message text is still scrubbed.
3. Nothing else changes: `SECRET_KEY_PARTS`, exact keys and `scrub_text` are
   untouched. A secret-named key wins over a typed value (`{"api_token":
   UsageMetrics(...)}` is redacted). Plain mappings such as
   `{"input_tokens": 5}`, `extra={"input_tokens": 5}`, and usage written into
   the message text (`"%s" % usage`) are still redacted.
4. Never preserved, typed or not: API/bearer tokens, `Authorization` headers,
   cookies, credentials, passwords, session secrets, private keys, raw prompts
   and raw model responses (until a future privacy ADR says otherwise).
5. The event protocol (P2) reuses `UsageMetrics` for usage events, so logs and
   events share one validated definition.

## Consequences

- Positive: usage is observable in logs; the exemption cannot be reached by
  naming a field, and general redaction is exactly as strong as before.
- Negative: callers must build a `UsageMetrics`; provider usage with other
  fields (e.g. audio tokens) is not logged until the model gains a field
  (additive change, reviewed).
- Contracts affected: ADR-0005 §3 gains this one typed exception (the frozen
  tag is unchanged; ADR-0005's status line points here).
- Rollback: revert the commit; usage is redacted again (fails safe).

## Review

- Reviewer A: pending · Reviewer B: pending — `docs/reviews/phase-2-reviews.md`.
