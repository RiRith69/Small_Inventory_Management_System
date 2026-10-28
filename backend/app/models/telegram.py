"""Telegram account links and single-use linking tokens."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class TelegramAccount(Base):
    """A verified Telegram user id bound to exactly one website account."""

    __tablename__ = "telegram_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Verified numeric id from Telegram updates - never a username.
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, index=True
    )
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="telegram_accounts", foreign_keys=[user_id]
    )


class TelegramLinkToken(Base):
    """Cryptographically random, single-use, short-lived linking token.

    Only the SHA-256 hash of the token is stored.
    """

    __tablename__ = "telegram_link_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_ip: Mapped[str | None] = mapped_column(String(64))


class TelegramLinkAttempt(Base):
    __tablename__ = "telegram_link_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_telegram_link_attempts_user_created", "telegram_user_id", "created_at"),
    )
