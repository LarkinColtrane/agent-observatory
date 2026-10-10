"""Application settings (ADR-0005 §3).

Configuration comes only from the environment (prefix ``AO_``). Secret values
are ``SecretStr`` and are read with ``get_secret_value()`` at the point of
use; they are never logged, returned, or put into exception messages.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration. ``env`` is required so no deployment silently runs as ``dev``."""

    model_config = SettingsConfigDict(env_prefix="AO_", extra="ignore", frozen=True)

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
    """Return the process-wide settings, loaded once from the environment."""
    return Settings()  # values come from the environment (AO_*)
