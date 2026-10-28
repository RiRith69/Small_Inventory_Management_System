"""Application configuration.

All secrets and environment-specific values are read from environment variables
(loaded from the repository-root ``.env`` in development).  Nothing secret is
ever hardcoded here.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# repository root = <root>/backend/app/core/config.py -> parents[3]
ROOT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- General ----
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    timezone: str = Field(default="Asia/Phnom_Penh")
    project_name: str = "Warehouse Roll Inventory"

    # ---- Database ----
    database_url: str = Field(default="postgresql+psycopg://warehouse:REPLACE_WITH_RANDOM_DATABASE_PASSWORD@127.0.0.1:5433/warehouse_inventory")
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ---- Security / sessions ----
    secret_key: str = Field(default="change-me-in-production")
    session_cookie_name: str = Field(default="warehouse_session")
    session_ttl_days: int = 30
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cookie_domain: str | None = None

    # ---- CORS / URLs ----
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    public_web_url: str = "http://localhost:5173"

    # ---- Telegram ----
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_link_ttl_minutes: int = 10
    telegram_link_max_attempts: int = 5
    telegram_link_window_minutes: int = 15
    # Shared secret the bot uses to authenticate against the internal bot API.
    bot_api_token: str = ""

    # ---- Rate limiting ----
    login_max_attempts: int = 5
    login_window_minutes: int = 15

    # ---- Bootstrap admin (used only by the create-admin CLI) ----
    admin_username: str = "admin"
    admin_password: str = "Admin@Rith"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        allowed = {"development", "dev", "production", "prod", "test"}
        if v.lower() not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}")
        return v

    @field_validator("session_ttl_days")
    @classmethod
    def _validate_session_ttl(cls, value: int) -> int:
        if not 1 <= value <= 90:
            raise ValueError("SESSION_TTL_DAYS must be between 1 and 90")
        return value

    def validate_for_startup(self) -> list[str]:
        """Return a list of human-readable warnings for unsafe production config."""
        warnings: list[str] = []
        if self.is_production:
            if "REPLACE_WITH_" in self.database_url:
                warnings.append("DATABASE_URL must use the configured production credentials")
            if self.secret_key in {"", "change-me-in-production", "REPLACE_WITH_RANDOM_SECRET"}:
                warnings.append("SECRET_KEY must be set to a random value in production")
            if self.bot_api_token in {
                "",
                "change-me-bot-token",
                "REPLACE_WITH_RANDOM_BOT_TOKEN",
            }:
                warnings.append("BOT_API_TOKEN must be set to a random value in production")
            if not self.cookie_secure:
                warnings.append("COOKIE_SECURE should be true in production")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Make sure ``os.environ`` reflects settings for libraries that read it directly.
os.environ.setdefault("TZ", settings.timezone)
