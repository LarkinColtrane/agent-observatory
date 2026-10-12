# ADR-0008: Universal agent event protocol v1

- Status: accepted (contract `event-protocol` v1.0.0, approved; frozen at the end of P2 per ADR-0003 §3)
- Date: 2026-10-12
- Deciders: Coordinator (proposed); Reviewer A and Reviewer B (sign-off)
- Components: C1 (owner), C2, C3, C4, C5, C6 (consumers)
- Related: ADR-0003, ADR-0005, ADR-0007, TD-022 (repaid), TD-026, A-001, A-002, A-003, A-013, roadmap "Universal event protocol" requirements 1–6, `docs/security-baseline.md`

## 1. Scope and rules

This contract defines the **emitted event**: what an adapter or SDK (P3) sends
to Observatory. It covers the envelope, taxonomy, payloads, identity, time,
ordering, causality, usage, extensions, payload safety, versioning,
validation, canonical serialisation, fingerprints and duplicate semantics. It
also fixes the shape of the records that ingestion (P4) keeps around an
accepted or rejected event.

Not in scope: adapters (P3), transport, authentication, storage, ingestion,
state reconstruction (P4), realtime (P5) and any UI. §15 lists what Phase 2
validates and what later phases must do.

1. **Immutable.** An accepted event is never changed. Corrections are new
   events. The single exception is security erasure (§14).
2. **Context-free validation.** Validating one event needs no store, no clock
   and no other event, so the result is deterministic.
3. **Never repair.** Materially malformed identity, time, security or
   financial data is rejected, never coerced. The only normalisations are:
   - lossless JSON syntax (whitespace, string escapes, key order);
   - timestamp fraction digits (§6).

   There are no defaults and no omitted values: the canonical form contains
   exactly the fields the event has (§13).
4. **Unknown stays unknown.** An absent field means "not reported". Nothing
   is defaulted to zero or derived. `null` is never accepted.
5. **Fail closed.** Anything unrecognised is rejected with a stable code
   (§12). **No rejected event is ever stored raw** (§12, `security-baseline.md`).

## 2. Envelope

All values are JSON strings, integers, booleans (extensions only), objects or
arrays. There are no floats and no nulls.

| Field | Type | Req. | Concern | Meaning |
|---|---|---|---|---|
| `spec_version` | `"MAJOR.MINOR"` | yes | identity | protocol version whose schema the event satisfies; v1 emits `"1.0"` |
| `event_id` | UUID | yes | identity | unique event identity within the workspace (§4) |
| `event_type` | string | yes | identity | taxonomy type (§8) or extension type (§11) |
| `scope.workspace_id` | WorkspaceId | yes | isolation | the one workspace the event belongs to |
| `scope.session_id` | Id | no | context | session (run, conversation) the actor was in |
| `scope.agent_id` | Id | no | context | the **actor**: the agent that performed or reported the action; absent = a human, the system or unknown |
| `scope.task_id` | Id | no | context | the task the actor was working on |
| `time.occurred_at` | Timestamp | no | time | when it happened, by the source clock; absent = unknown |
| `time.observed_at` | Timestamp | yes | time | when the emitter observed it, by the emitter clock |
| `source.provider` | Slug | yes | provenance | agent system family (`claude-code`, `my-orchestrator`) |
| `source.adapter.name` / `.version` | Slug / Version | yes | provenance | emitting adapter or SDK and its version |
| `source.stream_id` | Id | with `seq` | ordering | an ordered stream from one emitter instance (§7) |
| `source.seq` | int `0..2^53-1` | with `stream_id` | ordering | position in that stream: 0, 1, 2, … (§7) |
| `source.provider_event_id` | ProviderRef | no | provenance | the provider's own event id, unique within (workspace, provider) (§4) |
| `causality.correlation_id` | Id | no | causality | groups the events of one logical operation across agents |
| `causality.causation_id` | UUID | no | causality | `event_id` of the event that directly caused this one |
| `payload` | object | yes | payload | closed schema selected by `event_type` (§8) |
| `extensions` | object | no | extension | controlled provider extras (§11) |

An absent optional object (`causality`, `extensions`) is omitted. An empty
object `{}` is a `schema_violation`.

Fields left out on purpose:
- `parent_agent_id` is not on the envelope. Parentage is stated once, in
  `agent.spawned`, so the hierarchy has one source of truth.
- `usage` is not on the envelope. It is its own event (`usage.recorded`), so
  usage is never attached twice and double-counted.
- `metadata` (a free-form bag) is replaced by bounded, namespaced `extensions`.
- `ingested_at` belongs to Observatory, not the emitter (§14).
- `sequence` and `source_sequence` are `source.seq`. Arrival order is
  ingestion's `ingest_seq` (§14). A provider's own counter, if any, is not
  ordering data and may go in an extension.

`scope` holds **who acted and where**. `payload` holds **what happened, to
which subject**. For example, in `agent.spawned` the scope agent is the spawner
and the payload names the new agent.

## 3. Scalar types

| Type | Rule |
|---|---|
| WorkspaceId | `^[a-z0-9][a-z0-9-]{0,62}$` |
| Id | ASCII `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` |
| UUID | lowercase `8-4-4-4-12` hex; RFC 9562 variant (`8`–`b`); version 4, 7 or 8 (§4); nil and max UUIDs rejected |
| Slug | `^[a-z][a-z0-9-]{1,31}$` |
| Version | `^(0\|[1-9][0-9]{0,3})\.(0\|[1-9][0-9]{0,3})\.(0\|[1-9][0-9]{0,5})$` |
| ProviderRef | 1–256 printable ASCII characters (`0x21`–`0x7e`) |
| Code | `^[a-z][a-z0-9_.-]{0,63}$` (machine-readable reason, error or framework names) |
| ToolName, ModelName | 1–128 printable ASCII characters |
| Timestamp | `YYYY-MM-DDTHH:MM:SS[.f{1,6}]Z`, UTC only, valid calendar date, seconds `00`–`59`, year 2000–2099 |
| Text(n) | 1–n Unicode code points, safe text (§10); single line unless the field says otherwise |
| RelPath | workspace-relative POSIX path (§10) |
| Count | int `0..10^9` |
| DurationMs | int `0..2_592_000_000` (30 days) |

