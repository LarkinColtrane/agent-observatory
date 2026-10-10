"""Application settings (ADR-0005 §3).

Configuration comes only from the environment (prefix ``AO_``). Secret values
are ``SecretStr`` and are read with ``get_secret_value()`` at the point of
use; they are never logged, returned, or put into exception messages.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(ValueError):
    """Invalid configuration. Carries field names and messages only — never input values."""


class Settings(BaseSettings):
    """Process configuration. ``env`` is required so no deployment silently runs as ``dev``."""

    # hide_input_in_errors: a ValidationError must never echo input values (they may
    # contain credentials) — review P1A-08.
    model_config = SettingsConfigDict(
        env_prefix="AO_", extra="ignore", frozen=True, hide_input_in_errors=True
    )

    env: Literal["dev", "test", "prod"]
    service_name: str = "agent-observatory"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    git_sha: str | None = None

    @model_validator(mode="after")
    def _prod_requires_backing_services(self) -> Self:
        if self.env == "prod":
            missing = [n for n in ("database_url", "redis_url") if getattr(self, n) is None]
            if missing:
                # Names only — never values.
                raise ValueError(f"env=prod requires: {', '.join('AO_' + m.upper() for m in missing)}")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once from the environment.

    Raises ``ConfigurationError`` built from field locations and messages only.
    pydantic's ``ValidationError.errors()`` always contains raw inputs (which may
    be credentials), so the original error is not chained or retained.
    """
    problems: list[str] = []
    try:
        return Settings()  # values come from the environment (AO_*)
    except ValidationError as exc:
        for err in exc.errors(include_input=False, include_context=False, include_url=False):
            where = ".".join(str(part) for part in err["loc"]) or "settings"
            problems.append(f"{where}: {err['msg']}")
    # Raised outside the except block: no __context__ reference to the ValidationError.
    raise ConfigurationError("invalid configuration: " + "; ".join(problems))
