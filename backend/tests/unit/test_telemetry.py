"""Typed usage telemetry and its log-redaction exemption (ADR-0007, TD-022).

Adversarial: only an exact, valid ``UsageMetrics`` survives redaction; key
names never earn the exemption, and secrets stay redacted around it.
"""

from __future__ import annotations

import json
import logging
import math
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from observatory.core.logging import REDACTED, configure_logging, redact
from observatory.core.telemetry import MAX_TOKENS, Money, UsageMetrics, usage_log_fields
from tests.unit.conftest import SettingsFactory

# Synthetic credential-shaped values, built at runtime so no source line looks like a secret.
BEARER = "Bearer " + "synthetic-bearer-" + "abc123def456"
API_KEY = "sk-" + "synthetic-" + "0123456789abcdef"
PEM = "-----BEGIN " + "PRIVATE KEY-----\nsynthetic\n-----END " + "PRIVATE KEY-----"
SECRETS = (BEARER, API_KEY, "synthetic-" + "s3cr3t", PEM)

log = logging.getLogger("observatory.test.telemetry")

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens")


def _usage() -> UsageMetrics:
    return UsageMetrics(
        input_tokens=1200,
        output_tokens=345,
        cached_input_tokens=800,
        reasoning_tokens=0,
        total_tokens=1545,
        reported_cost=Money(amount="0.0123", currency="USD"),
        estimated_cost=Money(amount="0.012", currency="USD"),
    )


EXPECTED = {
    "input_tokens": 1200,
    "output_tokens": 345,
    "cached_input_tokens": 800,
    "reasoning_tokens": 0,
    "total_tokens": 1545,
    "reported_cost": {"amount": "0.0123", "currency": "USD"},
    "estimated_cost": {"amount": "0.012", "currency": "USD"},
}


def _emit(fmt: str, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str], **kw: Any) -> str:
    configure_logging(make_settings(log_format=fmt, log_level="DEBUG"))
    log.info("turn finished", **kw)
    return capsys.readouterr().err


def _record(out: str) -> dict[str, Any]:
    (line,) = [ln for ln in out.splitlines() if ln.strip()]
    record: dict[str, Any] = json.loads(line)
    return record


# --- the model ---------------------------------------------------------------


def test_valid_usage_round_trips_through_json() -> None:
    usage = _usage()
    assert UsageMetrics.model_validate_json(usage.model_dump_json()) == usage


def test_unknown_stays_unknown() -> None:
    usage = UsageMetrics(output_tokens=7)
    assert usage.input_tokens is None
    assert usage.reported_cost is None
    assert usage.estimated_cost is None
    assert usage_log_fields(usage) == {"output_tokens": 7}  # nothing defaulted to 0, nothing derived


def test_empty_usage_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UsageMetrics()


@pytest.mark.parametrize("field", TOKEN_FIELDS)
@pytest.mark.parametrize(
    "bad",
    [
        -1,
        MAX_TOKENS + 1,
        10**30,
        True,
        False,
        1.0,
        float("nan"),
        float("inf"),
        Decimal(5),
        "5",
        " 5",
        "0x10",
        "1e3",
        "\u0661\u0662",  # non-ASCII digits
        API_KEY,
        BEARER,
        [5],
        {"value": 5},
    ],
    ids=repr,
)
def test_token_counts_reject_everything_but_bounded_ints(field: str, bad: object) -> None:
    with pytest.raises(ValidationError):
        UsageMetrics.model_validate({field: bad})


@pytest.mark.parametrize("field", TOKEN_FIELDS)
@pytest.mark.parametrize(
    "raw", ['"5"', "5.0", "true", "-3", "1e3", "NaN", "Infinity", "10000000000001", "null5"]
)
def test_json_strings_pretending_to_be_numbers_are_rejected(field: str, raw: str) -> None:
    with pytest.raises(ValidationError):
        UsageMetrics.model_validate_json(f'{{"{field}": {raw}}}')


@pytest.mark.parametrize("field", TOKEN_FIELDS)
def test_token_bounds_are_inclusive(field: str) -> None:
    assert getattr(UsageMetrics.model_validate({field: 0}), field) == 0
    assert getattr(UsageMetrics.model_validate({field: MAX_TOKENS}), field) == MAX_TOKENS


@pytest.mark.parametrize("amount", ["0", "1", "12.5", "0.000000000001", "999999999.999999999999"])
def test_canonical_amounts_are_accepted(amount: str) -> None:
    assert Money(amount=amount, currency="EUR").amount == amount