- **Equality is byte equality.** Id equality is case-sensitive. Stores,
  caches and routes must never compare ids case-insensitively or after normalising them.
- **Numbers:**
  - Booleans are never accepted where an integer is expected.
  - Integers given as strings are rejected.
  - Any JSON number with a fraction or exponent is rejected, and so is the
    literal `-0`.
- **Id lists are sets.** They hold unique values in ascending code-point
  order, and any other order is a `schema_violation`. This keeps the
  canonical form a fixed point without repairing anything.

## 4. Identity

- **`event_id`** identifies the event within its workspace.
  - **With a provider id.** If `source.provider_event_id` is present,
    `event_id` **must** be `derive_event_id(workspace_id, provider,
    provider_event_id)`. This is a UUIDv8 made from the first 128 bits of
    `SHA-256(UTF-8("ao-event-id/v1" NUL workspace_id NUL provider NUL
    provider_event_id))`, with the version and variant bits set.
  - **Without a provider id.** `event_id` must be a UUIDv7 or UUIDv4.
  - A v8 UUID is accepted **if and only if** `provider_event_id` is present
    and the derivation matches. The validator recomputes it and rejects
    anything else with `invalid_reference`. So a re-delivered provider event
    always gets the same `event_id`, and a bare v8 UUID cannot be used to
    squat another source's derived ids.
  - `derive_event_id` validates its arguments (WorkspaceId, Slug,
    ProviderRef, none of which can contain NUL) and raises otherwise.
- **Scope of `provider_event_id`.** It must be unique within (workspace,
  provider). An adapter whose native id is unique only in a narrower scope
  (per session or per conversation) qualifies it first, as
  `<session-or-conversation id>/<native>`. Two adapters for the same provider
  that can observe the same native event must agree on one `provider` value
  and one qualification, so they derive the same id.
- **Without a provider id**, deduplication across emitter restarts needs the
  emitter to persist an event before sending it (an outbox) and reuse its
  `event_id` on retry. Otherwise re-emitted events are distinct. This is a
  documented limitation (§15).
- **Collision resistance:** 122 random or hash bits. Derivation includes the
  workspace and provider.
- **Entity ids** (session, agent, task, call, run, review, message, stream,
  correlation, unit) are opaque Ids, unique **within the workspace**.
  Adapters (P3) build them as `<provider>:<native>`, where `native` is used
  verbatim only if all of these hold:
  - it is in the Id alphabet;
  - it is at most `127 − len(provider)` characters;
  - it does not start with `h.`;
  - it passes the credential detectors (§10).

  Otherwise `native` is replaced by `h.` plus the first 32 hex characters of
  `SHA-256(UTF-8(native))`. An id is never truncated. Prefixing provider
  natives with `h.` is what keeps the mapping injective.
- **Provider ids are untrusted.** They are only compared and stored, never
  parsed, interpreted, joined to a path, URL-decoded or rendered as markup.
- **Identity, integrity and authentication are separate.**
  - `event_id` says which event this is.
  - The fingerprint (§14) says whether the bytes are unchanged.
  - Authentication (which credential may emit for a workspace, provider and
    adapter) is ingestion's concern and is not in the event.

## 5. Isolation

- Every event has exactly one `workspace_id`.
- **Identity, deduplication, sequencing and ordering are always scoped to
  `workspace_id`.** Every id an event references is resolved only inside its
  workspace, and there is no way to express a cross-workspace reference.
- The pure functions of §7 and §15 refuse input from more than one workspace
  (`ValueError`).
- Stores enforce uniqueness on (`workspace_id`, `event_id`).
- Ingestion (P4) checks that the authenticated credential is allowed to emit
  for that workspace, provider and adapter. The event's own claim is never enough.

## 6. Time

- **Required and optional times.** `observed_at` is required. `occurred_at`
  is optional; absent means the source gave no time, and it is never filled
  in from `observed_at`.
- **Effective time.** The time used for ordering is `occurred_at` if
  present, else `observed_at`. It is a per-event replay heuristic, never
  inferred from neighbouring events. Adapters omit an implausible
  `occurred_at` (for example an unset clock) rather than emit it.
- **Canonical form and accepted input.**
  - Canonical form always has 6 fraction digits (`…:05.120000Z`). Inputs with
    0–6 digits are accepted; this is lossless.
  - Times compare as UTC instants, which is the same as comparing canonical strings.
  - Rejected: offsets other than `Z`, missing zones, leap seconds, years
    outside 2000–2099, and more than 6 fraction digits.
- **Clock skew and delay are reported, not corrected.** Validation still
  accepts the event and returns these warnings, which are not stored in it:
  - `occurred_after_observed`: `occurred_at` is more than 5 minutes after `observed_at`;
  - `late_observation`: `observed_at` is more than 30 days after `occurred_at`.

  No timestamp is ever rewritten.
- `ingested_at` (§14) is assigned by Observatory. Comparing it with
  `observed_at` measures delivery delay; that comparison is ingestion's.

## 7. Ordering

- **Streams.**
  - The stream key is `(workspace_id, source.provider, source.adapter.name,
    source.stream_id)`. `stream_key(event)` returns this 4-tuple, or `None`
    for an event without a stream.
  - `seq` starts at 0 for a new `stream_id` and increases by exactly 1 per
    event emitted on that stream, so a gap is a missing integer.
  - An emitter that cannot persist its position durably must start a new
    `stream_id` (for example a UUIDv7) when it restarts. A `stream_id` is
    never reused after its emitter instance ends.
  - Inside a stream, `seq` is authoritative. Timestamps may go backwards
    there without changing stream order.
  - An emitter that observes events in order should assign `stream_id` and
    `seq` even when the provider has none, and the P3 SDK must.
  - An emitter assigns `seq` only to an event that has passed
    `validate_event`. A gap therefore means loss in transport or a dropped
    event.
