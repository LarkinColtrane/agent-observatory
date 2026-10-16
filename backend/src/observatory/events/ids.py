"""Scalar types, identity and time (ADR-0008 §§3, 4, 6).

Every pattern is ASCII and checked against the whole string. Ids are opaque:
compared byte for byte, never normalised.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Final

from pydantic import AfterValidator, BeforeValidator, Field, StringConstraints, WithJsonSchema

from observatory.events.text import is_rel_path, is_safe_line

MAX_SAFE_INT: Final = 2**53 - 1

WORKSPACE_ID_PATTERN: Final = r"^[a-z0-9][a-z0-9-]{0,62}$"
ID_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
SLUG_PATTERN: Final = r"^[a-z][a-z0-9-]{1,31}$"
VERSION_PATTERN: Final = r"^(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,5})$"
SPEC_VERSION_PATTERN: Final = r"^(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})$"  # C2
PROVIDER_REF_PATTERN: Final = r"^[\x21-\x7e]{1,256}$"
CODE_PATTERN: Final = r"^[a-z][a-z0-9_.-]{0,63}$"
NAME_PATTERN: Final = r"^[\x21-\x7e]{1,128}$"  # ToolName, ModelName: printable ASCII as in ProviderRef

_COMPILED: Final[dict[str, re.Pattern[str]]] = {}


def matches(pattern: str, value: object) -> bool:
    """True if ``value`` is exactly a ``str`` matching ``pattern`` as a whole."""
    if type(value) is not str:
        return False
    regex = _COMPILED.get(pattern)
    if regex is None:
        regex = _COMPILED[pattern] = re.compile(pattern)
    return regex.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class Position:
    """Marks a field whose valid values skip the text tier (§10.3, C1)."""

    kind: str


ID_POSITION: Final = Position("id")
PATH_POSITION: Final = Position("path")

# --- UUIDs and derived event ids (§4) ----------------------------------------------

_UUID: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-([478])[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def uuid_version(value: object) -> int | None:
    """The version (4, 7 or 8) of a valid protocol UUID, else ``None`` (nil and max are invalid)."""
    match = _UUID.fullmatch(value) if type(value) is str else None
    return int(match[1]) if match else None


def _check_uuid(value: str) -> str:
    if uuid_version(value) is None:
        raise ValueError("invalid UUID")
    return value


_EVENT_ID_DOMAIN: Final = "ao-event-id/v1"


def derive_event_id(workspace_id: str, provider: str, provider_event_id: str) -> str:
    """UUIDv8 from SHA-256 of the workspace, provider and provider event id (§4)."""
    if not (
        matches(WORKSPACE_ID_PATTERN, workspace_id)
        and matches(SLUG_PATTERN, provider)
        and matches(PROVIDER_REF_PATTERN, provider_event_id)
    ):
        raise ValueError("derive_event_id needs a WorkspaceId, a Slug and a ProviderRef")
    material = "\0".join((_EVENT_ID_DOMAIN, workspace_id, provider, provider_event_id)).encode("ascii")
    raw = bytearray(hashlib.sha256(material).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x80  # version 8
    raw[8] = (raw[8] & 0x3F) | 0x80  # RFC 9562 variant
    return str(uuid.UUID(bytes=bytes(raw)))


# --- timestamps (§6) -----------------------------------------------------------------

_TIMESTAMP: Final = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?Z"
)


def parse_timestamp(value: str) -> datetime:
    """The UTC instant of a protocol timestamp; ``ValueError`` if it is not one."""
    match = _TIMESTAMP.fullmatch(value)
    if match is None or not 2000 <= int(match[1]) <= 2099:
        raise ValueError("invalid timestamp")
    year, month, day, hour, minute, second = (int(match[i]) for i in range(1, 7))
    fraction = int((match[7] or "").ljust(6, "0"))
    try:
        return datetime(year, month, day, hour, minute, second, fraction, tzinfo=UTC)  # rejects 60 s
    except ValueError:
        raise ValueError("invalid timestamp") from None


def canonical_timestamp(value: str) -> str:
    """The canonical form (6 fraction digits) of a protocol timestamp."""
    instant = parse_timestamp(value)
    return f"{value[:19]}.{instant.microsecond:06d}Z"


# --- validated scalar types (§3) -----------------------------------------------------


def _check_line(value: str) -> str:
    if not is_safe_line(value):
        raise ValueError("text must be single-line safe text")
    return value


def _as_tuple(value: object) -> object:
    return tuple(value) if type(value) is list else value  # JSON arrays arrive as lists


def _sorted_set(values: tuple[str, ...]) -> tuple[str, ...]:
    if list(values) != sorted(set(values)):
        raise ValueError("id lists are unique and in ascending code-point order")
    return values


def _check_rel_path(value: str) -> str:
    if not is_rel_path(value):
        raise ValueError("invalid relative path")
    return value


_LINE: Final = AfterValidator(_check_line)

WorkspaceId = Annotated[str, StringConstraints(pattern=WORKSPACE_ID_PATTERN)]
Id = Annotated[str, StringConstraints(pattern=ID_PATTERN), ID_POSITION]
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]
Version = Annotated[str, StringConstraints(pattern=VERSION_PATTERN)]
ProviderRef = Annotated[str, StringConstraints(pattern=PROVIDER_REF_PATTERN)]
Code = Annotated[str, StringConstraints(pattern=CODE_PATTERN)]
EventUuid = Annotated[
    str,
    AfterValidator(_check_uuid),
    WithJsonSchema({"type": "string", "pattern": f"^{_UUID.pattern}$"}),
]
Timestamp = Annotated[
    str,
    AfterValidator(canonical_timestamp),
    WithJsonSchema({"type": "string", "pattern": f"^{_TIMESTAMP.pattern}$"}),
]
RelPath = Annotated[
    str,
    AfterValidator(_check_rel_path),
    WithJsonSchema({"type": "string", "minLength": 1, "maxLength": 1024, "pattern": "^[^/]"}),
    PATH_POSITION,
]
Seq = Annotated[int, Field(ge=0, le=MAX_SAFE_INT)]
Count = Annotated[int, Field(ge=0, le=10**9)]
DurationMs = Annotated[int, Field(ge=0, le=2_592_000_000)]
Text64 = Annotated[str, StringConstraints(min_length=1, max_length=64), _LINE]
Text128 = Annotated[str, StringConstraints(min_length=1, max_length=128), _LINE]
Text200 = Annotated[str, StringConstraints(min_length=1, max_length=200), _LINE]
Text512 = Annotated[str, StringConstraints(min_length=1, max_length=512), _LINE]
Text1024 = Annotated[str, StringConstraints(min_length=1, max_length=1024), _LINE]
ToolName = Annotated[str, StringConstraints(pattern=NAME_PATTERN)]
ModelName = Annotated[str, StringConstraints(pattern=NAME_PATTERN)]
Int32 = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]
Attempt = Annotated[int, Field(ge=2, le=1000)]


def _set_schema(item_pattern: str, max_items: int) -> WithJsonSchema:
    item = {"type": "string", "pattern": item_pattern}
    return WithJsonSchema(
        {"type": "array", "items": item, "minItems": 1, "maxItems": max_items, "uniqueItems": True}
    )


#: Id sets (§3): 1-64 unique Ids in ascending code-point order; any other order is rejected.
IdSet64 = Annotated[
    tuple[Id, ...],
    BeforeValidator(_as_tuple),
    Field(min_length=1, max_length=64),
    AfterValidator(_sorted_set),
    _set_schema(ID_PATTERN, 64),
]
#: Sets of 1-32 event ids, as above.
UuidSet32 = Annotated[
    tuple[EventUuid, ...],
    BeforeValidator(_as_tuple),
    Field(min_length=1, max_length=32),
    AfterValidator(_sorted_set),
    _set_schema(f"^{_UUID.pattern}$", 32),
]