@pytest.mark.parametrize(
    "amount",
    [
        "-1",
        "+1",
        "01",
        "1.50",
        "1.",
        ".5",
        "1e3",
        "1E-3",
        "NaN",
        "Infinity",
        "1000000000",
        "0.0000000000001",
        "1,5",
        " 1",
        "1 ",
        "1\n",
        "\u0661",
        API_KEY,
        "",
    ],
)
def test_non_canonical_amounts_are_rejected(amount: str) -> None:
    with pytest.raises(ValidationError):
        Money(amount=amount, currency="USD")


@pytest.mark.parametrize("amount", [1, 1.5, Decimal("1.5"), True, None])
def test_amount_must_be_a_string(amount: object) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate({"amount": amount, "currency": "USD"})


@pytest.mark.parametrize("currency", ["usd", "US", "USDT", "U$D", "", "\uff35\uff33\uff24", "USD\n"])
def test_currency_must_be_iso_shaped(currency: str) -> None:
    with pytest.raises(ValidationError):
        Money(amount="1", currency=currency)


@pytest.mark.parametrize("extra", ["api_token", "authorization", "prompt", "response", "audio_tokens"])
def test_unknown_fields_are_rejected(extra: str) -> None:
    with pytest.raises(ValidationError):
        UsageMetrics.model_validate({"input_tokens": 1, extra: 1})


def test_usage_is_immutable() -> None:
    usage = _usage()
    with pytest.raises(ValidationError):
        usage.input_tokens = 5  # type: ignore[misc]


# --- the log exemption: numeric usage survives --------------------------------


