"""JSON trees: canonical text, plain-tree inspection, schema shapes and pointers (ADR-0008 §§12, 13)."""

from __future__ import annotations

import json
import types
import typing
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from functools import cache
from typing import Annotated, Any, Final, get_args, get_origin

from pydantic import BaseModel

from observatory.events.ids import ID_POSITION, MAX_SAFE_INT, PATH_POSITION

MAX_BYTES: Final = 64 * 1024
MAX_DEPTH: Final = 16
MAX_POINTER: Final = 256

Segment = str | int
Pointer = tuple[Segment, ...]


def canonical_text(tree: object) -> str:
    """Sorted keys (code point), no whitespace, RFC 8785 string escapes, shortest integers (§13)."""
    return json.dumps(tree, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def utf8_length(text: str) -> int:
    """UTF-8 length; a lone surrogate (rejected later as forbidden) counts as 3 bytes."""
    return len(text.encode("utf-8", "surrogatepass"))


def _int_length(value: int) -> int:
    magnitude = abs(value)
    if magnitude <= MAX_SAFE_INT:
        return len(str(value))
    digits = max(1, int(magnitude.bit_length() * 0.30102999566398120))  # never str() a huge int
    while 10**digits <= magnitude:
        digits += 1
    return digits + (value < 0)


@dataclass(slots=True)
class TreeReport:
    """What ``inspect_tree`` found: plain types only, container depth, canonical size, safe integers."""

    plain: bool = True
    depth: int = 0
    size: int = 0
    safe_integers: bool = True


def inspect_tree(data: object) -> TreeReport:
    """Check exact built-in JSON types on an acyclic tree without shared containers (C3)."""
    report = TreeReport()
    seen: set[int] = set()
    stack: list[tuple[object, int]] = [(data, 1)]
    while stack:
        node, depth = stack.pop()
        kind = type(node)
        if kind is str:
            report.size += utf8_length(json.dumps(node, ensure_ascii=False))
        elif kind is bool:
            report.size += 4 if node else 5
        elif kind is int:
            report.size += _int_length(typing.cast(int, node))
            report.safe_integers &= abs(typing.cast(int, node)) <= MAX_SAFE_INT
        elif kind is dict or kind is list:
            if id(node) in seen:
                report.plain = False
                return report
            seen.add(id(node))
            report.depth = max(report.depth, depth)
            children: list[object]
            if kind is dict:
                mapping = typing.cast(dict[object, object], node)
                if any(type(k) is not str for k in mapping):
                    report.plain = False
                    return report
                report.size += sum(utf8_length(json.dumps(k, ensure_ascii=False)) + 1 for k in mapping)
                children = list(mapping.values())
            else:
                children = list(typing.cast(list[object], node))
            report.size += 2 + max(0, len(children) - 1)
            stack.extend((child, depth + 1) for child in children)
        else:
            report.plain = False
            return report
    return report


# --- schema shapes -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Shape:
    """What the schema says about a position: a model (known keys), a list, an Id, a RelPath, or free."""

    kind: str
    fields: Mapping[str, Shape] = field(default_factory=dict)
    item: Shape | None = None


FREE: Final = Shape("free")
LEAF: Final = Shape("leaf")


@cache
def model_shape(model: type[BaseModel]) -> Shape:
    """The shape of a model's fields; a model that allows extra keys is free."""
    if model.model_config.get("extra") == "allow":
        return FREE
    fields = {
        name: _shape_of(info.annotation, tuple(info.metadata)) for name, info in model.model_fields.items()
    }
    return Shape("model", types.MappingProxyType(fields))


def _shape_of(annotation: Any, metadata: tuple[object, ...] = ()) -> Shape:  # noqa: PLR0911 (one per form)
    if ID_POSITION in metadata:
        return Shape("id")
    if PATH_POSITION in metadata:
        return Shape("path")
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *extra = get_args(annotation)
        return _shape_of(base, tuple(extra))
    if origin is typing.Union or origin is types.UnionType:
        options = [a for a in get_args(annotation) if a is not type(None)]
        return _shape_of(options[0]) if len(options) == 1 else FREE
    if origin in (list, tuple):
        return Shape("list", item=_shape_of(get_args(annotation)[0]))
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return model_shape(annotation)
    return FREE if origin is dict else LEAF


def child_shape(shape: Shape, key: Segment) -> tuple[Shape, bool]:
    """The shape at ``key`` under ``shape`` and whether the schema defines that position."""
    if isinstance(key, str) and shape.kind == "model" and key in shape.fields:
        return shape.fields[key], True
    if isinstance(key, int) and shape.kind == "list" and shape.item is not None:
        return shape.item, True
    return FREE, False


def known_prefix(path: tuple[Segment, ...], shape: Shape) -> Pointer:
    """The longest prefix of ``path`` made of schema-defined keys and array indices (§12)."""
    out: list[Segment] = []
    for segment in path:
        shape, known = child_shape(shape, segment)
        if not known:
            break
        out.append(segment)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Entry:
    """One member of a container: its key or index, value and their schema positions."""

    container_path: tuple[Segment, ...]
    container_pointer: Pointer
    key: Segment
    value: object
    shape: Shape
    pointer: Pointer


def walk(tree: object, shape: Shape) -> Iterator[Entry]:
    """Every member of every container, with pointers truncated at the first unknown key."""
    stack: list[tuple[object, Shape, Pointer, tuple[Segment, ...]]] = [(tree, shape, (), ())]
    while stack:
        node, node_shape, pointer, path = stack.pop()
        members: Iterator[tuple[Segment, object]]
        if type(node) is dict:
            members = iter(typing.cast(dict[str, object], node).items())
        elif type(node) is list:
            members = enumerate(typing.cast(list[object], node))
        else:
            continue
        for key, value in members:
            value_shape, known = child_shape(node_shape, key)
            value_pointer = (*pointer, key) if known else pointer
            yield Entry(path, pointer, key, value, value_shape, value_pointer)
            if type(value) in (dict, list):
                stack.append((value, value_shape, value_pointer, (*path, key)))


def pointer_order(pointer: Pointer) -> tuple[tuple[int, int | str], ...]:
    """Segment-by-segment order: array indices numerically, keys by code point (§12)."""
    return tuple((0, s) if isinstance(s, int) else (1, s) for s in pointer)


def format_pointer(pointer: Pointer) -> str:
    """RFC 6901 text, at most 256 characters, cut at a segment boundary with ``/…``."""
    segments = [str(s).replace("~", "~0").replace("/", "~1") for s in pointer]
    text = "".join(f"/{s}" for s in segments)
    while len(text) > MAX_POINTER:
        segments.pop()
        text = "".join(f"/{s}" for s in segments) + "/…"
    return text
