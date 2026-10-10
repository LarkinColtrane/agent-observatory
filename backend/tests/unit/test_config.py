"""Settings contract (ADR-0005 §3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from observatory.core.config import ConfigurationError, Settings, get_settings

# Synthetic values, assembled at runtime so no literal looks like a credential.
FAKE_DB = "postgresql+psycopg://app:" + "not-a-real-password" + "@db.invalid:5432/ao"
FAKE_REDIS = "redis://cache.invalid:6379/0"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("AO_ENV", "AO_DATABASE_URL", "AO_REDIS_URL", "AO_MIGRATION_DATABASE_URL", "AO_LOG_FORMAT"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


def test_env_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="env"):
        Settings()  # type: ignore[call-arg]


def test_defaults_and_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AO_ENV", "test")
    s = Settings()  # type: ignore[call-arg]
    assert (s.env, s.service_name, s.log_format, s.log_level) == ("test", "agent-observatory", "json", "INFO")
    assert s.database_url is None
    assert s.redis_url is None


def test_secrets_are_secretstr_and_never_rendered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AO_ENV", "dev")
    monkeypatch.setenv("AO_DATABASE_URL", FAKE_DB)
    s = Settings()  # type: ignore[call-arg]
    assert s.database_url is not None
    assert s.database_url.get_secret_value() == FAKE_DB
    for rendered in (str(s), repr(s), s.model_dump_json()):
        assert "not-a-real-password" not in rendered


# A SHORT secret-bearing URL: pydantic truncates long inputs in error text, which
# would hide a leak from the assertion (review P1A-08).
SHORT_PW = "Pw9" + "xQ7"
SHORT_DB = "postgresql://a:" + SHORT_PW + "@d/x"


@pytest.mark.parametrize(
    ("env", "extra"),
    [
        ({"AO_ENV": "prod", "AO_DATABASE_URL": SHORT_DB}, "missing redis"),
        ({"AO_ENV": "staging", "AO_DATABASE_URL": SHORT_DB}, "invalid env"),
        ({"AO_ENV": "test", "AO_DATABASE_URL": SHORT_DB, "AO_LOG_FORMAT": "xml"}, "invalid field"),
    ],
)
def test_validation_errors_never_echo_input_values(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], extra: str
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # Direct construction: the rendered error must not echo inputs.
    with pytest.raises(ValidationError) as direct:
        Settings()  # type: ignore[call-arg]
    for rendered in (str(direct.value), repr(direct.value)):
        assert SHORT_PW not in rendered, extra
    # Supported entry point: a sanitized error with no reference to raw inputs at all
    # (pydantic's errors() always includes them, so the original is not retained).
    with pytest.raises(ConfigurationError) as sanitized:
        get_settings()
    err = sanitized.value
    assert err.__cause__ is None
    assert err.__context__ is None
    for rendered in (str(err), repr(err), repr(err.args)):
        assert SHORT_PW not in rendered, extra


@pytest.mark.parametrize("missing", ["AO_DATABASE_URL", "AO_REDIS_URL"])
def test_prod_requires_backing_services_without_leaking(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv("AO_ENV", "prod")
    monkeypatch.setenv("AO_DATABASE_URL", FAKE_DB)
    monkeypatch.setenv("AO_REDIS_URL", FAKE_REDIS)
    monkeypatch.delenv(missing)
    with pytest.raises(ValidationError) as excinfo:
        Settings()  # type: ignore[call-arg]
    assert missing in str(excinfo.value)
    assert "not-a-real-password" not in str(excinfo.value)


def test_prod_ok_with_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AO_ENV", "prod")
    monkeypatch.setenv("AO_DATABASE_URL", FAKE_DB)
    monkeypatch.setenv("AO_REDIS_URL", FAKE_REDIS)
    assert Settings().env == "prod"  # type: ignore[call-arg]


def test_invalid_values_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in (("AO_ENV", "staging"), ("AO_LOG_FORMAT", "xml")):
        monkeypatch.setenv("AO_ENV", "test")
        monkeypatch.setenv(key, value)
        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]
        monkeypatch.delenv(key)


def test_settings_are_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AO_ENV", "test")
    s = Settings()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        s.env = "prod"  # type: ignore[misc]


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AO_ENV", "test")
    assert get_settings() is get_settings()