- **Canonical order.** `canonical_order(events)` takes events of one
  workspace with unique `event_id`s; a duplicate `event_id` or more than one
  workspace raises `ValueError`. Classify duplicates first (§15). The order
  is deterministic and independent of input order:
  1. Group events by stream key. An event without a stream is a group of its
     own, with group key `(workspace_id, "", "", event_id)` and `seq` −1.
  2. Sort each group by `(seq, event_id)`.
  3. Merge the groups: repeatedly emit the group head with the smallest
     `(effective_time, group key, seq, event_id)`.

  This keeps every stream's own order, interleaves streams by time, and
  breaks every tie by an id. It is a replay order, not a claim of true causal
  order. Causal checks (a cause recorded before its effect) are ingestion's (P4).
- **Arrival order** is ingestion's `ingest_seq` (§14). Both orders are
  deterministic for a given recorded set.
- Gap detection over `seq` is ingestion's. Phase 2 provides the stream key
  and duplicate classification (§15).

## 8. Taxonomy and payloads

The taxonomy has 16 types in 10 families. Every payload is closed: an unknown
field is a `schema_violation`. Optional arrays hold at least one item when
present.

| `event_type` | Payload (`?` = optional) | Notes |
|---|---|---|
| `session.started` | `session_id`, `initiator?` ∈ {human, agent, schedule, system} | |
| `session.ended` | `session_id`, `outcome` ∈ {completed, failed, cancelled, unknown} | |
| `agent.spawned` | `agent_id`, `parent_agent_id?`, `role?` Text(64), `display_name?` Text(128), `model?` ModelName | parent = hierarchy owner; spawner = `scope.agent_id`, which may differ from the parent; a self-report omits `scope.agent_id` (spawner unknown); no parent = root agent |
| `agent.terminated` | `agent_id`, `reason` ∈ {completed, failed, cancelled, killed, timeout, unknown} | |
| `task.created` | `task_id`, `title?` Text(200), `parent_task_id?`, `depends_on?` 1–64 task ids | subtask = parent; DAG edges = `depends_on` |
| `task.assigned` | `task_id`, `assignee_agent_id`, `previous_assignee_agent_id?` | ownership; a handoff has a previous assignee; the assigner is `scope.agent_id` |
| `task.status_changed` | `task_id`, `status` ∈ {pending, in_progress, blocked, completed, failed, cancelled}, `blocked_by_task_ids?` (only when blocked, 1–64), `reason_code?` Code, `evidence_event_ids?` (only when completed or failed, 1–32 UUIDs) | completion evidence references test, review and file events |
| `task.dependency_added` | `task_id`, `depends_on_task_id` | DAG edge added after creation |
| `tool.call_started` | `call_id`, `tool_name`, `kind` ∈ {command, search, file_read, file_write, web, agent, other}, `attempt?` 2–1000, `retry_of_call_id?` (requires `attempt`), `command?` Text(1024) (kind command), `query?` Text(512) (kind search), `target_path?` RelPath (kinds file_read, file_write) | a retry is a new call with `attempt`; absent `attempt` means not a known retry |
| `tool.call_finished` | `call_id`, `outcome` ∈ {succeeded, failed, cancelled, timed_out}, `duration_ms?`, `exit_code?` int32, `error_code?` Code | |
| `file.changed` | `path` RelPath, `change` ∈ {created, modified, deleted, renamed}, `previous_path?` (required if and only if renamed), `call_id?`, `lines_added?`, `lines_removed?` Count | the effect, whatever tool or person caused it |
| `test.run_completed` | `run_id`, `outcome` ∈ {passed, failed, errored, cancelled}, `call_id?`, `framework?` Code, `passed?`, `failed?`, `skipped?`, `errored?` Count, `duration_ms?` | results only, never test output |
| `review.verdict_recorded` | `review_id`, `verdict` ∈ {approve, approve_with_notes, request_changes, reject, comment}, `subject_task_id?`, `findings?`, `blocking_findings?` Count | reviewer = `scope.agent_id` |
| `message.sent` | `message_id`, `intent` ∈ {request, response, notification, handoff, broadcast}, `to_agent_ids?` 1–64, `channel_id?`, `in_reply_to_message_id?`, `size_bytes?` Count | sender = `scope.agent_id`; absent = human or system; at least one of `to_agent_ids` or `channel_id`; **no content** |
| `error.reported` | `error_code` Code, `severity` ∈ {warning, error, fatal}, `message?` Text(512), `call_id?` | an error not expressed by a `tool.call_finished` outcome; `call_id` links it to the call it occurred in; adapters prefer `error_code` and never copy provider exception text verbatim |
| `usage.recorded` | `usage` UsageMetrics (ADR-0007), `accounting` ∈ {delta, cumulative}, `unit` ∈ {model_call, turn, agent, session}, `unit_id?` Id (required when cumulative), `model?` ModelName, `call_id?`, `pricing_ref?` ProviderRef | §9 |

Required scope:
- `session.*` needs `scope.session_id` equal to the payload `session_id`.
- `tool.*` needs `scope.agent_id`.
- `file.changed` and `usage.recorded` need `scope.agent_id` when `call_id` is present.
- Every other scope field is optional context.

These self references are rejected with `invalid_reference`:
- `parent_agent_id` equal to `agent_id`;
- in `agent.spawned`, `scope.agent_id` equal to `agent_id`;
- `parent_task_id` equal to `task_id`;
- `task_id` listed in its own `depends_on` or `blocked_by_task_ids`, or
  equal to `depends_on_task_id`;
- `previous_assignee_agent_id` equal to `assignee_agent_id`;
- `retry_of_call_id` equal to `call_id`;
- `in_reply_to_message_id` equal to `message_id`;
- `previous_path` equal to `path`;
- `causality.causation_id` equal to `event_id`.

