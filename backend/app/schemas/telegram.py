"""Telegram linking schemas (website side)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.auth import TelegramStatus


class TelegramLinkStartOut(BaseModel):
    token: str
    deep_link: str
    expires_at: datetime
    ttl_minutes: int
    bot_username: str | None = None
    instructions_en: str
    instructions_km: str


class TelegramUnlinkOut(BaseModel):
    revoked: int
    status: TelegramStatus
