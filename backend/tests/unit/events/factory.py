"""Synthetic events and credentials for the protocol tests.

Every credential-shaped value is built at runtime by concatenation, so no
source line looks like a secret. All data is synthetic.
"""

from __future__ import annotations

import copy
import json
import random
from typing import Any

from observatory.events import Accepted, Event, Rejected, validate_event

WS = "ws-1"
EVENT_ID = "0190a8f2-6b1c-7d3e-8f4a-123456789abc"  # v7
OTHER_ID = "4b1d6c1e-2f3a-4b5c-9d6e-7f8091a2b3c4"  # v4

# --- synthetic credentials (one per detector) ------------------------------------------
SK = "sk-" + "synthetic" + "0" * 20
GH = "gh" + "p_" + "A1" * 18
GH_PAT = "github_" + "pat_" + "B2" * 11
SLACK = "xox" + "b-" + "1234567890" + "ab"
AWS = "AK" + "IA" + "ABCDEFGHIJ012345"
GOOGLE = "AI" + "za" + "C" * 35
JWT = "ey" + "J" + "a" * 10 + "." + "ey" + "J" + "b" * 10 + "." + "c" * 6
PEM_BODY = "MIIE" + "synthetickeybodysynthetickeybody"
PEM = "-----BEGIN " + "PRIVATE KEY-----\\n" + PEM_BODY + "\\n-----END " + "PRIVATE KEY-----"
URL = "https://" + "alice" + ":" + "pa/ss" + "w0rd" + "@" + "host.example/x"
BEARER = "Bearer " + "q" * 20
CREDENTIALS = {
    "openai": SK,
    "github": GH,
    "github_pat": GH_PAT,
    "slack": SLACK,
    "aws": AWS,
    "google": GOOGLE,
    "jwt": JWT,
    "pem": PEM,
    "url": URL,
}


def base_tree() -> dict[str, Any]:
    """A valid ``session.started`` event as a plain tree."""
    return {
        "spec_version": "1.0",
        "event_id": EVENT_ID,
        "event_type": "session.started",
        "scope": {"workspace_id": WS, "session_id": "sess-1", "agent_id": "claude-code:agent-1"},
        "time": {"occurred_at": "2026-03-01T10:00:00.5Z", "observed_at": "2026-03-01T10:00:01Z"},
        "source": {
            "provider": "claude-code",
            "adapter": {"name": "cc-adapter", "version": "1.2.3"},
            "stream_id": "stream-a",
            "seq": 0,
        },
        "payload": {"session_id": "sess-1", "initiator": "human"},
    }


def tree(*changes: tuple[str, object]) -> dict[str, Any]:
    """``base_tree`` with ``("a.b.c", value)`` changes; a value of ``DELETE`` removes the key."""
    out = base_tree()
    for path, value in changes:
        *parents, last = path.split(".")
        node = out
        for key in parents:
            node = node.setdefault(key, {})
        if value is DELETE:
            node.pop(last, None)
        else:
            node[last] = copy.deepcopy(value)
    return out


DELETE: Any = object()


def raw(data: object) -> bytes:
    """Compact JSON bytes of ``data``."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def accept(data: object) -> Accepted:
    result = validate_event(data)
    assert isinstance(result, Accepted), result
    return result


def build(*changes: tuple[str, object]) -> Event:
    return accept(tree(*changes)).event


def reject(data: object) -> Rejected:
    result = validate_event(data)
    assert isinstance(result, Rejected), result
    return result


def uuid7(rng: random.Random) -> str:
    """A seeded, valid UUIDv7 string."""
    value = rng.getrandbits(128)
    value = (value & ~(0xF << 76)) | (0x7 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)
    text = f"{value:032x}"
    return f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"
