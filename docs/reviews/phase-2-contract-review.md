# Phase 2 contract review — ADR-0008 universal event protocol v1

Review of AO-P2-002, the `event-protocol` contract v1.0.0 (plan:
[P2-plan.md](../phases/P2-plan.md)), on branch `p2/002-contract`.
- **Reviewer A** covers security and privacy.
- **Reviewer B** covers protocol design, methodology and temporal semantics,
  in addition to architecture and concurrency.

Both reviewed in their own clones and did not modify the author's branch. The
contract is approved here and frozen at the end of P2 (ADR-0003 §3), after
the adversarial implementation review.

## Round 1 (`40ed833`): A REQUEST_CHANGES, B REQUEST_CHANGES

**Checks:**
- The governance checker, artifacts checker, 212 governance tests and
  `lint-imports` all passed.
- A probed `scrub_text` with CLI-style, invisible, confusable and NUL-split
  secrets, and probed Python `json` with huge integers, deep nesting,
  NaN/Infinity, `-0`, lone surrogates and duplicate keys.
- B modelled the ordering rule and probed stream-key mixing across workspaces.

| IDs | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-P2-002-01, R-B-P2-002-01 | blocker | Quarantine-disposition checks (floats, integers) ran before the secret scan | fixed: every check before the scan is drop; the invariant is stated; parse hooks reject NaN/Inf, `-0` and literals over 16 digits; `internal_error` added |
| R-A-P2-002-02 | blocker | Raw quarantine contradicted the security baseline and the owner's rule on unknown fields | fixed: no rejected event is ever stored raw; quarantine and drop records hold metadata only; `unsupported_version` is re-sent |
| R-B-P2-002-02 | blocker | Re-observed provider events became conflicts | fixed: `content_fingerprint` and the `redelivery` kind |
| R-A-P2-002-03 | major | Invisible and confusable characters evaded the scan | fixed: enumerated forbidden set and NFKC scan; cross-script homoglyphs recorded as TD-026 |
| R-A-P2-002-04 | major | `command` carried CLI secrets and heredoc bodies | fixed: single line, Text(1024), truncation; CLI detectors |
| R-A-P2-002-05, -06 | major | Ambiguous usage exemption; pointers echoed attacker keys | fixed: exemption covers the key name only, compared on tuple paths; pointer rules |
| R-A-P2-002-07, R-B-P2-002-04 | major | Pure functions were not scoped to a workspace; bare v8 UUIDs allowed squatting | fixed: 4-tuple stream key; mixed workspaces raise; v8 if and only if `provider_event_id` is present |
| R-A-P2-002-08, R-B-P2-002-18 | major | `Event` construction skipped the secret scan | fixed: construction runs checks 9–15; exact types only |
| R-A-P2-002-09, R-B-P2-002-11 | major | Detectors could not evolve; stored secrets could not be erased | fixed: event detector set owned by `observatory.events` and versioned; patch-release security exception (Reviewer A); erasure by tombstone |
| R-A-P2-002-10 | major | Field classification missing | fixed: §10.6 and policy limits |
| R-B-P2-002-03, -05, -06, -07, -10 | medium | Defaults ambiguous; `seq` semantics; version validated against; cumulative instance key; set order | fixed: no defaults or nulls; contiguous `seq`, new stream on restart; validated against declared version; `unit_id`; sorted id sets |
| R-B-P2-002-08 | medium | The key/value scrub dropped valid structural ids | fixed: two detector tiers (credential tier everywhere, text tier on free text only) |
| R-B-P2-002-09, -12 to -17, -19 to -21; R-A-P2-002-11 to -20 | minor/low/nit | Agent requirement, order preconditions, Provider C streams, provider-id scope, canonical size, self-spawn, pointer order, fixture ACs, governance consistency; parser pinning, entity-id injectivity, `derive_event_id` arguments, RelPath gaps, byte equality, digest oracle, cost provenance and ISO list, extension denylist, A-013 scope, `-0` | fixed as proposed |

## Round 2 (`858e986`): A APPROVE_WITH_NOTES, B REQUEST_CHANGES

