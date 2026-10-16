"""Structured logging and mandatory redaction (ADR-0005 §3)."""

from __future__ import annotations

import dataclasses
import io
import json
import logging
import math
import sys
import threading
import time
import types
import warnings
from typing import Any

import pytest

from observatory.core.logging import (
    REDACTED,
    SECRET_KEY_PARTS,
    ConsoleFormatter,
    JsonFormatter,
    _extras,
    _render_message,
    configure_logging,
    is_secret_key,
    mask_key_values,
    mask_url_credentials,
    redact,
    request_id_var,
    scrub_text,
)
from tests.unit.conftest import SettingsFactory

# Synthetic values only. Each must never appear in any output.
# Built at runtime so no source line looks like a credential to secret scanners.
SENTINEL = "synthetic-" + "s3cr3t-value"
URL_PW = "synthetic-" + "url-pw"
DSN = "postgresql+psycopg://app_user:" + URL_PW + "@db.internal:5432/observatory"

log = logging.getLogger("observatory.test")

# ADR-0005 §3, copied literally: the implementation may match more, never less.
ADR_SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
    "cookie",
    "x-api-key",
    "client_secret",
    "dsn",
    "database_url",
    "redis_url",
)


def _json_lines(err: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in err.splitlines() if line.strip()]


def _our_handler() -> logging.Handler:
    (handler,) = (h for h in logging.getLogger().handlers if getattr(h, "_observatory_handler", False))
    return handler


@pytest.fixture
def json_logging(make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]) -> None:
    # Requests capsys first so set-up output is captured too.
    configure_logging(make_settings(log_format="json", log_level="DEBUG"))


def test_adr_key_list_is_implemented() -> None:
    assert set(ADR_SECRET_KEY_PARTS) <= set(SECRET_KEY_PARTS)