def test_usage_survives_json_logging(
    make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _record(_emit("json", make_settings, capsys, extra={"usage": _usage()}))
    assert record["usage"] == EXPECTED


def test_nested_usage_survives_json_logging(
    make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    extra = {"turn": {"model": "synthetic-model", "usage": _usage(), "calls": [_usage()]}}
    record = _record(_emit("json", make_settings, capsys, extra=extra))
    assert record["turn"]["usage"] == EXPECTED
    assert record["turn"]["calls"] == [EXPECTED]


def test_usage_survives_console_logging(
    make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _emit("console", make_settings, capsys, extra={"usage": _usage(), "step": 3})
    rendered = out.split(" usage=", 1)[1].strip()
    assert json.loads(rendered) == EXPECTED
    assert "step=3" in out


# --- secrets stay redacted ------------------------------------------------------


@pytest.mark.parametrize("fmt", ["json", "console"])
@pytest.mark.parametrize(
    "extra",
    [
        {"input_tokens": 5},  # a usage-looking name earns nothing
        {"prompt_tokens": 5},
        {"usage": {"input_tokens": 5}},  # an untyped mapping earns nothing
        {"usage": [("total_tokens", 5)]},
    ],
    ids=repr,
)
def test_untyped_usage_is_still_redacted(
    fmt: str, extra: dict[str, Any], make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _emit(fmt, make_settings, capsys, extra=extra)
    assert REDACTED in out
    for shape in (": 5", "=5", ", 5"):
        assert shape not in out


@pytest.mark.parametrize("fmt", ["json", "console"])
@pytest.mark.parametrize("secret", SECRETS)
@pytest.mark.parametrize(
    "key",
    [
        "access_token",
        "refresh_tokens",
        "x-auth-token",
        "session_token",
        "input_tokens",
        "authorization",
        "cookie",
    ],
)
def test_credential_values_under_token_keys_stay_redacted(
    fmt: str, secret: str, key: str, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _emit(fmt, make_settings, capsys, extra={"payload": {key: secret, "usage": _usage()}})
    assert "synthetic" not in out
    if fmt == "json":
        assert _record(out)["payload"] == {key: REDACTED, "usage": EXPECTED}


@pytest.mark.parametrize("fmt", ["json", "console"])
def test_nested_secrets_next_to_usage_stay_redacted(
    fmt: str, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    extra = {
        "usage": _usage(),
        "request": {
            "headers": [("Authorization", BEARER), ("Cookie", "sid=" + API_KEY)],
            "body": {"client": {"credentials": {"password": API_KEY}}},
            "url": "https://user:" + API_KEY + "@api.example.invalid/v1",
            "note": "token=" + API_KEY,
            "key": PEM,
        },
    }
    out = _emit(fmt, make_settings, capsys, extra=extra)
    assert "synthetic" not in out
    if fmt == "json":
        assert _record(out)["usage"] == EXPECTED


@pytest.mark.parametrize("fmt", ["json", "console"])
@pytest.mark.parametrize("key", ["api_token", "token", "secret_usage", "Authorization", "password"])
def test_secret_named_key_wins_over_typed_usage(
    fmt: str, key: str, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _emit(fmt, make_settings, capsys, extra={"wrapper": {key: _usage()}})
    assert "1200" not in out
    assert REDACTED in out


def test_secret_named_pair_wins_over_typed_usage() -> None:
    assert redact([("token", _usage())]) == [["token", REDACTED]]


@pytest.mark.parametrize("fmt", ["json", "console"])
def test_usage_in_message_text_is_still_scrubbed(
    fmt: str, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_format=fmt, log_level="DEBUG"))
    log.info("usage %s", _usage())
    log.info(_usage())
    out = capsys.readouterr().err
    assert "1200" not in out


# --- bypass attempts ------------------------------------------------------------


class _Sub(UsageMetrics):
    """A subclass is not the allowlisted type, even if valid."""


def _bypass_objects() -> list[tuple[str, object]]:
    forged = UsageMetrics.model_construct(input_tokens=API_KEY)  # skips validation
    mutated = UsageMetrics(input_tokens=1)
    object.__setattr__(mutated, "output_tokens", BEARER)  # frozen bypass
    injected = UsageMetrics(input_tokens=1)
    injected.__dict__["api_key"] = API_KEY  # extra attribute: never read
    bad_money = UsageMetrics(reported_cost=Money.model_construct(amount=API_KEY, currency="USD"))
    bad_currency = UsageMetrics(reported_cost=Money.model_construct(amount="1", currency=PEM))
    money_as_dict = UsageMetrics(input_tokens=1)
    object.__setattr__(money_as_dict, "estimated_cost", {"amount": BEARER, "currency": "USD"})
    float_cost = UsageMetrics(input_tokens=1)
    object.__setattr__(float_cost, "reported_cost", Money.model_construct(amount=math.inf, currency="USD"))
    empty = UsageMetrics.model_construct()
    huge = UsageMetrics.model_construct(total_tokens=10**40)
    negative = UsageMetrics.model_construct(total_tokens=-5)
    return [
        ("forged", forged),
        ("mutated", mutated),
        ("injected", injected),
        ("bad_money", bad_money),
        ("bad_currency", bad_currency),
        ("money_as_dict", money_as_dict),
        ("float_cost", float_cost),
        ("empty", empty),
        ("huge", huge),
        ("negative", negative),
    ]


@pytest.mark.parametrize(("name", "obj"), _bypass_objects(), ids=[n for n, _ in _bypass_objects()])
def test_forged_usage_is_redacted_whole(name: str, obj: object) -> None:
    fields = usage_log_fields(obj)
    if name == "injected":  # valid fields; the injected attribute is never read
        assert fields == {"input_tokens": 1}
    else:
        assert fields is None


@pytest.mark.parametrize("fmt", ["json", "console"])
@pytest.mark.parametrize(("name", "obj"), _bypass_objects(), ids=[n for n, _ in _bypass_objects()])
def test_forged_usage_never_leaks(
    fmt: str, name: str, obj: object, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _emit(fmt, make_settings, capsys, extra={"usage": obj})
    assert "synthetic" not in out
    assert "10000000000000000000000000000000000000000" not in out
    if fmt == "json" and name != "injected":
        assert _record(out)["usage"] == REDACTED


@pytest.mark.parametrize("fmt", ["json", "console"])
def test_subclass_is_not_exempt(
    fmt: str, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _emit(fmt, make_settings, capsys, extra={"usage": _Sub(input_tokens=1200)})
    assert "1200" not in out


@pytest.mark.parametrize("fmt", ["json", "console"])
@pytest.mark.parametrize(
    "key",
    ["usage\nforged=1", "usage\x1b[31m", "token=" + API_KEY, "a password=" + API_KEY],
    ids=repr,
)
def test_hostile_keys_cannot_inject_or_leak(
    fmt: str, key: str, make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _emit(
        fmt, make_settings, capsys, extra={"wrap": {key: _usage()}} if fmt == "json" else {key: _usage()}
    )
    assert "synthetic" not in out
    assert "\x1b" not in out
    assert len([ln for ln in out.splitlines() if ln.strip()]) == 1  # no forged second record


def test_valid_usage_object_is_not_mutated_by_redaction() -> None:
    usage = _usage()
    assert redact({"usage": usage})["usage"] is usage
    assert usage == _usage()