Deliberately not types:
- workspace lifecycle: workspaces are configured in Observatory, not emitted by sources;
- `retry`: expressed by `attempt` and `retry_of_call_id`;
- `handoff`: a `task.assigned` with a previous assignee, optionally with a
  `message.sent` of intent `handoff`;
- `command` and `search`: these are tool calls with a typed `kind`;
- agent "status" (idle or working): derived by the state engine (P4) from activity.

Hierarchy, ownership and task dependencies are stated as facts. Checking them
across events (parents spawned first, no cycles, references that exist) is P4's job.

## 9. Usage and cost

`usage.recorded` carries an ADR-0007 `UsageMetrics`. Token meanings and the
subset rules are ADR-0007's: cached input ⊆ input, reasoning ⊆ output, and
total only as reported. Cache-write tokens count as input.

- **Accounting.**
  - `accounting: delta` is an increment.
  - `accounting: cumulative` is a running total for the unit instance
    (`unit`, `unit_id`). `unit_id` must equal `scope.session_id` when `unit`
    is `session`, and `scope.agent_id` when `unit` is `agent`.
  - Consumers take, per (workspace, unit, unit_id, model, currency), the
    maximum cumulative value, because totals are monotone. They never sum
    cumulative values, and never mix delta and cumulative for the same unit instance.
- **Costs.**
  - `reported_cost` is only what the provider reported.
  - `estimated_cost` is an estimate, never copied from `reported_cost`. When
    it is present, `pricing_ref` is required: the price table's id and
    version. In an *emitted* event the estimate is attributed to
    `source.adapter` and `pricing_ref`. P4 treats it as Observatory-estimated
    only if `pricing_ref` names a known Observatory price table, and
    otherwise recomputes or ignores it.
  - `pricing_ref` without `estimated_cost` is a `schema_violation`.
- **Currency** in a usage event must be in the pinned allowlist of active
  ISO 4217 codes (as of 2026-01-01, excluding `X`-prefixed codes), kept in
  `observatory.events`. Changing the list is a minor version. Provider
  credits and other non-ISO units stay unknown, so the cost is omitted.
- No cost is ever fabricated. An unknown cost is absent.

## 10. Payload safety

### 10.1 Size and shape

- The raw event is at most 64 KiB, and so is the canonical event.
- Nesting is at most 16 levels; the top-level value is level 1, and brackets
  inside strings do not count.
- Per-field length limits are as in §3 and §8, and arrays are bounded per field.
- There is no binary type: free text is bounded Text, so a blob cannot hide in a field.

### 10.2 Forbidden characters

Every key and every string is rejected (`forbidden_character`) if it holds
any code point in this fixed, enumerated list. The list is not derived from
Unicode categories, so it does not change with the Unicode version.

- C0 controls except TAB and LF, plus DEL and C1.
- Invisible and format characters: U+00AD, U+034F, U+061C, U+115F–U+1160,
  U+17B4–U+17B5, U+180B–U+180F, U+200B–U+200F, U+202A–U+202E,
  U+2028–U+2029, U+2060–U+206F, U+3164, U+FE00–U+FE0F, U+FEFF, U+FFA0, U+FFF0–U+FFFB.
- Noncharacters and private use: U+FDD0–U+FDEF, every U+nFFFE–U+nFFFF,
  U+E0000–U+E0FFF, surrogates, U+E000–U+F8FF, and planes 15–16.

TAB and LF are never allowed in keys (`forbidden_character`). In a v1 Text
field they break the single-line rule (`schema_violation`). No v1 Text field
is multi-line.

HTML, script and markup are **data**: they are kept verbatim and never
interpreted. Renderers must escape them (A-013).

### 10.3 Secrets (`secret_detected`)

There are two detector tiers. Both are linear-time and versioned as
`SECRET_RULES_VERSION` (v1 = 1), and they are defined in `observatory.events`
independently of `core.logging`. Each check runs on a string **and** on its
NFKC form; a hit on either counts.

- **Credential detectors** run on every key and every string, Ids and RelPaths
  included. The v1 patterns are exact. They are ASCII and case-sensitive
  unless marked, and `B` is the left boundary `(?<![A-Za-z0-9_-])`:

  | Detector | v1 pattern |
  |---|---|
  | OpenAI-style key | `B sk-[A-Za-z0-9_-]{20,}` |
  | GitHub token | `B gh[pousr]_[A-Za-z0-9]{36,}` |
  | GitHub fine-grained token | `B github_pat_[A-Za-z0-9_]{22,}` |
  | Slack token | `B xox[abposr]-[A-Za-z0-9-]{10,}` |
  | AWS access key id | `(?<![A-Z0-9])(?:AKIA\|ASIA)[A-Z0-9]{16}(?![A-Z0-9])` |
  | Google API key | `B AIza[A-Za-z0-9_-]{35}` |
  | JWT | `B eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*` |
  | PEM/PGP private key | detection: `-----BEGIN [A-Z ]{0,40}PRIVATE KEY( BLOCK)?-----`; extent for replacement: from that header to the next `-----END [A-Z ]{0,40}PRIVATE KEY( BLOCK)?-----`, or to the end of the string if there is none (possessive or tempered, linear) |
  | URL userinfo | in the whitespace-free token after `://`, a `:` before the token's last `@`, with no `/` between `://` and that `:`; evaluated per token (possessive token match, then a last-`@` search), so it stays linear and a password may contain `/` |

  So `task-42`, `desk-ops` and "Basic authentication enabled" are not hits.
  `sanitize_text` replaces the full extent of each match as defined here, so
  no byte of a private-key body survives.
- **Text detectors** run on Text, ProviderRef, ToolName, ModelName and
  extension string values (not on Ids or RelPaths):
  - Bearer/Basic credentials, `(?i:bearer|basic)\s+[A-Za-z0-9._~+/-]{16,}=*`;
    text tier only, so a path such as `docs/Basic usage/getting-started-guide.md`
    is not a hit;
  - ADR-0005's key/value scrub (`password=x`, `token: x`, `'api_key': 'x'`);
  - secret-named options (ADR-0005 key rules) written with whitespace or
    attached with `=`: `--password X`, `--api-key=X`;
  - `-p<value>` attached, when the command's first word is `mysql`,
    `mysqldump`, `mysqladmin`, `mariadb` or `mariadb-dump`. The first word
    is taken after skipping `sudo` and `env` together with their options and
    option arguments, and `NAME=value` words. It is compared by basename;
  - `-u`/`--user` values of the form `user:pass`;
  - `set <secret-named key> <value>`.
