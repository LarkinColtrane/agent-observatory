"""Regression tests for the AO-P2-006 review findings and ADR-0008 amendments C14-C24.

All secrets are synthetic and built by concatenation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
from contextvars import copy_context
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from observatory.events import (
    Accepted,
    Disposition,
    Event,
    RecordedEvent,
    RejectCode,
    WarningCode,
    content_fingerprint,
    load_recorded,
    parse_event,
    sanitize_text,
    validate_event,
)
from observatory.events import envelope as envelope_module
from observatory.events import text as text_module
from observatory.events.envelope import event_tree
from observatory.events.text import RULES_V1, check_unicode_data
from observatory.events.tree import canonical_text
from tests.unit.events.factory import DELETE, accept, raw, reject, tree

R = "[" + "REDACTED" + "]"
PW = "hun" + "ter2" + "Xy9Q" + "zz"
AWS = "AK" + "IA" + "ABCDEFGHIJ012345"


def _message(text: str) -> dict[str, Any]:
    payload = {"error_code": "e1", "severity": "error", "message": text}
    return tree(("event_type", "error.reported"), ("payload", payload))


def _windows(secret: str) -> set[str]:
    return {secret[i : i + 4] for i in range(len(secret) - 3)}


def _assert_no_residue(out: str, secret: str) -> None:
    survivors = {w for w in _windows(secret) if w in out}
    assert not survivors, (out, survivors)


# --- C18: only an exact [REDACTED] counts as already redacted -------------------------------------

REDACTED_PREFIX = {
    "key/value": "password=" + R + PW,
    "quoted key/value": "password='" + R + PW + "'",
    "option": "--password " + R + PW,
    "attached option": "--api-key=" + R + PW,
    "set": "set password " + R + PW,
    "-u": "-u " + R + "bob:" + PW,
    "mysql": "mysql -p" + R + PW,
    "pwd key": "MYSQL_PWD=" + R + PW,
}


@pytest.mark.parametrize("name", REDACTED_PREFIX)
def test_a_value_starting_with_redacted_is_still_a_hit(name: str) -> None:
    text = REDACTED_PREFIX[name]
    rejected = reject(_message(text))
    assert (rejected.code, rejected.disposition, rejected.raw_sha256) == (
        RejectCode.SECRET_DETECTED,
        Disposition.DROP,
        None,
    )
    out = sanitize_text(text)
    _assert_no_residue(out, PW)
    assert isinstance(validate_event(_message(out)), Accepted)


@pytest.mark.parametrize(
    "text",
    ["password=" + R, "password='" + R + "'", "--password " + R, "-u " + R, "mysql -p" + R, "set token " + R],
)
def test_an_exact_redacted_value_is_left_alone(text: str) -> None:
    assert sanitize_text(text) == text
    assert isinstance(validate_event(_message(text)), Accepted)


def test_partial_credential_masks_mask_the_whole_value() -> None:
    for text in (
        "token=" + AWS + "/" + PW,
        "Authorization: Bearer " + "q" * 20 + "%" + PW,
        "--api-key " + AWS + PW,
    ):
        out = sanitize_text(text)
        _assert_no_residue(out, PW)
        _assert_no_residue(out, AWS)
        assert isinstance(validate_event(_message(out)), Accepted), out


# --- C19: quoted values run to the matching unescaped quote -----------------------------------------

QUOTED = {
    "option single": ("--password 'correct horse " + PW + "'", "--password " + R),
    "option double": ('--password "correct horse ' + PW + '"', "--password " + R),
    "mysql attached": ('mysql -p"x y ' + PW + '"', "mysql -p" + R),
    "-u quoted": ("curl -u 'bob:x y " + PW + "' https://h", "curl -u " + R + " https://h"),
    "key/value": ("password='a b " + PW + "' tail", "password=" + R + " tail"),
    "escaped quote": ("password='a \\' b " + PW + "' tail", "password=" + R + " tail"),
    "unterminated": ("password='a b " + PW, "password=" + R),
}


@pytest.mark.parametrize("name", QUOTED)
def test_quoted_values_are_masked_whole(name: str) -> None:
    text, expected = QUOTED[name]
    assert sanitize_text(text) == expected
    assert reject(_message(text)).code is RejectCode.SECRET_DETECTED


# --- C20: CLI coverage ----------------------------------------------------------------------------------

CLI_HITS = [
    "docker exec -it db mysql -uroot -p" + PW,
    "docker compose exec db mysql -p" + PW + " app",
    "kubectl exec db-0 -- mysql -p" + PW,
    "cd app && mysql -p" + PW,
    "true || mysql -p" + PW,
    "echo x | mysql -p" + PW,
    "ls;mysql -p" + PW,
    "timeout 5 mysql -p" + PW,
    "sudo -Eu root mysql -p" + PW,
    "env -iu X mysql -p" + PW,
    "curl -Eu bob:" + PW + " https://h",
    "sshpass -p " + PW + " ssh host",
    "sshpass -p" + PW + " ssh host",
    "redis-cli -a " + PW + " ping",
    "redis-cli -a" + PW + " ping",
    "redis-cli --pass " + PW,
    "openssl pkcs12 -passin pass:" + PW + " -in x.p12",
    "openssl enc -passout pass:" + PW,
    "MYSQL_PWD=" + PW + " mysql -uroot",
    "db_pwd: " + PW,
    "password => " + PW,
    "'password' => '" + PW + "'",
    "password    =    " + PW,
    "password\t:\t" + PW,
]


@pytest.mark.parametrize("text", CLI_HITS)
def test_cli_coverage(text: str) -> None:
    assert RULES_V1.string_hit(text, text_tier=True)
    _assert_no_residue(sanitize_text(text), PW)


@pytest.mark.parametrize(
    "text",
    [
        "redis-cli ping",
        "sshpass -h",
        "openssl -passin env:VAR",
        "docker exec db psql -p 5432",
        "pip install -pkg",
    ],
)
def test_cli_rules_need_their_tool(text: str) -> None:
    assert not RULES_V1.string_hit(text, text_tier=True)


# --- C21: the stripped form is scanned too ------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "pass" + chr(0x200B) + "word=" + PW,
        "s" + chr(0x00AD) + "k-" + "synthetic" + "0" * 20,
        "password:" + "\n" * 4 + PW,
    ],
)
def test_forbidden_characters_cannot_hide_a_secret(text: str) -> None:
    for rejected in (reject(_message(text)), reject(tree(("scope.zz", text)))):
        assert (rejected.code, rejected.disposition, rejected.raw_sha256) == (
            RejectCode.SECRET_DETECTED,
            Disposition.DROP,
            None,
        )
    assert reject(tree(("extensions", {"x-acme": {"a" + chr(0x200B) + "pass" + "word": 1}}))).code is (
        RejectCode.SECRET_DETECTED
    )


# --- C22: acceptance paths -------------------------------------------------------------------------------


def test_json_and_string_validation_are_refused() -> None:
    body = raw(tree())
    for call in (
        lambda: Event.model_validate_json(body),
        lambda: Event.model_validate_strings(tree()),
        lambda: RecordedEvent.model_validate_json(b"{}"),
        lambda: RecordedEvent.model_validate_strings({}),
    ):
        with pytest.raises(TypeError, match=r"parse_event|load_recorded"):
            call()


@pytest.mark.parametrize(
    "change",
    [("source.seq", "0"), ("source.seq", True), ("source.seq", 0.0), ("scope.session_id", 5)],
    ids=["string seq", "bool seq", "float seq", "int id"],
)
def test_envelope_is_strict_whatever_the_caller_asks(change: tuple[str, object]) -> None:
    data = tree(change)
    rejected = "schema_violation|invalid_json"  # a float is not even a JSON-tree type here
    with pytest.raises(ValidationError, match=rejected):
        Event.model_validate(data, strict=False)
    with pytest.raises(ValidationError, match=rejected):
        TypeAdapter(Event).validate_python(data, strict=False)


def test_recorded_rows_are_strict_too() -> None:
    event = accept(tree()).event
    row = {
        "event": event_tree(event),
        "fingerprint": accept(tree()).fingerprint,
        "ingested_at": "2026-03-01T10:00:02Z",
        "ingest_seq": "3",
        "secret_rules_version": 1,
    }
    with pytest.raises(ValueError, match="recorded event"):
        load_recorded(row)
    with pytest.raises(ValidationError):
        RecordedEvent.model_validate(row, strict=False)


# --- C23: only load_recorded names an older rules version ---------------------------------------------

MARKER = "zz-v2-" + "marker"


@pytest.fixture
def rules_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    v1 = text_module.RULES_V1
    v2 = dataclasses.replace(v1, version=2, credential=(*v1.credential, lambda s: s.replace(MARKER, R)))
    monkeypatch.setattr(text_module, "SECRET_RULES", text_module._Rules({1: v1, 2: v2}))
    monkeypatch.setattr(text_module, "SECRET_RULES_VERSION", 2)


@pytest.mark.usefixtures("rules_v2")
def test_no_public_route_stamps_a_new_event_with_older_rules() -> None:
    new = tree(("scope.task_id", MARKER))
    assert not hasattr(envelope_module, "recorded_rules")
    forged_overrides: list[object] = [1, (object(), 1), ("token", 1), (None, 1)]
    for override in forged_overrides:

        def attempt(value: object = override) -> object:
            envelope_module._RECORDED_RULES.set(value)
            return Event.model_validate(new)

        with pytest.raises(ValidationError, match="secret_detected"):
            copy_context().run(attempt)
    assert validate_event(new).code is RejectCode.SECRET_DETECTED  # type: ignore[union-attr]


# --- C24: process-local events and the Unicode pin -----------------------------------------------------


def test_unicode_data_mismatch_fails_closed() -> None:
    check_unicode_data("15.0.0")
    with pytest.raises(ImportError, match=r"15\.0\.0"):
        check_unicode_data("15.1.0")
    code = "import unicodedata; unicodedata.unidata_version = '99.0.0'; import observatory.events"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode != 0
    assert "ImportError" in result.stderr


def test_envelope_documents_process_local_events() -> None:
    doc = envelope_module.__doc__ or ""
    assert "process" in doc
    assert "canonical bytes" in doc


# --- C14 and C15 -------------------------------------------------------------------------------------------


def test_c14_content_fingerprint_keeps_an_empty_time_object() -> None:
    event = accept(tree(("time.occurred_at", DELETE))).event
    digest_input = json.loads(canonical_text(event_tree(event)))
    del digest_input["time"]["observed_at"]
    for name in ("adapter", "stream_id", "seq"):
        del digest_input["source"][name]
    text = canonical_text(digest_input)
    assert '"time":{}' in text
    assert content_fingerprint(event) == "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_c15_core_family_vendor_is_a_schema_violation() -> None:
    rejected = reject(tree(("event_type", "x-task.created"), ("payload", {"a": 1})))
    assert (rejected.code, rejected.pointer, rejected.disposition) == (
        RejectCode.SCHEMA_VIOLATION,
        "/event_type",
        Disposition.QUARANTINE,
    )


# --- R-B-P2-006-06: surviving mutants ----------------------------------------------------------------------


@pytest.mark.parametrize("unit", ["agent", "session"])
def test_delta_usage_with_an_unequal_unit_id(unit: str) -> None:
    payload = {"usage": {"input_tokens": 1}, "accounting": "delta", "unit": unit, "unit_id": "someone-else"}
    rejected = reject(tree(("event_type", "usage.recorded"), ("payload", payload)))
    assert (rejected.code, rejected.pointer) == (RejectCode.SCHEMA_VIOLATION, "/payload/unit_id")


def test_late_observation_boundary_is_strict() -> None:
    exactly = accept(
        tree(("time.occurred_at", "2026-01-30T10:00:01Z"), ("time.observed_at", "2026-03-01T10:00:01Z"))
    )
    assert exactly.warnings == ()
    late = accept(
        tree(
            ("time.occurred_at", "2026-01-30T10:00:00.999999Z"), ("time.observed_at", "2026-03-01T10:00:01Z")
        )
    )
    assert late.warnings == (WarningCode.LATE_OBSERVATION,)


def test_array_indices_compare_numerically() -> None:
    depends = [f"t-{i:02d}" for i in range(12)]
    depends[2] = depends[10] = "a b"  # two bad items; the reported one is index 2, not "10"
    rejected = reject(
        tree(("event_type", "task.created"), ("payload", {"task_id": "t-x", "depends_on": depends}))
    )
    assert rejected.pointer == "/payload/depends_on/2"


def test_parse_event_is_the_json_acceptance_path() -> None:
    assert isinstance(parse_event(raw(tree())), Accepted)
