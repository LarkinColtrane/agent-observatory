"""Settings contract (ADR-0005 §3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from observatory.core.config import Settings, get_settings

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
