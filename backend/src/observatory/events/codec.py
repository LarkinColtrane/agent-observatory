"""Bounded JSON parsing, canonical JSON and fingerprints (ADR-0008 §§10.1, 12, 13, 14)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Final

from observatory.events.codes import RejectCode
from observatory.events.envelope import event_tree, revalidate
from observatory.events.ids import MAX_SAFE_INT
from observatory.events.tree import MAX_DEPTH, canonical_text

MAX_INTEGER_DIGITS: Final = 16
UTF8_BOM: Final = b"\xef\xbb\xbf"

# Strings are skipped whole (an unterminated one runs to the end), so brackets inside them never count.
_DEPTH_TOKEN: Final = re.compile(r'"(?:[^"\\]++|\\[\s\S])*+"?|[\[\]{}]')


def exceeds_depth(text: str, limit: int = MAX_DEPTH) -> bool:
    """String-aware pre-scan: True if brackets nest deeper than ``limit`` (the top level is 1)."""
    depth = 0
    for match in _DEPTH_TOKEN.finditer(text):
        char = text[match.start()]
        if char in "[{":
            depth += 1
            if depth > limit:
                return True
        elif char in "]}":
            depth -= 1
    return False


@dataclass(slots=True)
class _Flags:
    duplicate_key: bool = False
    float_seen: bool = False
    bad_integer: bool = False


def parse_json(text: str) -> object | RejectCode:
    """Decode ``text`` with hooks; the first of checks 4-7 that fails, in that order, else the tree."""
    flags = _Flags()

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = dict(items)
        flags.duplicate_key |= len(result) != len(items)
        return result

    def no_float(_literal: str) -> int:
        flags.float_seen = True
        return 0

    def bounded_int(literal: str) -> int:
        if len(literal.lstrip("-")) > MAX_INTEGER_DIGITS or literal == "-0":
            flags.bad_integer = True  # rejected before int() ever sees it
            return 0
        value = int(literal)
        flags.bad_integer |= abs(value) > MAX_SAFE_INT
        return value

    decoder = json.JSONDecoder(
        object_pairs_hook=pairs, parse_float=no_float, parse_int=bounded_int, parse_constant=no_float
    )
    try:
        tree: object = decoder.decode(text)
    except json.JSONDecodeError:
        return RejectCode.INVALID_JSON
    if flags.duplicate_key:
        return RejectCode.DUPLICATE_KEY
    if flags.float_seen:
        return RejectCode.FLOAT_NOT_ALLOWED
    if flags.bad_integer:
        return RejectCode.INTEGER_OUT_OF_RANGE
    return tree


def sha256_hex(data: bytes) -> str:
    """Prefixed SHA-256 digest, as used by both fingerprints and the quarantine record."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_json(event: object) -> bytes:
    """Canonical UTF-8 JSON of an exact, re-validated ``Event`` (§13)."""
    return canonical_text(event_tree(revalidate(event))).encode("utf-8")


def fingerprint(event: object) -> str:
    """``sha256:`` + hex SHA-256 of ``canonical_json(event)`` (§14)."""
    return sha256_hex(canonical_json(event))


def content_fingerprint(event: object) -> str:
    """The fingerprint without ``time.observed_at``, ``source.adapter``, ``stream_id`` and ``seq`` (§14)."""
    tree = event_tree(revalidate(event))
    tree["time"].pop("observed_at", None)
    for name in ("adapter", "stream_id", "seq"):
        tree["source"].pop(name, None)
    return sha256_hex(canonical_text(tree).encode("utf-8"))