- **Known limit (TD-026):** Ids skip the text tier so that structural ids
  such as `sess:auth:42` or `tokenizer:abc` stay valid. An Id shaped like
  `password:x` is therefore accepted. Ids are opaque references that
  adapters build (§4), never free text.
- **Secret-named keys.** Any key whose name is secret-named under ADR-0005
  rules is a hit, at any depth, extensions and unknown fields included. The
  only exemption: the **key-name test** (not the value scan) is skipped for a
  key that is one of the five ADR-0007 token-count names, whose path is
  exactly (`payload`, `usage`, name), whose top-level `event_type` is exactly
  `"usage.recorded"`, and whose value is a JSON integer. Paths are compared
  as tuples of decoded keys, never as pointer strings.

`sanitize_text(text) -> str` replaces every text-tier and credential-tier
match with `[REDACTED]`. It is idempotent, and its output is a fixed point of
the scan. Adapters call it on free text before emitting. Over-masking, such as
`--max-tokens=[REDACTED]`, is accepted as the safe direction. An Id cannot be
sanitised; an adapter hashes a native id that hits a credential detector (§4).

Known limit (TD-026): cross-script homoglyphs, such as a Cyrillic `а` in
`pаssword=`, are not folded by NFKC and can evade the text tier.
`SECRET_RULES_VERSION` pins `unicodedata.unidata_version` (15.0.0 for v1, the version Python 3.12 ships; see C0 below). A
test asserts it, and a change is a rules patch. NFKC can expand a string up
to 18 times, so the 64 KiB timing test includes NFKC-expanding input such as
U+FDFA.

### 10.4 Never in v1 events

- message content, raw prompts and raw model responses;
- tool input or output bodies, heredoc bodies;
- test output;
- environment variables;
- headers, cookies, credentials.

`command` is a single line of at most 1024 characters. Adapters emit the
command up to its first newline or heredoc marker, then apply this order:
sanitise, truncate to fit, append ` [TRUNCATED]` when cut, and sanitise
again. They repeat truncate-and-sanitise until the result is a fixed point of
at most 1024 characters. The loop ends because each round keeps a strictly
shorter prefix. A cut can therefore never leave half a secret or
half a `[REDACTED]`.

### 10.5 RelPath

A RelPath is display and identity data. No consumer joins it to a filesystem
root, URL-decodes it, or maps it through NFKC.

- Length and shape: 1–1024 characters, at most 64 segments, safe Text, `/`
  separators only.
