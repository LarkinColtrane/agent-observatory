"""Payload base, cross-field rules and extension values (ADR-0008 §§8, 11).

The core payload models and the registry the envelope dispatches on are in
``taxonomy``.
"""

from __future__ import annotations

import re
import typing
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_core import PydanticCustomError

from observatory.core.logging import _normalize_key
from observatory.events.text import is_safe_line
from observatory.events.tree import Pointer, canonical_text, pointer_order, utf8_length

if TYPE_CHECKING:
    from observatory.events.envelope import Event

STRICT: Final = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

NAMESPACE: Final = re.compile(r"x-[a-z][a-z0-9-]{1,30}")
EXTENSION_TYPE: Final = re.compile(r"(?P<vendor>x-[a-z][a-z0-9-]{1,30})\.[a-z][a-z0-9_]{0,63}")
_EXTENSION_KEY: Final = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
#: Content denylist (§11): a normalised key containing any of these is a schema violation.
CONTENT_DENYLIST: Final = (
    "prompt", "completion", "content", "response", "body", "stdout",
    "stderr", "output", "input", "messages", "env", "header",
)  # fmt: skip
MAX_NAMESPACES: Final = 4
MAX_EXTENSIONS_BYTES: Final = 4 * 1024
MAX_EXTENSION_PAYLOAD_BYTES: Final = 8 * 1024
MAX_EXTENSION_DEPTH: Final = 4
MAX_EXTENSION_ARRAY: Final = 32
MAX_EXTENSION_TEXT: Final = 512
#: The five ADR-0007 token-count names whose key-name test is exempt in ``usage.recorded`` (§10.3).
USAGE_TOKEN_KEYS: Final = frozenset(
    {"input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens"}
)


def denied_name(name: str) -> bool:
    """True if ``name``, normalised as in ADR-0005, contains a denylisted word."""
    normalized = _normalize_key(name)
    return any(word in normalized for word in CONTENT_DENYLIST)


def _check_extension_value(value: object, depth: int) -> None:
    kind = type(value)
    if kind is str:
        text = typing.cast(str, value)
        if not 1 <= len(text) <= MAX_EXTENSION_TEXT or not is_safe_line(text):
            raise ValueError("extension text must be Text(512)")
    elif kind is dict:
        check_extension_object(typing.cast(dict[str, object], value), depth + 1, allow_empty=True)
    elif kind is list:
        items = typing.cast(list[object], value)
        if depth + 1 > MAX_EXTENSION_DEPTH or len(items) > MAX_EXTENSION_ARRAY:
            raise ValueError("extension array too deep or too long")
        for item in items:
            _check_extension_value(item, depth + 1)
    elif kind is not int and kind is not bool:  # integer range is check 7
        raise ValueError("extension values are strings, integers, booleans, arrays or objects")


def check_extension_object(value: object, depth: int = 1, *, allow_empty: bool = False) -> None:
    """Check one extension object; a namespace object (or an extension payload) is depth 1 (C7)."""
    if type(value) is not dict or depth > MAX_EXTENSION_DEPTH:
        raise ValueError("extension object expected within depth 4")
    members = typing.cast(dict[str, object], value)
    if not members and not allow_empty:
        raise ValueError("an extension namespace is a non-empty object")
    for key, item in members.items():
        if _EXTENSION_KEY.fullmatch(key) is None or denied_name(key):
            raise ValueError("invalid or denylisted extension key")
        _check_extension_value(item, depth)


def check_extensions(value: dict[str, Any]) -> dict[str, Any]:
    """The ``extensions`` rules of §11: 1-4 namespaces, 4 KiB canonical in total."""
    if not 1 <= len(value) <= MAX_NAMESPACES:
        raise ValueError("extensions hold 1 to 4 namespaces")
    for namespace, content in value.items():
        if NAMESPACE.fullmatch(namespace) is None or denied_name(namespace):
            raise ValueError("invalid or denylisted namespace")
        check_extension_object(content)
    if utf8_length(canonical_text(value)) > MAX_EXTENSIONS_BYTES:
        raise ValueError("extensions exceed 4 KiB canonical")
    return value


CROSS_FIELD: Final = "cross_field"


def check_rules(violations: list[Pointer]) -> None:
    """Raise one cross-field error at the smallest violated position (relative to the payload)."""
    if violations:
        at = min(violations, key=pointer_order)
        raise PydanticCustomError(CROSS_FIELD, "cross-field rule violated", {"at": at})


class EventPayload(BaseModel):
    """Base of every payload model; a closed schema selected by ``event_type``."""

    model_config = STRICT

    def scope_errors(self, scope: Mapping[str, object]) -> tuple[Pointer, ...]:
        """Required-scope rules (§8) against the raw ``scope``, as pointers from the event root; check 13."""
        del scope
        return ()

    def reference_errors(self, event: Event) -> tuple[Pointer, ...]:
        """Self references (§8) that fail, as pointers from the event root; part of check 14."""
        del event
        return ()


class ExtensionPayload(EventPayload):
    """Payload of an ``x-<vendor>.<name>`` event: extension values, at most 8 KiB canonical (§11)."""

    model_config = ConfigDict(frozen=True, extra="allow", strict=True, hide_input_in_errors=True)

    @model_validator(mode="before")
    @classmethod
    def _extension_values(cls, data: Any) -> Any:
        check_extension_object(data)
        if utf8_length(canonical_text(data)) > MAX_EXTENSION_PAYLOAD_BYTES:
            raise ValueError("extension payload exceeds 8 KiB canonical")
        return data
