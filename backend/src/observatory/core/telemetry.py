"""Typed usage telemetry (ADR-0007).

``UsageMetrics`` is the only usage data that log redaction preserves, and the
event protocol reuses it. The exemption is by *type*, never by key name: a
mapping such as ``{"input_tokens": 5}`` is still redacted.
"""

from __future__ import annotations

from typing import Annotated, Final, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

#: Upper bound for any token count (well above any real session; rejects absurd values).
MAX_TOKENS: Final = 10**12

#: Canonical non-negative decimal: no sign, exponent, leading zero or trailing fraction zero.
DECIMAL_AMOUNT_PATTERN: Final = r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{0,11}[1-9])?$"
CURRENCY_PATTERN: Final = r"^[A-Z]{3}$"

TokenCount = Annotated[int, Field(strict=True, ge=0, le=MAX_TOKENS)]

# hide_input_in_errors: a rejected value is never echoed in an error (R-A-P2-001-06).
_STRICT: Final = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class Money(BaseModel):
    """An amount in one currency. Binary floats are never accepted for money."""

    model_config = _STRICT

    amount: Annotated[str, StringConstraints(pattern=DECIMAL_AMOUNT_PATTERN)]
    currency: Annotated[str, StringConstraints(pattern=CURRENCY_PATTERN)]


class UsageMetrics(BaseModel):
    """Model usage as reported or estimated; an absent field means unknown, never zero.

    Canonical meanings (ADR-0007 §Semantics); producers convert provider counts:
    ``input_tokens`` counts all input, cache reads and cache writes included;
    ``cached_input_tokens`` is the part of it read from cache; ``reasoning_tokens``
    is the part of ``output_tokens`` spent on reasoning; ``total_tokens`` is only
    ever the provider's own total, never computed. Whether the values are a delta
    or a running total is stated by the record that carries them.
    """

    model_config = _STRICT

    input_tokens: TokenCount | None = None
    output_tokens: TokenCount | None = None
    cached_input_tokens: TokenCount | None = None
    reasoning_tokens: TokenCount | None = None
    total_tokens: TokenCount | None = None
    #: Cost as reported by the provider.
    reported_cost: Money | None = None
    #: Cost computed by Observatory (never by copying ``reported_cost``).
    estimated_cost: Money | None = None

    @field_validator("reported_cost", "estimated_cost", mode="before")
    @classmethod
    def _exact_money(cls, value: object) -> object:
        # Pydantic accepts model instances, subclasses included, without re-validating
        # them (R-A-P2-001-01): only an exact Money is taken, and re-checked as a mapping.
        if type(value) is Money:
            return {"amount": value.__dict__.get("amount"), "currency": value.__dict__.get("currency")}
        if isinstance(value, BaseModel):
            raise ValueError("cost must be exactly Money")
        return value

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if all(getattr(self, name) is None for name in USAGE_FIELDS):
            raise ValueError("usage metrics need at least one known value")
        # Subset rules from the canonical meanings; checked only when both are known.
        for part, whole in (("cached_input_tokens", "input_tokens"), ("reasoning_tokens", "output_tokens")):
            part_value, whole_value = getattr(self, part), getattr(self, whole)
            if part_value is not None and whole_value is not None and part_value > whole_value:
                raise ValueError(f"{part} cannot exceed {whole}")
        return self


#: The fixed field names; rendering reads only these.
USAGE_FIELDS: Final[tuple[str, ...]] = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "total_tokens",
    "reported_cost",
    "estimated_cost",
)
_MONEY_FIELDS: Final = frozenset({"reported_cost", "estimated_cost"})


def usage_log_fields(value: object) -> dict[str, object] | None:
    """Re-validated plain fields of an exact ``UsageMetrics``, or ``None`` if not safe to log.

    Re-validation guards objects built with ``model_construct`` or mutated
    after construction; only the fixed field names are read.
    """
    if type(value) is not UsageMetrics:
        return None
    try:
        raw: dict[str, object] = {}
        for name in USAGE_FIELDS:
            field = value.__dict__.get(name)
            if name in _MONEY_FIELDS and field is not None and type(field) not in (Money, dict):
                return None  # e.g. a Money subclass: never trusted (R-A-P2-001-01)
            raw[name] = field  # an exact Money is re-checked field by field by _exact_money
        checked = UsageMetrics.model_validate(raw)
        out: dict[str, object] = {}
        for name in USAGE_FIELDS:
            field = getattr(checked, name)
            if isinstance(field, Money):
                out[name] = {"amount": str(field.amount), "currency": str(field.currency)}
            elif field is not None:
                out[name] = int(field)
        return out
    except Exception:  # any failure on a tampered object fails closed (R-A-P2-001-04)
        return None