- Rejected:
  - a leading `/`;
  - `\`, `%`, `:` or a drive letter;
  - an empty segment;
  - a segment that is `.`, `..` or `~`, or whose NFKC form is `.`, `..` or
    `~` or contains `/` or `\`.

Absolute paths are rejected because they leak user names and host layout.
Adapters relativise absolute paths in free text where they can. Free text
may still contain them, which is one reason it is classified sensitive (§10.6).

### 10.6 Field classification (`security-baseline.md` "Sensitive data in events")

| Class | Fields |
|---|---|
| identifier | `event_id`, `causation_id`, `evidence_event_ids`, every Id, WorkspaceId, `provider_event_id` |
| metadata | `spec_version`, `event_type`, timestamps, `source.*` except `provider_event_id`, enums, Codes, Counts, durations, `exit_code`, `attempt`, `tool_name`, `model`, `usage`, `pricing_ref` |
| sensitive-text | `command`, `query`, `title`, `role`, `display_name`, `message`, extension string values (non-string extension values are metadata) |
| sensitive-path | `path`, `previous_path`, `target_path` |

Ingestion policy (P4) works within these limits:
- It may only reject events, or remove whole optional `sensitive-*` fields
  **before** acceptance. Extension values are removed only as whole
  `extensions` namespaces, never one value at a time, and the event after
  the policy is re-validated (checks 9–15) before acceptance; if it fails,
  the event is rejected. For an incoming event whose `event_id` already
  exists, ingestion applies the stored event's `policy_id` before
  `classify_duplicate`, so a policy change cannot turn a redelivery into a
  conflict.
- The fingerprint and duplicate rules then apply to the event after the
  policy, and the policy id is recorded in `RecordedEvent`.
- A policy never edits a value in part.

## 11. Extensions and unknown events

- **`extensions`:**
  - at most 4 namespaces `^x-[a-z][a-z0-9-]{1,30}$`, each a non-empty JSON object;
  - at most 4 KiB canonical in total, and depth ≤ 4 inside a namespace;
  - keys match `^[A-Za-z][A-Za-z0-9_]{0,63}$`;
  - values are strings (Text(512)), safe-range integers, booleans, or
    arrays (≤ 32) and objects of these, with no nulls and no floats;
  - they are subject to the secret rules.
- **Content denylist.** A key whose normalised name (ADR-0005
  normalisation) contains any of these is a `schema_violation`: `prompt`,
  `completion`, `content`, `response`, `body`, `stdout`, `stderr`, `output`,
  `input`, `messages`, `env`, `header`. The denylist applies to every key
  inside `extensions`, to every key of an extension event payload, and to
  namespace and vendor names.
- Consumers ignore namespaces they do not know, and core semantics never
  depend on extensions.
- Unknown provider fields are **not** carried automatically: an adapter must
  map a field into an extension on purpose. The P3 adapter interface
  declares each adapter's namespaces and keys statically, and Reviewer A
  reviews them.
- **Extension event types** are named `x-<vendor>.<name>`, with the vendor
  as above and name `^[a-z][a-z0-9_]{0,63}$`. The payload follows the
  extension value rules and is at most 8 KiB canonical. These events are
  accepted, stored and ignored by core state (P4). A vendor can never
  define a core family name.
- An unknown non-extension `event_type` is rejected with `unknown_event_type`.

## 12. Validation

`parse_event(raw: bytes)` returns either `Accepted(event, fingerprint,
content_fingerprint, warnings)` or `Rejected(code, pointer, disposition,
raw_length, raw_sha256?)`. `raw_sha256` is present only on quarantine.

**Parsing:**
- strict UTF-8;
- a string-aware depth pre-scan;
- duplicate keys detected on decoded keys;
- `parse_float` and `parse_constant` hooks that reject fractions, exponents,
  `NaN` and `±Infinity`;
- a `parse_int` hook that rejects literals of more than 16 digits and `-0`
  before converting them.

Strings are never encoded before the forbidden-character check. Any
unexpected exception during validation becomes `internal_error` (drop) and
is never re-raised with values.

Checks run in a fixed order, and the first failure decides. **Invariant:**
every check whose disposition is quarantine runs after the secret scan.

| # | Check | Code | Disposition |
|---|---|---|---|
| 1 | raw size ≤ 64 KiB | `too_large` | drop |
| 2 | strict UTF-8, no BOM | `invalid_encoding` | drop |
| 3 | nesting ≤ 16 | `too_deep` | drop |
| 4 | JSON syntax | `invalid_json` | drop |
| 5 | no duplicate keys | `duplicate_key` | drop |
| 6 | no fraction, exponent, `NaN` or `Infinity` | `float_not_allowed` | drop |
| 7 | integer literals ≤ 16 digits, within ±(2^53−1), not `-0` | `integer_out_of_range` | drop |
| 8 | top level is an object | `not_an_object` | drop |
| 9 | secret scan of every key and string (§10.3) | `secret_detected` | drop |
| 10 | forbidden characters in any key or string (§10.2) | `forbidden_character` | quarantine |
| 11 | `spec_version` present, a string, and supported | `unsupported_version` | quarantine |
| 12 | `event_type` present, a string, and known or a valid extension type | `unknown_event_type` | quarantine |
| 13 | schema: envelope, payload, scalar types, cross-field rules (validated against the declared `spec_version`) | `schema_violation` | quarantine |
| 14 | references (§4, §8) | `invalid_reference` | quarantine |
| 15 | canonical size ≤ 64 KiB | `too_large` | quarantine |
| — | unexpected exception | `internal_error` | drop |

**No raw bytes are ever kept for a rejected event.**
- A **drop record** is `{code, pointer, raw_length}`. It has no digest: the
  secret scan has not passed, and a hash of a templated document with one
  short secret would be an offline guessing oracle.
- A **quarantine record** is a drop record plus `raw_sha256` (the scan has
  passed; the residual risk of an undetected low-entropy secret behind this
  unkeyed digest is part of TD-026) and those of `workspace_id`, `event_id`, `event_type`,
  `spec_version`, `source.provider`, `source.adapter`, `source.stream_id` and
  `source.seq` that individually satisfy their own scalar rule. Nothing else
  is kept. Ingestion reports a quarantined stream slot as quarantined, not lost.
- An `unsupported_version` event is not reprocessed. The emitter re-sends it
  after the upgrade.

**Pointers** (RFC 6901, at most 256 characters):
- A segment is either an array index or a key the schema defines at that position.
- An unknown key is reported as its parent's pointer.
- For `secret_detected`, the pointer stops at the parent of the hit.
- Pointers longer than the limit are cut at a segment boundary and end in `/…`.
- When there are several schema errors, the reported one has the smallest
  pointer, compared segment by segment: array indices numerically, keys by
  code point.
- Rejections never echo values or unknown keys.

**`validate_event(data)`** first checks that `data` is an acyclic tree whose
nodes have exactly the built-in types `dict` (with exact `str` keys), `list`,
`str`, `int` and `bool`. Any other type, subclasses included, and also
`float` and `None`, is `invalid_json` (drop). It also checks depth ≤ 16
(`too_deep`) and canonical size ≤ 64 KiB (`too_large`), then runs checks 7–15.

**Every `Event` instance has passed checks 9–15:** construction runs the
secret scan too. Accepting a new event (`parse_event`, `validate_event`,
ingestion, SDK emission) always uses the current `SECRET_RULES_VERSION` and
cannot name another. An older version may be named only when loading a
stored event, and must equal its `RecordedEvent.secret_rules_version`. Every rules
version is kept, as validators are, so a later rules patch never makes
replay fail (A-002). A newer rules version is applied to stored events only
by the explicit re-scan operation, whose hits become tombstones (§14). `canonical_json`, `fingerprint`, `content_fingerprint`,
`classify_duplicate`, `stream_key` and `canonical_order` accept only exact
`Event`s, with no subclasses, and re-validate them. `model_construct` is
never used on protocol models.

## 13. Canonical serialisation

`canonical_json(event) -> bytes` produces:
- UTF-8 JSON;
- object keys sorted by code point (all schema keys and extension keys are
  ASCII, so this equals RFC 8785 ordering);
- no whitespace;
- strings escaped as in RFC 8785 (`\"`, `\\`, `\b\f\n\r\t`, other controls as `\u00xx`; everything else literal);
- integers in shortest decimal form;
- timestamps in canonical form;
- exactly the fields present: none added, none omitted.

The result is a fixed point: `canonical_json(parse(canonical_json(e))) ==
canonical_json(e)`. JSON lines files hold one canonical event per line.

## 14. Fingerprints, recorded events and erasure

- **`fingerprint(event)`** is `"sha256:"` + hex(SHA-256(`canonical_json(event)`)).
  It is used for integrity (bytes unchanged since acceptance) and replay
  evidence (a trace digest is the SHA-256 of its canonical JSONL).
- **`content_fingerprint(event)`** is the same digest over the event with
  `time.observed_at`, `source.adapter`, `source.stream_id` and `source.seq`
  removed. It identifies the content of a re-observed event (§15).