| IDs | Sev | Finding | Disposition |
|---|---|---|---|
| R-A-P2-002-21, R-B-P2-002-22 | major / blocking | Credential detectors named only by prefix; `sk-` matched `task-42` | fixed: exact v1 patterns with boundaries; mandatory negative corpus in AO-P2-003 AC4 |
| R-B-P2-002-23 | blocking | A rules patch could break replay of stored events | fixed: `RecordedEvent.secret_rules_version`; stored events validated under their recorded version; newer rules only by explicit re-scan |
| R-A-P2-002-22 | minor | Ids skip the text tier | (a) declined: it would drop structural ids that R-B-P2-002-08 requires; recorded as a known limit (TD-026) with a test; (b) applied |
| R-A-P2-002-23 to -29; R-B-P2-002-24 to -28 | minor/low/nit | mysql `-p` rule, denylist scope, exact built-in types, namespace-level policy, erasure scope and rotation, digest residual, unidata pinning; tombstone shape, quarantine stream slot, policy and dedup, duplicate precedence, pointer index order, command pipeline, TAB/LF | fixed as proposed |

## Round 3 (`53d0baf`): A APPROVE_WITH_NOTES, B REQUEST_CHANGES

| IDs | Sev | Finding | Disposition |
|---|---|---|---|
| R-B-P2-002-29 | blocking | The PEM pattern matched only the header, so a single-line key body survived `sanitize_text` | fixed: replacement extent runs through the END line or to the end of the string; AC4 test |
| R-A-P2-002-30 | major | A tombstone could keep the secret it erases | fixed: a field holding a hit is dropped whatever its class |
| R-A-P2-002-31 to -33; R-B-P2-002-30 to -32 | minor/low/nit | No rules downgrade on acceptance; URL userinfo with `/`; command fixed point; Bearer/Basic on paths; rules-version API; `sudo mysql` | fixed as proposed (`parse_event`/`validate_event` always use the current rules; `load_recorded` uses the recorded version) |

## Round 4 (`bf627d7`): A APPROVE, B APPROVE_WITH_NOTES

Both reviewers checked only the round-3 diff. Notes applied before merge:
- `sudo`/`env` options are skipped (A);
- the position of a tombstone whose `stream_id` was dropped (B);
- why the truncate-and-sanitise loop terminates (B).

Carried into the AO-P2-003 review: tests for skipping sudo/env options, and
a requirement that `load_recorded` is never used to accept a new event.

## Round 5 (`5894c26`, `d79215a`): clarifications C0–C8 raised during AO-P2-003, A APPROVE, B APPROVE

W-P stopped AO-P2-003 on one contradiction and eight gaps:
- the pinned Unicode data version said 15.1.0, but Python 3.12 ships 15.0.0;
- tier selection at check 9;
- the quarantine metadata fields;
- `validate_event` raw bytes;
- the rules version carried by an event;
- `sanitize_text` on NFKC-only hits;
- detector details;
- extension depth;
- the `too_large` disposition.

The coordinator ruled on each as clarification C0–C8 in ADR-0008. C0 is an
erratum; the others resolve toward over-scanning and over-masking, with no
change of design. Both reviewers signed off, and their wording notes on C3
and C4 are applied (`d79215a`). Reviewer A's C4 note was passed to AO-P2-003
as a test requirement: only `load_recorded` sets the private rules version,
and it never downgrades.

## Round 6: adversarial implementation review (AO-P2-006, `918050c` → `af8f58d`), A APPROVE, B APPROVE

This is the freeze review that ADR-0003 §3 requires. Fresh reviewer agents
attacked the implementation and the contract text together; the findings
and dispositions are in `docs/reviews/phase-2-reviews.md`. The contract
gained clarifications C9–C13 from implementation and amendments C14–C26
from this review. Each one tightens the contract or makes it exact; none
changes the design.

Reviewer B derived the canonical bytes, fingerprints, derived event ids and
the trace digest from ADR-0008 alone, and they matched the implementation.
Both reviewers state that ADR-0008 with C0–C26 can be frozen as
`contract-event-protocol-v1.0.0`.

<!-- final-verdicts -->
- **Reviewer A final outcome:** APPROVE — AO-P2-002 round 4 (`bf627d7`)
- **Reviewer B final outcome:** APPROVE_WITH_NOTES — AO-P2-002 round 4 (`bf627d7`), notes applied before merge
- **Reviewer A final outcome:** APPROVE — ADR-0008 clarifications C0–C8 (`5894c26`)
- **Reviewer B final outcome:** APPROVE — ADR-0008 clarifications C0–C8 (`5894c26`), wording notes applied in `d79215a`
- **Reviewer A final outcome:** APPROVE — ADR-0008 with C0–C26, freeze review AO-P2-006 round 3 (`af8f58d`)
- **Reviewer B final outcome:** APPROVE — ADR-0008 with C0–C26, freeze review AO-P2-006 round 3 (`af8f58d`)