@pytest.mark.parametrize("part", ADR_SECRET_KEY_PARTS)
def test_every_key_family_is_redacted(
    part: str, json_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    key = part.replace("-", "_")  # extra keys must be identifiers for most callers
    log.info("event", extra={key: SENTINEL, f"nested_{part}": {"x": SENTINEL}})
    out = capsys.readouterr().err
    assert SENTINEL not in out
    record = _json_lines(out)[0]
    assert record[key] == REDACTED


@pytest.mark.parametrize(
    "key",
    [
        "Password",
        "DB_PASSWORD",
        "x-api-key",
        "X-Api-Key",
        "myAuthorizationHeader",
        "SESSION_COOKIE",
        "sentry_dsn",
        "Api-Key",
        "privateKey",
        "accessKey",
        "databaseUrl",
        "REDIS-URL",
        "auth",
        "AUTH",
        b"password",
        b"Authorization",
        b"auth",  # exact match needs the decoded key, not "b'auth'"
    ],
)
def test_key_match_is_case_insensitive_substring(key: str | bytes) -> None:
    assert is_secret_key(key)


@pytest.mark.parametrize("key", ["user", "host", "status", "request_id", "count", "author", "authority"])
def test_ordinary_keys_are_not_secret(key: str) -> None:
    assert not is_secret_key(key)


def test_nested_mappings_and_sequences(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    payload = {
        "service": "db",
        "conn": {
            "Client_Secret": SENTINEL,
            "user": "alice",
            "deeper": [{"apiKey": SENTINEL}, ("ok", {"TOKEN": SENTINEL})],
        },
        "items": [{"password": SENTINEL}, {"passwd": SENTINEL}],
        "urls": [DSN],
        "ids": {1, 2},
    }
    log.info("nested", extra={"payload": payload})
    out = capsys.readouterr().err
    assert SENTINEL not in out
    assert URL_PW not in out
    rec = _json_lines(out)[0]["payload"]
    assert rec["conn"]["Client_Secret"] == REDACTED
    assert rec["conn"]["user"] == "alice"
    assert rec["conn"]["deeper"][0]["apiKey"] == REDACTED
    assert rec["conn"]["deeper"][1] == ["ok", {"TOKEN": REDACTED}]
    assert rec["items"] == [{"password": REDACTED}, {"passwd": REDACTED}]
    assert rec["urls"] == ["postgresql+psycopg://[REDACTED]@db.internal:5432/observatory"]
    assert sorted(rec["ids"]) == [1, 2]


def test_url_credentials_in_message_and_args(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    log.info(f"connecting to {DSN}")
    log.info("connecting to %s via %r", DSN, "redis://:" + URL_PW + "@cache:6379/0")
    out = capsys.readouterr().err
    assert URL_PW not in out
    first, second = _json_lines(out)
    assert first["msg"] == "connecting to postgresql+psycopg://[REDACTED]@db.internal:5432/observatory"
    assert "redis://[REDACTED]@cache:6379/0" in second["msg"]


def test_secret_keys_in_args(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    log.info("cfg %(user)s %(password)s", {"user": "alice", "password": SENTINEL})
    log.info("cfg %s", {"api_key": SENTINEL, "user": "bob"})
    log.info({"token": SENTINEL, "msg": "mapping as message"})
    out = capsys.readouterr().err
    assert SENTINEL not in out
    a, b, c = (r["msg"] for r in _json_lines(out))
    assert a == f"cfg alice {REDACTED}"
    assert REDACTED in b
    assert "bob" in b
    assert REDACTED in c


def test_unformattable_args_do_not_leak(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    # Handled by our handler directly: pytest's own capture handler raises on bad args.
    record = log.makeRecord(log.name, logging.INFO, __file__, 1, "only one %s", (SENTINEL, DSN), None)
    _our_handler().handle(record)
    out = capsys.readouterr().err
    assert SENTINEL not in out
    assert URL_PW not in out
    assert "could not be formatted" in _json_lines(out)[0]["msg"]


def test_url_credentials_in_exception_and_traceback(
    json_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    def connect() -> None:
        dsn = DSN  # appears in the exception text
        raise ConnectionError(f"could not connect to {dsn}")

    try:
        try:
            connect()
        except ConnectionError as exc:
            raise RuntimeError(f"startup failed for {DSN}") from exc
    except RuntimeError:
        log.exception("startup failed")
    log.warning("with stack", stack_info=True, extra={"target": DSN})
    out = capsys.readouterr().err
    assert URL_PW not in out
    records = _json_lines(out)
    assert "Traceback" in records[0]["exc_info"]
    assert "ConnectionError" in records[0]["exc_info"]
    assert "[REDACTED]@db.internal" in records[0]["exc_info"]
    assert "Stack (most recent call last)" in records[1]["exc_info"]


def test_preformatted_exc_text_is_masked(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    record = log.makeRecord(log.name, logging.ERROR, __file__, 1, "boom", None, None)
    record.exc_text = f"Traceback: {DSN}"
    log.handle(record)
    out = capsys.readouterr().err
    assert URL_PW not in out
    assert _json_lines(out)[0]["exc_info"].endswith("[REDACTED]@db.internal:5432/observatory")


def test_non_string_extra_values_are_stringified_and_masked(
    json_logging: None, capsys: pytest.CaptureFixture[str]
) -> None:
    class Opaque:
        def __str__(self) -> str:
            return f"Opaque({DSN})"

    log.info("obj", extra={"thing": Opaque(), "n": 3, "ok": True, "nothing": None, "ratio": 0.5})
    out = capsys.readouterr().err
    assert URL_PW not in out
    rec = _json_lines(out)[0]
    assert rec["thing"].startswith("Opaque(postgresql+psycopg://[REDACTED]@")
    assert (rec["n"], rec["ok"], rec["nothing"], rec["ratio"]) == (3, True, None, 0.5)


def test_json_record_shape_and_request_id(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    log.info("outside")
    token = request_id_var.set("req-12345678")
    try:
        log.info("inside", extra={"ts": "spoof", "user": "alice"})
    finally:
        request_id_var.reset(token)
    outside, inside = _json_lines(capsys.readouterr().err)
    assert set(outside) == {"ts", "level", "logger", "msg", "request_id"}
    assert outside["request_id"] is None
    assert outside["level"] == "INFO"
    assert outside["logger"] == "observatory.test"
    assert outside["ts"].endswith("Z")
    assert inside["request_id"] == "req-12345678"
    assert inside["ts"] != "spoof"  # core fields are never overridden by extras
    assert inside["user"] == "alice"


def test_console_format_redacts(make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(log_format="console"))
    token = request_id_var.set("req-console-1")
    try:
        log.info("dsn %s", DSN, extra={"password": SENTINEL, "user": "alice"})
    finally:
        request_id_var.reset(token)
    try:
        raise ValueError(DSN)
    except ValueError:
        log.exception("failed")
    log.info("plain")
    out = capsys.readouterr().err
    assert SENTINEL not in out
    assert URL_PW not in out
    assert "[req-console-1]" in out
    assert "password='[REDACTED]'" in out
    assert "user='alice'" in out
    assert "Traceback" in out
    assert "[-] plain" in out


def test_level_is_applied_and_invalid_level_rejected(
    make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_level="warning"))
    log.info("hidden")
    log.warning("shown")
    lines = _json_lines(capsys.readouterr().err)
    assert [r["msg"] for r in lines] == ["shown"]
    with pytest.raises(ValueError, match="unknown log level"):
        configure_logging(make_settings(log_level="LOUD"))


def test_configure_is_idempotent_and_replaces_foreign_handlers(
    make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    foreign = logging.StreamHandler()
    logging.getLogger().addHandler(foreign)
    uvicorn_handler = logging.StreamHandler()
    logging.getLogger("uvicorn.error").addHandler(uvicorn_handler)
    logging.getLogger("uvicorn.error").propagate = False

    configure_logging(make_settings())
    configure_logging(make_settings())

    root = logging.getLogger()
    assert foreign not in root.handlers
    assert len(root.handlers) == 1
    assert logging.getLogger("uvicorn.error").handlers == []
    assert logging.getLogger("uvicorn.error").propagate is True
    logging.getLogger("uvicorn.error").info("server %s", DSN, extra={"color_message": DSN})
    out = capsys.readouterr().err
    assert len(_json_lines(out)) == 1
    assert URL_PW not in out
    assert "color_message" not in out


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("postgresql://u:p@h/db", "postgresql://[REDACTED]@h/db"),
        ("redis://:p@h:6379", "redis://[REDACTED]@h:6379"),
        ("x_postgresql://u:p@ss@h", "x_postgresql://[REDACTED]@h"),  # unencoded "@" in password
        ("amqp://u:" + "p?#x@h", "amqp://[REDACTED]@h"),
        ("https://token@github.com/org", "https://[REDACTED]@github.com/org"),
        ("https://example.com/a@b", "https://[REDACTED]@b"),  # over-masking is accepted
        ("postgresql://u:ab/LEAKME@h/db", "postgresql://[REDACTED]@h/db"),  # "/" in the password
        (f"dsn {DSN} end", "dsn postgresql+psycopg://[REDACTED]@db.internal:5432/observatory end"),
        ("redis://default:p/w@cache:6379/0", "redis://[REDACTED]@cache:6379/0"),
        ("https://example.com/path", "https://example.com/path"),
        ("mail alice@example.com", "mail alice@example.com"),
        ("a://u:p@h b://v:q@i", "a://[REDACTED]@h b://[REDACTED]@i"),
    ],
)
def test_mask_url_credentials(text: str, expected: str) -> None:
    assert mask_url_credentials(text) == expected


@pytest.mark.parametrize(
    "hostile",
    [
        "://" * 50_000 + "a" * 50_000,
        "://" + "a" * 100_000,
        "a" * 100_000 + "=",
        "password=" * 20_000,
        "x: " * 30_000,
        "'" * 50_000 + "token=" + "'" * 50_000,
    ],
)
def test_scrubbing_is_fast_on_hostile_input(hostile: str) -> None:
    started = time.monotonic()
    scrub_text(hostile)
    assert time.monotonic() - started < 2.0


def test_redact_depth_limit_and_no_mutation() -> None:
    cyclic: dict[str, Any] = {"password": SENTINEL}
    cyclic["self"] = cyclic
    out = redact(cyclic)
    assert out["password"] == REDACTED
    assert cyclic["password"] == SENTINEL  # input untouched
    node = out
    while isinstance(node, dict):
        node = node["self"]
    assert node == "[TRUNCATED]"


def test_redact_keeps_tuples_and_objects_for_formatting() -> None:
    marker = object()
    assert redact(("a", marker), stringify=False) == ("a", marker)
    assert redact(["a", marker], stringify=False) == ["a", marker]


def test_handler_failure_never_prints_record_data(
    json_logging: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_format(record: logging.LogRecord) -> str:
        raise RuntimeError("formatter exploded")

    handler = _our_handler()
    monkeypatch.setattr(handler, "format", broken_format)
    record = log.makeRecord(log.name, logging.INFO, __file__, 1, "dsn %s", (DSN,), None)
    setattr(record, "password", SENTINEL)  # noqa: B010 (keeps the line scanner-clean)
    handler.handle(record)
    err = capsys.readouterr().err
    assert "logging error (RuntimeError)" in err
    assert "details suppressed" in err
    assert SENTINEL not in err
    assert URL_PW not in err
    assert "dsn" not in err


def test_handler_follows_stderr_redirection(json_logging: None, monkeypatch: pytest.MonkeyPatch) -> None:
    redirected = io.StringIO()
    monkeypatch.setattr(sys, "stderr", redirected)
    log.info("after redirect %s", DSN)
    assert _json_lines(redirected.getvalue())[0]["msg"] == "after redirect " + DSN.replace(
        f"app_user:{URL_PW}", REDACTED
    )


# --- text scrubbing: key=value / key: value forms ---------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("host=h password=pw1 dbname=x", f"host=h password={REDACTED} dbname=x"),  # libpq
        ("/healthz?token=t1" + "&api_key=k1&x=1", f"/healthz?token={REDACTED}&api_key={REDACTED}&x=1"),
        ("Cfg(password='a b', user='u')", f"Cfg(password='{REDACTED}', user='u')"),  # dataclass repr
        ("{'password': 'p1', 'user': 'u'}", f"{{'password': '{REDACTED}', 'user': 'u'}}"),
        ('{"Api-Key": "k1"}', f'{{"Api-Key": "{REDACTED}"}}'),
        ("Authorization: Bearer abc.def", f"Authorization: {REDACTED}"),
        ("SECRET = s1;", f"SECRET = {REDACTED};"),
        ('cfg="password=p1"', f'cfg="password={REDACTED}"'),  # nested in a non-secret value
        ('password="' + 'token=abc" next', f'password="{REDACTED}" next'),  # secret inside a redacted value
        ("user=alice at 12:30 status: ok", "user=alice at 12:30 status: ok"),
        ("password reset requested", "password reset requested"),
        ("password=&next=1", "password=&next=1"),  # empty value: nothing to redact
    ],
)
def test_mask_key_values(text: str, expected: str) -> None:
    assert mask_key_values(text) == expected


@pytest.mark.parametrize("text", ["token=x&a=1", "password: 'x'", f"{DSN} password=y", "auth=[x]"])
def test_scrub_text_is_idempotent(text: str) -> None:
    once = scrub_text(text)
    assert scrub_text(once) == once


def test_scrub_text_applies_both_masks() -> None:
    assert scrub_text(f"{DSN}?sslpassword=x") == (
        f"postgresql+psycopg://{REDACTED}@db.internal:5432/observatory?sslpassword={REDACTED}"
    )


def test_uvicorn_access_line_query_secrets(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    access = logging.getLogger("uvicorn.access")
    access.info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:5000",
        "GET",
        f"/healthz?token={SENTINEL}&api_key={SENTINEL}",
        "1.1",
        200,
    )
    out = capsys.readouterr().err
    assert SENTINEL not in out
    assert _json_lines(out)[0]["msg"] == (
        f'127.0.0.1:5000 - "GET /healthz?token={REDACTED}&api_key={REDACTED} HTTP/1.1" 200'
    )


@dataclasses.dataclass
class _Cfg:
    user: str
    password: str


def test_dataclass_repr_in_args_and_extras(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    log.info(
        "cfg %s / %r", _Cfg("alice", SENTINEL), _Cfg("bob", SENTINEL), extra={"cfg": _Cfg("carol", SENTINEL)}
    )
    out = capsys.readouterr().err
    assert SENTINEL not in out
    rec = _json_lines(out)[0]
    assert (
        rec["msg"]
        == f"cfg _Cfg(user='alice', password='{REDACTED}') / _Cfg(user='bob', password='{REDACTED}')"
    )
    assert rec["cfg"] == f"_Cfg(user='carol', password='{REDACTED}')"


def test_dict_in_exception_traceback(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    try:
        raise ValueError({"user": "alice", "password": SENTINEL, "dsn": f"host=h password={SENTINEL}"})
    except ValueError:
        log.exception("bad config")
    out = capsys.readouterr().err
    assert SENTINEL not in out
    assert f"'password': '{REDACTED}'" in _json_lines(out)[0]["exc_info"]


def test_libpq_dsn_in_message(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    log.info("connecting with %s", f"host=db port=5432 user=app password={SENTINEL} sslmode=require")
    out = capsys.readouterr().err
    assert SENTINEL not in out
    assert _json_lines(out)[0]["msg"].endswith(f"password={REDACTED} sslmode=require")


# --- structural redaction ----------------------------------------------------


def test_header_pairs_in_sequences(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    headers = [
        (b"authorization", b"Bearer " + SENTINEL.encode()),
        ("x-api-key", SENTINEL),
        ("accept", "json"),
    ]
    log.info("request", extra={"headers": headers, "auth": ("user", SENTINEL)})
    out = capsys.readouterr().err
    assert SENTINEL not in out
    rec = _json_lines(out)[0]
    assert rec["headers"] == [["b'authorization'", REDACTED], ["x-api-key", REDACTED], ["accept", "json"]]
    assert rec["auth"] == REDACTED


def test_pair_rule_applies_only_inside_sequences() -> None:
    assert redact(("token", "visible-by-design"), stringify=False) == ("token", "visible-by-design")
    assert redact([("token", SENTINEL)], stringify=False) == [("token", REDACTED)]


def test_non_string_messages_are_redacted(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    log.info([{"password": [SENTINEL, SENTINEL]}, DSN])

    class Message:
        def __str__(self) -> str:
            return f"Message(token={SENTINEL})"

    log.info(Message())
    out = capsys.readouterr().err
    assert SENTINEL not in out
    assert URL_PW not in out
    first, second = (r["msg"] for r in _json_lines(out))
    assert first.startswith(f"[{{'password': '{REDACTED}'}}")
    assert second == f"Message(token={REDACTED})"


def test_non_finite_floats_keep_json_valid(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    log.info("ratios", extra={"nan": math.nan, "inf": math.inf, "nested": [-math.inf], "ok": 0.5})

    def reject(constant: str) -> None:
        raise ValueError(constant)

    rec = json.loads(capsys.readouterr().err, parse_constant=reject)
    assert (rec["nan"], rec["inf"], rec["nested"], rec["ok"]) == ("nan", "inf", ["-inf"], 0.5)


# --- each masking layer, tested on its own -----------------------------------


def _record(msg: Any, args: Any = None, name: str = "observatory.test", **extra: Any) -> logging.LogRecord:
    record = logging.LogRecord(name, logging.INFO, __file__, 1, msg, args, None)
    record.__dict__.update(extra)
    return record


def test_layer_render_message_scrubs_text() -> None:
    assert URL_PW not in _render_message(_record(f"to {DSN}"))
    assert SENTINEL not in _render_message(_record(f"token={SENTINEL}"))


def test_layer_render_message_redacts_args_structurally() -> None:
    # A list value is not fully caught by the text scrubber; only argument redaction catches it.
    assert SENTINEL not in _render_message(_record("cfg %s", ({"password": [SENTINEL, SENTINEL]},)))
    assert SENTINEL not in _render_message(_record("%(password)s", ({"password": SENTINEL},)))


def test_layer_render_message_redacts_mapping_message() -> None:
    assert SENTINEL not in _render_message(_record({"password": [SENTINEL, SENTINEL]}))


def test_layer_extras() -> None:
    extras = _extras(_record("m", **{"password": SENTINEL}, nested={"token": [SENTINEL]}, url=DSN))
    assert extras == {
        "password": REDACTED,
        "nested": {"token": REDACTED},
        "url": DSN.replace(f"app_user:{URL_PW}", REDACTED),
    }


@pytest.mark.parametrize("formatter", [JsonFormatter(), ConsoleFormatter()])
def test_layer_exception_text(formatter: JsonFormatter | ConsoleFormatter) -> None:
    record = _record("m")
    record.exc_text = f"Traceback: {DSN} token={SENTINEL}"
    record.stack_info = f"Stack: {DSN}"
    text = formatter._exception_text(record)
    assert text is not None
    assert URL_PW not in text
    assert SENTINEL not in text


@pytest.mark.parametrize("formatter", [JsonFormatter(), ConsoleFormatter()])
def test_layer_final_backstop(formatter: JsonFormatter | ConsoleFormatter) -> None:
    # Logger names reach the output without passing any inner layer: only the
    # formatter's final scrub protects them.
    out = formatter.format(_record("m", name=f"pool.{DSN}.token={SENTINEL}"))
    assert URL_PW not in out
    assert SENTINEL not in out


def test_layer_json_backstop_keeps_valid_json() -> None:
    out = JsonFormatter().format(_record('quote " and \\ backslash', name=f'pool."{DSN}"'))
    rec = json.loads(out)
    assert rec["msg"] == 'quote " and \\ backslash'
    assert URL_PW not in out


# --- console output ------------------------------------------------------------


def test_console_escapes_control_characters(
    make_settings: SettingsFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(make_settings(log_format="console"))
    forged = "ok\n2026-01-01T00:00:00.000Z CRITICAL observatory fake [-] forged"
    log.info("user input: %s", "ok\r\n2026-01-01T00:00:00.000Z CRITICAL observatory fake [-] forged\x1b[31m")
    log.info("extra", extra={"note": "a\nb"})
    try:
        raise ValueError("line one\nline two\rthree")
    except ValueError:
        log.exception("failed")
    out = capsys.readouterr().err
    lines = out.splitlines()
    assert "\r" not in out
    assert "\x1b" not in out
    assert not any(line.startswith("2026-01-01") for line in lines)
    assert "\\r\\n2026-01-01" in lines[0]
    assert "\\x1b[31m" in lines[0]
    assert "note='a\\nb'" in lines[1]  # repr of the extra; no raw newline
    assert all(line.startswith("  ") for line in lines[3:])  # traceback lines are indented
    assert forged not in out


# --- warnings and uncaught exceptions -------------------------------------------


def test_warnings_are_captured_and_scrubbed(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn(f"could not connect {DSN} token={SENTINEL}", UserWarning, stacklevel=1)
    out = capsys.readouterr().err
    assert URL_PW not in out
    assert SENTINEL not in out
    rec = _json_lines(out)[0]
    assert rec["logger"] == "py.warnings"
    assert "UserWarning: could not connect" in rec["msg"]


def _raise(exc: BaseException) -> tuple[type[BaseException], BaseException, Any]:
    try:
        raise exc
    except BaseException as caught:
        return type(caught), caught, caught.__traceback__


def test_sys_excepthook_logs_redacted(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    sys.excepthook(*_raise(RuntimeError(f"fatal {DSN} password={SENTINEL}")))
    out = capsys.readouterr().err
    assert URL_PW not in out
    assert SENTINEL not in out
    rec = _json_lines(out)[0]
    assert (rec["logger"], rec["level"], rec["msg"]) == (
        "observatory.uncaught",
        "CRITICAL",
        "uncaught exception",
    )
    assert "RuntimeError: fatal" in rec["exc_info"]


def test_sys_excepthook_leaves_keyboard_interrupt_to_default(
    json_logging: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[type[BaseException]] = []
    monkeypatch.setattr(sys, "__excepthook__", lambda t, e, tb: seen.append(t))
    sys.excepthook(*_raise(KeyboardInterrupt()))
    assert seen == [KeyboardInterrupt]
    assert capsys.readouterr().err == ""


def test_thread_excepthook_logs_redacted(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    def work() -> None:
        raise RuntimeError(f"worker failed {DSN}")

    worker = threading.Thread(target=work, name="worker-1")
    worker.start()
    worker.join()
    out = capsys.readouterr().err
    assert URL_PW not in out
    rec = _json_lines(out)[0]
    assert rec["msg"] == "uncaught exception in thread worker-1"
    assert "RuntimeError: worker failed" in rec["exc_info"]


def test_thread_excepthook_edge_cases(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    threading.excepthook(threading.ExceptHookArgs([SystemExit, SystemExit(), None, None]))
    assert capsys.readouterr().err == ""
    threading.excepthook(threading.ExceptHookArgs([RuntimeError, None, None, None]))
    rec = _json_lines(capsys.readouterr().err)[0]
    assert rec["msg"] == "uncaught exception in thread unknown"
    assert "exc_info" not in rec


def test_configure_logging_installs_hooks(make_settings: SettingsFactory) -> None:
    configure_logging(make_settings())
    assert sys.excepthook is not sys.__excepthook__
    assert threading.excepthook is not threading.__excepthook__


# --- long values, header lines, PEM, escaped quotes ---------------------------

_JWT = "eyJhbGciOiJSUzI1NiJ9." + "eyJzdWIiOiJ4In0" * 60 + "." + "S1gnatureTail" * 40  # ~1.5 KB


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer " + _JWT,
        "token=" + _JWT,
        "api_key: Bearer " + _JWT,
        "password='" + "y" * 300 + "S1gnatureTail'",
        '{"client_secret": "' + "z" * 2000 + 'S1gnatureTail"}',
        "postgresql://u:" + "p" * 1500 + "S1gnatureTail@db/x",
    ],
)
def test_long_secrets_are_redacted_entirely(text: str) -> None:
    out = scrub_text(text)
    assert "S1gnatureTail" not in out
    assert "eyJzdWIi" not in out
    assert REDACTED in out


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cookie: a=1; sid=s1d-value", f"Cookie: {REDACTED}"),
        ("Set-Cookie: session=s1d-value; Path=/; HttpOnly", f"Set-Cookie: {REDACTED}"),
        (
            "authorization: AWS4-HMAC-SHA256 Credential=x, Signature=s1g\nnext line",
            f"authorization: {REDACTED}\nnext line",
        ),
        ("{'cookie': 'a=1; sid=s1d'} rest", f"{{'cookie': '{REDACTED}'}} rest"),  # quoted: just the value
        ("api_key: Bearer abc.def x", f"api_key: {REDACTED} x"),
    ],
)
def test_header_line_values(text: str, expected: str) -> None:
    assert mask_key_values(text) == expected


@pytest.mark.parametrize("kind", ["", "RSA ", "EC ", "OPENSSH ", "ENCRYPTED "])
def test_pem_private_key_blocks(kind: str) -> None:
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\nS1gnatureTail+/=="
    text = f"key loaded: -----BEGIN {kind}PRIVATE KEY-----\n{body}\n-----END {kind}PRIVATE KEY----- done"
    assert scrub_text(text) == f"key loaded: {REDACTED} done"


def test_unterminated_pem_block_is_redacted_to_end() -> None:
    begin = "-----BEGIN " + "PRIVATE KEY-----"  # split so secret scanners do not flag this file
    assert scrub_text(f"x {begin}\nMIIEvS1gnatureTail") == f"x {REDACTED}"


def test_public_pem_is_kept() -> None:
    text = "-----BEGIN PUBLIC KEY-----\nMIIBIjAN\n-----END PUBLIC KEY-----"
    assert scrub_text(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"password": "ab\\"S1gnatureTail"}', f'{{"password": "{REDACTED}"}}'),
        ("password='it\\'s S1gnatureTail' next", f"password='{REDACTED}' next"),
    ],
)
def test_escaped_quotes_do_not_end_the_value(text: str, expected: str) -> None:
    assert mask_key_values(text) == expected


def test_list_pairs_are_redacted_like_tuples() -> None:
    assert redact({"h": [["authorization", "Bearer x"], ["accept", "json"]]}) == {
        "h": [["authorization", REDACTED], ["accept", "json"]]
    }
    assert redact([["token", SENTINEL]], stringify=False) == [["token", REDACTED]]
    assert redact([("token", SENTINEL)], stringify=False) == [("token", REDACTED)]


# --- performance: scrubbing must stay linear (it runs on the event loop) -------


def _elapsed(fn: Any, *args: Any) -> float:
    started = time.perf_counter()
    fn(*args)
    return time.perf_counter() - started


@pytest.mark.parametrize("text", ["a" * 1_000_000, "x-" * 500_000], ids=["a-1MB", "x-dash-1MB"])
def test_scrub_one_megabyte_token_is_fast(text: str) -> None:
    assert _elapsed(scrub_text, text) < 0.1


def test_access_log_line_with_64kb_path_is_fast() -> None:
    path = "/" + "a" * 65_536
    record = _record(
        '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:5000", "GET", path, "1.1", 404), name="uvicorn.access"
    )
    assert _elapsed(JsonFormatter().format, record) < 0.05


# --- unraisable exceptions --------------------------------------------------------


def _unraisable(exc: BaseException | None, obj: object, err_msg: str | None = None) -> Any:
    # sys.UnraisableHookArgs is not constructible at runtime; the hook only reads attributes.
    return types.SimpleNamespace(
        exc_type=type(exc) if exc is not None else None,
        exc_value=exc,
        exc_traceback=exc.__traceback__ if exc is not None else None,
        err_msg=err_msg,
        object=obj,
    )


def test_unraisablehook_logs_redacted(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    class Holder:
        def __repr__(self) -> str:
            return f"Holder({DSN})"

    _, exc, _ = _raise(RuntimeError(f"cleanup failed token={SENTINEL}"))
    sys.unraisablehook(_unraisable(exc, Holder()))
    out = capsys.readouterr().err
    assert URL_PW not in out
    assert SENTINEL not in out
    rec = _json_lines(out)[0]
    assert rec["logger"] == "observatory.uncaught"
    assert rec["msg"].startswith("Exception ignored in: Holder(postgresql+psycopg://[REDACTED]@")
    assert "RuntimeError: cleanup failed" in rec["exc_info"]


def test_unraisablehook_edge_cases(json_logging: None, capsys: pytest.CaptureFixture[str]) -> None:
    class BadRepr:
        def __repr__(self) -> str:
            raise ValueError("no repr")

    sys.unraisablehook(_unraisable(None, BadRepr(), "custom message"))
    sys.unraisablehook(_unraisable(None, None))
    first, second = _json_lines(capsys.readouterr().err)
    assert first["msg"] == "custom message: <unrepresentable object>"
    assert "exc_info" not in first
    assert second["msg"] == "Exception ignored in: unknown object"


def test_unraisablehook_is_installed(make_settings: SettingsFactory) -> None:
    configure_logging(make_settings())
    assert sys.unraisablehook is not sys.__unraisablehook__


# --- ADR-0008 C18: only an exact "[REDACTED]" is already redacted (R-A-P2-006-01) ------------------

_C18_SECRET = "hun" + "ter2" + "Xy9Q" + "zz"
_C18_CASES = [
    "password=" + REDACTED + _C18_SECRET,
    "password='" + REDACTED + _C18_SECRET + "'",
    'token: "' + REDACTED + " " + _C18_SECRET + '"',
    "api_key=" + REDACTED + "/" + _C18_SECRET + " tail",
    "Authorization: " + REDACTED + "%" + _C18_SECRET,
    "Cookie: " + REDACTED + "; sid=" + _C18_SECRET,
]


@pytest.mark.parametrize("text", _C18_CASES)
def test_a_value_that_only_starts_with_redacted_is_masked_whole(text: str) -> None:
    for out in (mask_key_values(text), scrub_text(text)):
        assert not {_C18_SECRET[i : i + 4] for i in range(len(_C18_SECRET) - 3)} & {
            out[i : i + 4] for i in range(len(out) - 3)
        }, out
        assert scrub_text(out) == out  # still idempotent


@pytest.mark.parametrize(
    "text",
    ["password=" + REDACTED, "password='" + REDACTED + "'", "token: " + REDACTED + ", x", "auth=[x]"],
)
def test_an_exact_redacted_value_is_left_alone(text: str) -> None:
    once = scrub_text(text)
    assert scrub_text(once) == once
    if REDACTED in text:
        assert once == text


def test_normalize_key_is_public() -> None:
    from observatory.core.logging import _normalize_key, normalize_key  # noqa: PLC0415

    assert normalize_key("Api-Key") == normalize_key("api_key") == "apikey"
    assert _normalize_key is normalize_key