- Neither fingerprint is **authentication**: anyone can compute them. Source
  signatures over the canonical bytes are possible later (P11) without
  changing the event format.
- **`RecordedEvent`** is `{event, fingerprint, ingested_at: Timestamp,
  ingest_seq: int ≥ 0, secret_rules_version: int ≥ 1, policy_id?: Code}`. It is assigned by ingestion (P4).
  `ingest_seq` is unique and strictly increasing in commit order per
  workspace, and gaps are allowed.
- **Security erasure overrides immutability.** A stored event found to hold
  a secret or forbidden content is replaced by a tombstone. The tombstone
  keeps the original `fingerprint` and `content_fingerprint` as evidence of
  what was erased, plus `erased_at` and `reason_code`. It also keeps every
  identifier- and metadata-class field (§10.6) except `usage` and
  `extensions`: `event_type`, `time.*`, the `scope.*` ids, `source.*` and
  `causality.*`, and payload identifier- and metadata-class fields under the
  same rule. Every `sensitive-*` field is dropped.
  - A field that is the location of a hit, or that contains one, is dropped
    too, whatever its class.
  - A dropped field inside an object drops only that field, so a tombstone
    may lack fields that an event requires.
  - `event_id`, `workspace_id`, `event_type` and the two fingerprints are
    always kept; none of them can carry free text.
  - When the hit is in `provider_event_id`, the derived `event_id` is a
    guessing oracle for it, which is why rotation comes first.
  - Replays treat a tombstone as an event of unknown content.
  - Canonical order and gap detection treat it at its original position.
    If the hit was in `source.stream_id` and that field was dropped, the
    tombstone is ordered as a stream-less event at its kept time, and gap
    detection reports the slot as erased.
  - An incoming event whose `event_id` matches a tombstone is classified
    against the tombstone's two fingerprints, and is never re-accepted. Erasure covers every copy of
  the event: projections, exports and trace files, caches, indexes, and
  backups within their retention. It is done only after the leaked
  credential has been rotated, because the kept fingerprint could otherwise
  be used to confirm a guessed secret. This follows the security-baseline
  leak procedure, and P4 implements it. A newer
  secret-rule version never changes stored events by itself; re-scanning is
  an explicit operation.

## 15. Duplicates, and the boundary with ingestion

`classify_duplicate(existing, incoming)` requires both events to be in the
same workspace and raises `ValueError` otherwise. Ingestion calls it against
the stored event with the same `event_id` and against the stored event at the
same (stream key, `seq`). It returns the first match in this order of precedence:
- `exact_duplicate`: same `event_id` and same `fingerprint`. A no-op.
- `redelivery`: same `event_id` and same `content_fingerprint`. The same
  provider event was observed again (adapter restart, upgrade, re-read
  transcript). A no-op: the first accepted copy wins.
- `conflict`: same `event_id`, different content. The incoming event is
  rejected and quarantined (metadata only), the stored event is never
  replaced, and ingestion raises an alert attributed to the sending credential.
- `sequence_conflict`: a different `event_id`, but the same stream key and
  `seq`. Quarantined.
- `distinct`: anything else.

`DuplicateKind` has exactly these five values. An exact duplicate or a
redelivery still consumes its (stream key, `seq`) for gap detection.

Phase 2 provides these pure functions, the stream key and the canonical
order. Ingestion (P4) applies them against the store. Later phases must also:
- authenticate sources and bind credentials to (workspace, provider, adapter);
- assign `ingested_at` and `ingest_seq`;
- keep quarantine and drop records with retention;
- detect gaps;
- resolve references (causation exists, parents spawned, DAG acyclic,
  assignee exists);
- collect skew statistics;
- rate-limit;
- apply the field-classification policy (§10.6);
- implement security erasure (§14).

## 16. Versioning

- `spec_version = MAJOR.MINOR`. A validator supports an explicit set (v1: `{"1.0"}`).
- **An event is validated against the schema of its declared
  `spec_version`.** A field, type or enum value introduced in a later minor
  is a `schema_violation` under an earlier declared version. Emitters should
  declare the lowest version their event satisfies; validators do not
  enforce minimality. A newer minor than supported is `unsupported_version`.
- **Additive (minor):**
  - new event types;
  - new optional fields;
  - new enum values;
  - extension rules that only loosen;
  - additions to the currency allowlist.
- **Breaking (major):**
  - removing, renaming or retyping a field;
  - changing a meaning or unit;
  - tightening a rule;
  - changing the canonical form, either fingerprint input, or the `event_id` derivation.
- **Security exception.** Detectors may be added, the forbidden set may
  grow, and a detector may be narrowed to remove a demonstrated false
  positive, in a patch release (`SECRET_RULES_VERSION` + 1) with a
  superseding ADR signed off by Reviewer A. This tightening is not breaking. Stored events
  are handled as described in §14.
- **Migration:** stored events are never rewritten except by erasure (§14).
  Each version's validator is kept for replay. Readers upcast older majors in
  memory (P4). A fingerprint always refers to the event as accepted.
- Every change to this contract needs a superseding ADR signed off by both
  reviewers. A breaking change also needs a new major and its own frozen tag.

## 17. Interfaces (Python, `observatory.events`)

The package depends only on `observatory.core` and Pydantic. It is an
import-linter layer between `api | db | cache` and `core`; the layer is
optional until AO-P2-003 creates the package, and mandatory from then on.

```text
SPEC_VERSION = "1.0"; SUPPORTED_VERSIONS = frozenset({"1.0"}); SECRET_RULES_VERSION = 1
Event, Scope, EventTime, Source, Adapter, Causality         frozen strict models
<one payload model per §8 type>; ExtensionPayload
parse_event(raw: bytes) -> Accepted | Rejected                  always the current rules version
validate_event(data: object) -> Accepted | Rejected             always the current rules version
load_recorded(record: Mapping[str, object]) -> RecordedEvent    validates with record["secret_rules_version"]
SECRET_RULES: Mapping[int, RuleSet]                             every rules version; unknown version -> ValueError
canonical_json(event: Event) -> bytes
fingerprint(event: Event) -> str
content_fingerprint(event: Event) -> str
derive_event_id(workspace_id: str, provider: str, provider_event_id: str) -> str
sanitize_text(text: str) -> str
canonical_order(events: Iterable[Event]) -> list[Event]
stream_key(event: Event) -> tuple[str, str, str, str] | None
classify_duplicate(existing: Event, incoming: Event) -> DuplicateKind
RejectCode, Disposition, WarningCode, DuplicateKind         StrEnums (values as in §12/§6/§15)
RecordedEvent                                               model (§14)
```

