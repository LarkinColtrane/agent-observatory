"""Structured logging with mandatory redaction (ADR-0005 §3).

Every record emitted through the handler installed by ``configure_logging``:

- carries the current request ID (``request_id_var``, ``None`` outside a request);
- has the value of every secret-named key replaced by ``"[REDACTED]"``, recursively
  through nested mappings and sequences (including ``(key, value)`` pairs such as
  header lists) in the message, its arguments and extra fields;
- has every string passed through ``scrub_text``: credentials embedded in URLs
  (``scheme://<user>:<password>@host``) are masked, and so are the values of
  secret-named keys written as text (``token=x``, ``password: x``,
  ``'api_key': 'x'``, ``password='x'``), in the message, extras and the
  formatted exception/traceback.

Each formatter finally scrubs its whole output once more (JSON: every key and
string of the payload; console: the full text, with control characters
escaped) as a backstop for anything rendered outside the layers above.
Text masking is pattern-based and best-effort: secrets must still never be
logged on purpose.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import re
import sys
import threading
from collections.abc import Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import lru_cache
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # annotation only: Settings is built solely by get_settings()
    from observatory.core.config import Settings  # noqa: TID251 (type only; never constructed)

REDACTED: Final = "[REDACTED]"

#: ADR-0005 §3 minimum: a key is secret if its name *contains* any of these.
SECRET_KEY_PARTS: Final[tuple[str, ...]] = (
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
#: Secret only on an exact (normalized) match: as a substring "auth" would hit "author".
SECRET_EXACT_KEYS: Final[frozenset[str]] = frozenset({"auth"})

#: Request ID of the request being served, set by the API middleware.
request_id_var: ContextVar[str | None] = ContextVar("observatory_request_id", default=None)


def _normalize_key(key: str) -> str:
    # "Api-Key", "api_key", "apiKey" and "APIKEY" all become "apikey".
    return key.lower().replace("-", "").replace("_", "")


_NORMALIZED_PARTS: Final = tuple(sorted({_normalize_key(p) for p in SECRET_KEY_PARTS}))

# Every pattern below is anchored and possessive, so scrubbing is linear in the
# input length (no per-position retries, no backtracking).
#
# A URL is matched as the whole whitespace-free token after "://"; its userinfo
# runs to the token's last "@" (a password may contain unencoded "/", "@", "?" or
# "#"). An "@" later in a path or query is over-masked, which is safe.
_URL_TOKEN: Final = re.compile(r"://\S++")
# PEM private-key blocks, to the END line or, if that is missing, to the end of text.
_PEM_PRIVATE_KEY: Final = re.compile(
    r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----"
    r"(?:(?!-----END)[\s\S])*+"
    r"(?:-----END [A-Z ]{0,40}PRIVATE KEY-----)?"
)
# A key at a token start, followed by ":" or "=", optionally quoted ('key': / "key"=).
_KEY: Final = re.compile(r"""(?<![A-Za-z0-9_.-])(?P<key>[A-Za-z0-9_.-]++)['"]?\s{0,3}[:=]\s{0,3}""")
# The value after a secret key, matched only once the key is known to be secret.
# Unbounded: a long token or signature must not leak its tail.
_VALUE: Final = re.compile(
    r"""'(?:[^'\\\n]|\\.)*+'?|"(?:[^"\\\n]|\\.)*+"?"""
    r"""|(?i:(?:bearer|basic|token|digest)\s{1,3})?[^\s&,;'")\]}>]++"""
)
# Header values made of several pairs (Cookie: a=1; sid=x) are redacted to end of line.
_LINE_VALUE: Final = re.compile(r"[^\n]++")
_LINE_VALUE_KEYS: Final = ("cookie", "authorization")
_CONTROL_CHARS: Final = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_MAX_DEPTH: Final = 12
_TRUNCATED: Final = "[TRUNCATED]"

# Attributes every LogRecord has; anything else on a record is an "extra" field.
_RECORD_ATTRS: Final = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
# Set by uvicorn for its own colouring; a duplicate of the message.
_IGNORED_EXTRAS: Final = frozenset({"color_message"})
_HANDLER_MARK: Final = "_observatory_handler"
_FRAMEWORK_LOGGERS: Final = ("uvicorn", "uvicorn.error", "uvicorn.access")


def is_secret_key(key: object) -> bool:
    """True if ``key`` names a secret (substring match ignoring case, ``-`` and ``_``)."""
    return _is_secret_name(key.decode("latin-1") if isinstance(key, bytes) else str(key))


@lru_cache(maxsize=4096)  # log text repeats the same few key names
def _is_secret_name(name: str) -> bool:
    normalized = _normalize_key(name)
    return normalized in SECRET_EXACT_KEYS or any(part in normalized for part in _NORMALIZED_PARTS)


def _mask_url_token(match: re.Match[str]) -> str:
    token = match.group()
    at = token.rfind("@")
    return token if at < 0 else f"://{REDACTED}{token[at:]}"


def mask_url_credentials(text: str) -> str:
    """Replace the userinfo of every URL in ``text`` with ``[REDACTED]``."""
    return _URL_TOKEN.sub(_mask_url_token, text)


def mask_key_values(text: str) -> str:
    """Replace the value of every secret-named ``key=value`` / ``key: value`` pair in ``text``."""
    out: list[str] = []
    pos = 0
    for match in _KEY.finditer(text):
        start = match.end()
        if match.start() < pos or not is_secret_key(match["key"]):
            continue  # inside a value already redacted, or not a secret
        quote = text[start] if text[start : start + 1] in ("'", '"') else ""
        if text.startswith(REDACTED, start + len(quote)):
            continue  # already redacted (scrubbing is idempotent)
        whole_line = not quote and any(k in _normalize_key(match["key"]) for k in _LINE_VALUE_KEYS)
        value = (_LINE_VALUE if whole_line else _VALUE).match(text, start)
        if value is None:
            continue  # no value (e.g. "password:" at end of line)
        out.append(text[pos:start] + quote + REDACTED + quote)
        pos = value.end()
    out.append(text[pos:])
    return "".join(out)


def scrub_text(text: str) -> str:
    """Apply every text mask: PEM private keys, URL credentials, secret-named key/value pairs."""
    return mask_key_values(mask_url_credentials(_PEM_PRIVATE_KEY.sub(REDACTED, text)))


def redact(value: Any, *, stringify: bool = True, _depth: int = 0) -> Any:
    """Return a redacted copy of ``value`` (the input is never mutated).

    Mapping values under secret-named keys, and the second element of
    ``(secret_key, value)`` pairs in sequences, become ``[REDACTED]``; mappings
    and sequences are walked recursively; strings and keys go through
    ``scrub_text``. With ``stringify`` (JSON output) other objects are rendered
    with ``str()`` and scrubbed and non-finite floats become strings; without it
    (``%``-format arguments) they are returned unchanged, to be scrubbed after
    formatting.
    """
    if _depth > _MAX_DEPTH:
        return _TRUNCATED
    if isinstance(value, str):
        return scrub_text(value)
    deeper = _depth + 1
    if isinstance(value, Mapping):
        return {
            scrub_text(str(k)): (
                REDACTED if is_secret_key(k) else redact(v, stringify=stringify, _depth=deeper)
            )
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        items = [_redact_item(v, stringify, deeper) for v in value]
        return tuple(items) if not stringify and isinstance(value, tuple) else items
    if value is None or isinstance(value, bool | int | float):
        return _redact_number(value, stringify)
    return scrub_text(str(value)) if stringify else value


def _redact_number(value: float | None, stringify: bool) -> Any:
    if isinstance(value, float) and stringify and not math.isfinite(value):
        return str(value)  # JSON has no NaN/Infinity
    return value


def _redact_item(item: Any, stringify: bool, depth: int) -> Any:
    """Redact a sequence element; a ``(secret_key, value)`` pair (e.g. a header) keeps only its key."""
    is_pair = isinstance(item, tuple | list) and len(item) == 2 and isinstance(item[0], str | bytes)
    if is_pair and is_secret_key(item[0]):
        pair = [redact(item[0], stringify=stringify, _depth=depth), REDACTED]
        return pair if stringify or isinstance(item, list) else tuple(pair)
    return redact(item, stringify=stringify, _depth=depth)


def _render_message(record: logging.LogRecord) -> str:
    msg: Any = record.msg
    text = msg if isinstance(msg, str) else str(redact(msg))
    if record.args:
        args: Any = record.args
        safe_args = (
            redact(args, stringify=False)
            if isinstance(args, Mapping)
            else tuple(redact(a, stringify=False) for a in args)
        )
        try:
            text = text % safe_args
        except (TypeError, ValueError, KeyError):
            # Never fall back to logging.Handler.handleError: it prints raw args.
            text = f"{text} [log arguments could not be formatted]"
    return scrub_text(text)


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    extras = {
        k: v
        for k, v in record.__dict__.items()
        if k not in _RECORD_ATTRS and k not in _IGNORED_EXTRAS and k != "request_id"
    }
    redacted: dict[str, Any] = redact(extras)
    return redacted


def _escape_controls(text: str) -> str:
    """Escape control characters (CR, LF, ESC, ...) so one record cannot forge another."""
    return _CONTROL_CHARS.sub(lambda m: m.group().encode("unicode_escape").decode("ascii"), text)


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to every record (``None`` outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            record.request_id = request_id_var.get()
        return True


class _RedactingFormatter(logging.Formatter):
    def _exception_text(self, record: logging.LogRecord) -> str | None:
        parts: list[str] = []
        if record.exc_info:
            parts.append(self.formatException(record.exc_info))
        elif record.exc_text:
            parts.append(record.exc_text)
        if record.stack_info:
            parts.append(self.formatStack(record.stack_info))
        return scrub_text("\n".join(parts)) if parts else None

    @staticmethod
    def _timestamp(record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        return ts.replace("+00:00", "Z")

    @staticmethod
    def _request_id(record: logging.LogRecord) -> str | None:
        rid = getattr(record, "request_id", None)
        return str(rid) if rid is not None else request_id_var.get()


class JsonFormatter(_RedactingFormatter):
    """One JSON object per line: ``ts``, ``level``, ``logger``, ``msg``, ``request_id``, extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self._timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": _render_message(record),
            "request_id": self._request_id(record),
        }
        for key, value in _extras(record).items():
            payload.setdefault(key, value)  # core fields are never overridden
        exc = self._exception_text(record)
        if exc is not None:
            payload["exc_info"] = exc
        # Backstop: every key and string scrubbed once more; the output stays valid JSON.
        return json.dumps(redact(payload), default=str, allow_nan=False)


class ConsoleFormatter(_RedactingFormatter):
    """Human-readable record (development); one line plus an indented traceback."""

    def format(self, record: logging.LogRecord) -> str:
        line = (
            f"{self._timestamp(record)} {record.levelname:<8} {record.name} "
            f"[{self._request_id(record) or '-'}] {_render_message(record)}"
        )
        extras = _extras(record)
        if extras:
            line += " " + " ".join(f"{k}={v!r}" for k, v in extras.items())
        # Backstop scrub, then escape control characters (CR/LF included).
        text = _escape_controls(scrub_text(line))
        exc = self._exception_text(record)
        if exc is not None:
            text += "".join("\n  " + _escape_controls(ln) for ln in scrub_text(exc).split("\n"))
        return text


class _StderrHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Writes to the *current* ``sys.stderr`` and never echoes record data on failure."""

    def __init__(self) -> None:
        super().__init__(sys.stderr)

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr  # follow redirection (e.g. test capture, daemonisation)
        super().emit(record)

    def handleError(self, record: logging.LogRecord) -> None:
        # logging.Handler.handleError prints the record's raw msg and args, which
        # would bypass redaction. Report only that a failure happened.
        if logging.raiseExceptions:
            err_type = sys.exc_info()[0]
            name = err_type.__name__ if err_type is not None else "unknown error"
            with contextlib.suppress(Exception):  # nothing else can be done if stderr fails
                sys.stderr.write(f"--- logging error ({name}) in {record.name!r}; details suppressed ---\n")


_uncaught = logging.getLogger("observatory.uncaught")


def _log_uncaught(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    """``sys.excepthook``: uncaught exceptions are logged (redacted), not printed raw."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    _uncaught.critical("uncaught exception", exc_info=(exc_type, exc, tb))


def _log_uncaught_in_thread(args: threading.ExceptHookArgs) -> None:
    """``threading.excepthook``: as ``_log_uncaught``; ``SystemExit`` is ignored like the default."""
    if issubclass(args.exc_type, SystemExit):
        return
    name = args.thread.name if args.thread is not None else "unknown"
    if args.exc_value is None:
        _uncaught.error("uncaught exception in thread %s", name)
    else:
        exc_info = (args.exc_type, args.exc_value, args.exc_traceback)
        _uncaught.error("uncaught exception in thread %s", name, exc_info=exc_info)


def _log_unraisable(unraisable: sys.UnraisableHookArgs) -> None:
    """``sys.unraisablehook`` (e.g. an exception in ``__del__``): logged, redacted."""
    try:
        where = repr(unraisable.object) if unraisable.object is not None else "unknown object"
    except Exception:
        where = "<unrepresentable object>"
    exc_info = (
        (unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback)
        if unraisable.exc_value is not None
        else None
    )
    _uncaught.error("%s: %s", unraisable.err_msg or "Exception ignored in", where, exc_info=exc_info)


def _level(name: str) -> int:
    level = logging.getLevelNamesMapping().get(name.strip().upper())
    if level is None:
        raise ValueError(f"unknown log level: {name!r}")
    return level


def configure_logging(settings: Settings) -> None:
    """Route all logging, warnings and uncaught exceptions through one redacting handler.

    Replaces any handlers on the root logger (a foreign handler would bypass
    redaction), makes uvicorn's loggers propagate to it, captures ``warnings``
    and installs ``sys.excepthook``, ``threading.excepthook`` and ``sys.unraisablehook``. Idempotent.
    """
    level = _level(settings.log_level)
    handler = _StderrHandler()
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())
    handler.addFilter(RequestIdFilter())
    setattr(handler, _HANDLER_MARK, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        if getattr(existing, _HANDLER_MARK, False):
            existing.close()
    root.addHandler(handler)
    root.setLevel(level)

    for name in _FRAMEWORK_LOGGERS:
        framework_logger = logging.getLogger(name)
        framework_logger.handlers.clear()
        framework_logger.propagate = True

    logging.captureWarnings(True)
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_in_thread
    sys.unraisablehook = _log_unraisable
