"""Golden contract tests: hand-written events, pinned canonical bytes and fingerprints (ADR-0008 §§4, 13, 14).

The literals below are the anchor for an independent re-derivation: anyone can
recompute them from ADR-0008 alone (sorted keys, no whitespace, RFC 8785 string
escapes, 6-digit fractions, SHA-256). A change to any of them is a breaking change.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from observatory.events import (
    Accepted,
    canonical_json,
    content_fingerprint,
    derive_event_id,
    fingerprint,
    parse_event,
    validate_event,
)

SDK = {"name": "golden-sdk", "version": "0.1.0"}

GOLDEN: dict[str, tuple[dict[str, Any], bytes, str, str]] = {
    "minimal": (
        {
            "spec_version": "1.0",
            "event_id": "01890a5d-ac96-774b-bcce-b302099a8057",
            "event_type": "session.started",
            "scope": {"workspace_id": "golden-ws", "session_id": "s-1"},
            "time": {"observed_at": "2026-01-01T00:00:00Z"},
            "source": {"provider": "golden", "adapter": SDK},
            "payload": {"session_id": "s-1"},
        },
        b'{"event_id":"01890a5d-ac96-774b-bcce-b302099a8057","event_type":"session.started",'
        b'"payload":{"session_id":"s-1"},"scope":{"session_id":"s-1","workspace_id":"golden-ws"},'
        b'"source":{"adapter":{"name":"golden-sdk","version":"0.1.0"},"provider":"golden"},"spec_version":"1.0",'
        b'"time":{"observed_at":"2026-01-01T00:00:00.000000Z"}}',
        "sha256:87e59c59d235191f28e2830def699db1e7993bcfeed6e91ade5a6b151fe9211d",
        "sha256:ace1707a983d10d6b3cb55bbbd6dfce54849ef40be16c88c3be6dc17321817aa",
    ),
    "derived id, escapes, stream": (
        {
            "spec_version": "1.0",
            "event_id": "7a66fe38-1fe9-87dd-a2a8-20d2ac9c0a65",
            "event_type": "tool.call_started",
            "scope": {"workspace_id": "golden-ws", "agent_id": "golden:agent-1"},
            "time": {"occurred_at": "2026-01-01T00:00:01.5Z", "observed_at": "2026-01-01T00:00:02.25Z"},
            "source": {
                "provider": "golden",
                "adapter": SDK,
                "stream_id": "golden:stream-1",
                "seq": 3,
                "provider_event_id": "run-7/tool-3",
            },
            "payload": {
                "call_id": "golden:tool-3",
                "tool_name": "Bash",
                "kind": "command",
                "command": 'echo "caf' + chr(0xE9) + '" \\ done',
            },
        },
        b'{"event_id":"7a66fe38-1fe9-87dd-a2a8-20d2ac9c0a65","event_type":"tool.call_started",'
        b'"payload":{"call_id":"golden:tool-3","command":"echo \\"caf\xc3\xa9\\" \\\\ done","kind":"command",'
        b'"tool_name":"Bash"},"scope":{"agent_id":"golden:agent-1","workspace_id":"golden-ws"},'
        b'"source":{"adapter":{"name":"golden-sdk","version":"0.1.0"},"provider":"golden",'
        b'"provider_event_id":"run-7/tool-3","seq":3,"stream_id":"golden:stream-1"},"spec_version":"1.0",'
        b'"time":{"observed_at":"2026-01-01T00:00:02.250000Z","occurred_at":"2026-01-01T00:00:01.500000Z"}}',
        "sha256:8da492da2bd3546f4e126d9e29077ecd760fd5c2ad1b36e57256fd5d8765577a",
        "sha256:d6d54ea7c469fa468b31018581c183a27db11e3ef725c347c3ba88d7e023ea9d",
    ),
    "usage, cost, extensions": (
        {
            "spec_version": "1.0",
            "event_id": "4b1d6c1e-2f3a-4b5c-9d6e-7f8091a2b3c4",
            "event_type": "usage.recorded",
            "scope": {"workspace_id": "golden-ws", "agent_id": "golden:agent-1"},
            "time": {"observed_at": "2026-01-01T00:00:03.000001Z"},
            "source": {"provider": "golden", "adapter": SDK},
            "causality": {"correlation_id": "golden:corr-1"},
            "payload": {
                "usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 250,
                    "output_tokens": 50,
                    "estimated_cost": {"amount": "0.0042", "currency": "EUR"},
                },
                "accounting": "delta",
                "unit": "model_call",
                "pricing_ref": "golden-prices/v1",
            },
            "extensions": {"x-golden": {"region": "eu", "retries": 0, "cached": True}},
        },
        b'{"causality":{"correlation_id":"golden:corr-1"},"event_id":"4b1d6c1e-2f3a-4b5c-9d6e-7f8091a2b3c4",'
        b'"event_type":"usage.recorded","extensions":{"x-golden":{"cached":true,"region":"eu","retries":0}},'
        b'"payload":{"accounting":"delta","pricing_ref":"golden-prices/v1","unit":"model_call",'
        b'"usage":{"cached_input_tokens":250,"estimated_cost":{"amount":"0.0042","currency":"EUR"},'
        b'"input_tokens":1000,"output_tokens":50}},"scope":{"agent_id":"golden:agent-1","workspace_id":"golden-ws"},'
        b'"source":{"adapter":{"name":"golden-sdk","version":"0.1.0"},"provider":"golden"},"spec_version":"1.0",'
        b'"time":{"observed_at":"2026-01-01T00:00:03.000001Z"}}',
        "sha256:b6c0aabe63d60bb6f6ec22d7caaf1f19a72f70721e34486da381e4c4f6f50e16",
        "sha256:2577c5341d45aba735c01c5ddf004b33cea26b8228f689ea35033341307a9d40",
    ),
    "extension event": (
        {
            "spec_version": "1.0",
            "event_id": "01890a5d-ac96-774b-bcce-b302099a8058",
            "event_type": "x-golden.checkpoint",
            "scope": {"workspace_id": "golden-ws"},
            "time": {"observed_at": "2026-01-01T00:00:04Z"},
            "source": {"provider": "golden", "adapter": SDK},
            "payload": {"step": "lint", "ok": True, "counts": [3, 0]},
        },
        b'{"event_id":"01890a5d-ac96-774b-bcce-b302099a8058","event_type":"x-golden.checkpoint",'
        b'"payload":{"counts":[3,0],"ok":true,"step":"lint"},"scope":{"workspace_id":"golden-ws"},'
        b'"source":{"adapter":{"name":"golden-sdk","version":"0.1.0"},"provider":"golden"},"spec_version":"1.0",'
        b'"time":{"observed_at":"2026-01-01T00:00:04.000000Z"}}',
        "sha256:94902d2c7a576367466ae5bd163eee3375c5f9637e4e0d540214f511b90e5788",
        "sha256:7a7e96b780bcf29564f8ac24c12e765493f4a94b39e4fb6aab1ee72e90bb6bc5",
    ),
}


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_bytes_and_fingerprints(name: str) -> None:
    data, expected, expected_fingerprint, expected_content = GOLDEN[name]
    accepted = validate_event(data)
    assert isinstance(accepted, Accepted)
    assert canonical_json(accepted.event) == expected
    assert expected_fingerprint == "sha256:" + hashlib.sha256(expected).hexdigest()
    assert (accepted.fingerprint, fingerprint(accepted.event)) == (expected_fingerprint, expected_fingerprint)
    assert (accepted.content_fingerprint, content_fingerprint(accepted.event)) == (
        expected_content,
        expected_content,
    )
    reparsed = parse_event(expected)
    assert isinstance(reparsed, Accepted)
    assert canonical_json(reparsed.event) == expected


def test_golden_derived_event_id() -> None:
    assert derive_event_id("golden-ws", "golden", "run-7/tool-3") == "7a66fe38-1fe9-87dd-a2a8-20d2ac9c0a65"
    material = b"ao-event-id/v1\x00golden-ws\x00golden\x00run-7/tool-3"
    # First 128 bits of the SHA-256; then version nibble a -> 8 and variant byte 22 -> a2.
    assert hashlib.sha256(material).hexdigest()[:32] == "7a66fe381fe9a7dd22a820d2ac9c0a65"
