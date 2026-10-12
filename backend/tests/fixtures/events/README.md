# Synthetic event-protocol fixtures (SYNTHETIC — no real data)

Everything in this directory is **synthetic**. It was written by hand for the
ADR-0008 tests. It contains no real transcripts, webhooks, people, hosts or
credentials. All names (`synthetic-ws`, `synthetic-*` providers, agents, tasks,
paths) are invented. A test that needs a credential-shaped value builds one by
concatenation at run time; such values never appear in these files.

| File | What it is |
|---|---|
| `synthetic-provider-a-transcript.jsonl` | Provider shape A: a Claude/Codex-like transcript (assistant `tool_use`, user `tool_result`, per-turn usage with Anthropic-like cache fields, sub-agent spawns, message ids) |
| `synthetic-provider-b-webhooks.json` | Provider shape B: generic orchestrator webhooks (tasks, agent lifecycle, reviews, offset timestamps, delivery ids, one re-delivery) |
| `synthetic-provider-c-agent.json` | Provider shape C: a minimal custom Python agent's plain step dicts (no timestamps, no ids) |
| `mappers.py` | Test-only mappers from A, B and C to ADR-0008 events. They are **not** product adapters (P3) |
| `reference.py` | Deterministic generator of the reference trace |
| `reference-trace-v1.jsonl` / `.sha256` | The versioned multi-agent reference trace (canonical JSONL) and its pinned digest |

Regenerate the reference trace (then review the diff and update the pinned digest in the test):

```sh
cd backend && .venv/bin/python -m tests.fixtures.events.reference
```