`docs/contracts/event-protocol-v1.schema.json` is generated from the models
and checked by a golden test. It is informative. The Python validator is
normative, because a JSON Schema cannot express §10. The accepted and
rejected corpus of AO-P2-005 is the portable conformance evidence.

## 18. Fixtures and evidence (all synthetic)

- **Provider shapes.** Three synthetic shapes are mapped by test-only mappers
  (not adapters) to the same **projection** (`event_type`, scope, payload)
  for a shared scenario. Ids, time and provenance differ as §4 and §6 require.
  - A: a Claude/Codex-like transcript with tool use and cache-aware usage.
  - B: a generic orchestrator's lifecycle webhooks.
  - C: a minimal custom Python agent with no timestamps or provider ids. Its
    SDK-style emitter assigns `stream_id` and `seq` (§7).

  The fields each shape cannot map are listed as A-001 evidence.
- **Reference trace.** `reference-trace-v1.jsonl` is versioned, with a pinned
  SHA-256. Its scenario is a Coordinator with Backend, Frontend, Testing and
  Security Reviewer agents, covering:
  - spawn and assignment;
  - tools and file changes;
  - a failing test, a retry and a handoff message;
  - an error and a review;
  - usage, delta and cumulative;
  - completion with evidence.
- **Tests.**
  - golden contract tests;
  - seeded, bounded property tests: order permutation invariance, round trip,
    fingerprint stability;
  - adversarial tests for every rejection code and each detector, with one
    positive and one negative case each;
  - a 64 KiB worst-case timing test for the detectors.

## Clarifications during implementation (before the freeze)

AO-P2-003 raised these points and the coordinator ruled on them. Both
reviewers signed off on them (`docs/reviews/phase-2-contract-review.md`).
They make the contract exact without changing its design.

- **C0 (erratum).** The pinned Unicode data version for secret rules v1 is
  15.0.0, the version of the pinned runtime (Python 3.12). It is not 15.1.0.
- **C1.** At check 9 the field type is not known yet. The text tier is
  skipped only for a string at an Id or RelPath position that already
  satisfies that rule; every other string gets both tiers.
- **C2.** The quarantine metadata are optional fields of `Rejected`.
  `source.adapter` is kept only if both its name and its version are valid.
  `spec_version` matches `^(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})$`.
- **C3.** For `validate_event`, "raw" is the plain serialisation of the
  input tree: sorted keys, compact, UTF-8, with no timestamp normalisation.
  `raw_length` is 0 if the tree cannot be serialised. A
  container object reachable more than once is `invalid_json` (drop), which
  blocks reference bombs.
- **C4.** Each `Event` privately carries the secret-rules version it was
  validated under: the current version, or the recorded one through
  `load_recorded`. Only `load_recorded` may set it, and a forged or mutated
  value never downgrades the rules (fail closed). It is excluded from
  `canonical_json`, both fingerprints and `Event` equality. The pure
  functions re-validate under that version.
- **C5.** If `sanitize_text` finds a hit only in the NFKC form, it sanitises
  the NFKC form and repeats until the result is stable. If the result never
  settles, the whole string becomes `[REDACTED]`.
- **C6.** Each detector detail resolves toward over-masking:
  - a fixed table of `sudo` and `env` options that take an argument;
  - `-u` matched in attached form too;
  - `set` matched case-insensitively;
  - secret-named options matched after one dash or two.
- **C7.** Inside `extensions`, the namespace object is depth 1. An
  extension-event payload follows the namespace rules, including being non-empty.
- **C8.** `validate_event`'s pre-check `too_large` is drop, as the §12
  invariant requires.

AO-P2-004 and AO-P2-005 raised five more readings, which the coordinator
accepted. Reviewers A and B check them in the AO-P2-006 implementation review.

- **C9.** A missing or unequal required scope, a cumulative usage event
  without `unit_id`, and a `unit_id` that does not equal the required scope
  field are `schema_violation`. Only the §4 derivation rule and the listed
  self references are `invalid_reference`.
- **C10.** A vendor name equal to a core family name is rejected:
  `x-session.*` fails at `/event_type`, while `x-sessionco.*` is accepted.
- **C11.** ToolName and ModelName are printable ASCII `0x21`–`0x7e`, so a
  space is not allowed, as for ProviderRef.
- **C12.** The `unit_id` equality rule applies whenever `unit_id` is
  present, delta events included.
- **C13.** For §18, "the same projection" is compared with the
  `<provider>:` prefix removed from entity ids. §4 qualifies every entity id
  by provider, so ids from two shapes can never be literally equal.

## Consequences

- **Positive:**
  - one small, closed taxonomy;
  - deterministic bytes, order and duplicate rules;
  - secrets fail closed before anything is stored, and nothing rejected is stored raw;
  - adapters have an exact target.
- **Negative:**
  - strictness moves work to adapters, which must sanitise text, derive and
    qualify ids, keep streams contiguous and convert usage;
  - no message content in v1;
  - some legitimate free text is over-masked;
  - an `unsupported_version` event must be re-sent;
  - homoglyph evasion is a known limit (TD-026).
- Assumption: A-013 (renderers, exports and model consumers treat event text as data).
- Rollback: superseding ADR; nothing is stored in v1 yet.

## Review

- Reviewer A: APPROVE (round 4) · Reviewer B: APPROVE_WITH_NOTES (round 4, notes applied) — `docs/reviews/phase-2-contract-review.md`.
