"""Authentication schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import UserRole
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TelegramStatus(BaseModel):
    is_linked: bool
    bot_username: str | None = None
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    linked_at: datetime | None = None
    history: list[dict] = []


class CurrentUser(ORMModel):
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    permissions: dict[str, bool] = {}
    telegram: TelegramStatus | None = None
    csrf_token: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)
