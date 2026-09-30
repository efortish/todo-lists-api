"""Runtime configuration, read from environment variables (and ``.env`` if present)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        "sqlite:///./todo.db",
        description="SQLAlchemy URL. Docker uses PostgreSQL; the default lets you run locally "
        "without any server.",
    )
    # No default on purpose: a secret committed to the repo is a secret anyone can use to
    # forge tokens. `make env` generates a random one.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(60, gt=0, le=24 * 60)
    auth_rate_limit_per_minute: int = Field(
        10, gt=0, description="Requests per minute and client IP on each auth endpoint."
    )
    max_request_body_bytes: int = Field(1024 * 1024, gt=0)
    log_level: str = "INFO"

    @property
    def docs_enabled(self) -> bool:
        """Swagger/ReDoc/OpenAPI are only served outside production."""
        return self.app_env != "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()
