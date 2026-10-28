"""Telegram account linking and identity resolution.

Security properties
-------------------
* Linking requires an authenticated website session; a single-use token with a
  short expiry is handed to the bot, never the user's password.
* Only the SHA-256 hash of the token is stored.
* Identity after linking is the *verified numeric* ``telegram_user_id`` taken
  from the Telegram update - never a username (usernames can change) and never a
  value the user can supply as proof.
* One Telegram account maps to exactly one website account (DB unique
  constraint), and revoked/inactive links are refused.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    ValidationError,
)
from app.core.security import generate_token, hash_token
from app.core.timezone import as_utc, now_utc
from app.models.telegram import TelegramAccount, TelegramLinkAttempt, TelegramLinkToken
from app.models.user import User
from app.services import audit_service

logger = logging.getLogger("app.telegram")


# --------------------------------------------------------------------------- #
# Link tokens
# --------------------------------------------------------------------------- #
def create_link_token(
    db: Session, *, user_id: int, ip_address: str | None = None
) -> tuple[str, TelegramLinkToken]:
    """Invalidate previous unused tokens for this user and issue a fresh one."""
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found", code="user_not_found")
    if not user.is_active:
        raise PermissionDeniedError("This account is deactivated", code="user_inactive")
    previous = (
        db.execute(
            select(TelegramLinkToken).where(
                TelegramLinkToken.user_id == user_id, TelegramLinkToken.used_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    for token in previous:
        token.used_at = now_utc()  # burn any outstanding token

    raw_token = generate_token(24)
    expires_at = now_utc() + timedelta(minutes=settings.telegram_link_ttl_minutes)
    record = TelegramLinkToken(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
        created_ip=ip_address,
    )
    db.add(record)
    db.flush()
    audit_service.record(
        db, action="telegram.link_token_created", actor_user_id=user_id, entity_type="user",
        entity_id=user_id, ip_address=ip_address,
    )
    return raw_token, record


def link_url(raw_token: str) -> str:
    """Deep link the user taps to open the bot with the token pre-filled."""
    if settings.telegram_bot_username:
        return f"https://t.me/{settings.telegram_bot_username}?start={raw_token}"
    return ""


def consume_link_token(
    db: Session,
    *,
    raw_token: str,
    telegram_user_id: int,
    telegram_username: str | None = None,
    telegram_chat_id: int | None = None,
) -> TelegramAccount:
    """Validate a linking token and bind the Telegram account to the user."""
    raw_token = (raw_token or "").strip()
    if not raw_token:
        raise ValidationError("A linking code is required", code="link_token_missing")

    window_start = now_utc() - timedelta(minutes=settings.telegram_link_window_minutes)
    attempts = db.execute(
        select(TelegramLinkAttempt.id).where(
            TelegramLinkAttempt.telegram_user_id == telegram_user_id,
            TelegramLinkAttempt.successful.is_(False),
            TelegramLinkAttempt.created_at >= window_start,
        )
    ).all()
    if len(attempts) >= settings.telegram_link_max_attempts:
        raise RateLimitedError(
            "Too many linking attempts. Wait a few minutes before trying again.",
            code="telegram_link_rate_limited",
        )

    record = db.execute(
        select(TelegramLinkToken)
        .where(TelegramLinkToken.token_hash == hash_token(raw_token))
        .with_for_update()
    ).scalar_one_or_none()
    if record is None:
        db.add(TelegramLinkAttempt(telegram_user_id=telegram_user_id, successful=False))
        db.commit()
        raise ValidationError("That linking code is not valid", code="link_token_invalid")
    if record.used_at is not None:
        db.add(TelegramLinkAttempt(telegram_user_id=telegram_user_id, successful=False))
        db.commit()
        raise ConflictError("That linking code has already been used", code="link_token_used")
    if as_utc(record.expires_at) <= now_utc():
        db.add(TelegramLinkAttempt(telegram_user_id=telegram_user_id, successful=False))
        db.commit()
        raise ValidationError(
            "That linking code has expired. Please generate a new one from the website.",
            code="link_token_expired",
        )

    user = db.execute(
        select(User).where(User.id == record.user_id).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found", code="user_not_found")
    if not user.is_active:
        raise PermissionDeniedError("This account is deactivated", code="user_inactive")

    # One Telegram account -> one website account.
    existing = db.execute(
        select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id)
    ).scalar_one_or_none()
    if existing is not None and existing.user_id != user.id:
        raise ConflictError(
            "This Telegram account is already linked to a different user. "
            "An administrator must revoke that link first.",
            code="telegram_already_linked",
        )

    # Replace the user's own previous link (if any) - same user, allowed.
    account = (
        db.execute(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user.id, TelegramAccount.is_active.is_(True)
            )
        )
        .scalars()
        .first()
    )
    if account is not None and account.telegram_user_id != telegram_user_id:
        account.is_active = False
        account.revoked_at = now_utc()

    if existing is not None:
        account = existing
        account.is_active = True
        account.revoked_at = None
        account.revoked_by = None
    elif account is None or account.telegram_user_id != telegram_user_id:
        account = TelegramAccount(user_id=user.id, telegram_user_id=telegram_user_id)
        db.add(account)

    account.telegram_username = (telegram_username or None)
    account.telegram_chat_id = telegram_chat_id
    record.used_at = now_utc()
    db.add(TelegramLinkAttempt(telegram_user_id=telegram_user_id, successful=True))
    db.flush()

    audit_service.record(
        db, action="telegram.linked", actor_user_id=user.id, entity_type="user", entity_id=user.id,
        details={"telegram_user_id": telegram_user_id},
    )
    return account


# --------------------------------------------------------------------------- #
# Identity resolution (used by every protected bot action)
# --------------------------------------------------------------------------- #
def resolve(db: Session, telegram_user_id: int) -> tuple[User, TelegramAccount]:
    """Map a verified Telegram user id to a website user, or raise."""
    if telegram_user_id is None:
        raise PermissionDeniedError("Telegram user id is required", code="telegram_user_missing")

    account = db.execute(
        select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id)
    ).scalar_one_or_none()
    if account is None:
        raise PermissionDeniedError(
            "This Telegram account is not linked yet. Link it from the website first.",
            code="telegram_not_linked",
        )
    if not account.is_active or account.revoked_at is not None:
        raise PermissionDeniedError(
            "Your Telegram link has been revoked. Please link again from the website.",
            code="telegram_link_revoked",
        )
    user = db.get(User, account.user_id)
    if user is None or not user.is_active:
        raise PermissionDeniedError("This account is deactivated", code="user_inactive")
    return user, account


# --------------------------------------------------------------------------- #
# Unlinking
# --------------------------------------------------------------------------- #
def unlink_self(db: Session, *, user: User, ip_address: str | None = None) -> int:
    accounts = (
        db.execute(
            select(TelegramAccount).where(
                TelegramAccount.user_id == user.id, TelegramAccount.is_active.is_(True)
            )
        )
        .scalars()
        .all()
    )
    for account in accounts:
        account.is_active = False
        account.revoked_at = now_utc()
        account.revoked_by = user.id
    if accounts:
        audit_service.record(
            db, action="telegram.unlinked", actor_user_id=user.id, entity_type="user",
            entity_id=user.id, ip_address=ip_address,
        )
    db.flush()
    return len(accounts)


def revoke_link(
    db: Session, *, telegram_account_id: int, actor_user_id: int, ip_address: str | None = None
) -> TelegramAccount:
    account = db.get(TelegramAccount, telegram_account_id)
    if account is None:
        raise NotFoundError("Telegram link not found", code="telegram_link_not_found")
    if not account.is_active:
        raise ConflictError("That link is already revoked", code="already_revoked")
    account.is_active = False
    account.revoked_at = now_utc()
    account.revoked_by = actor_user_id
    db.flush()
    audit_service.record(
        db, action="telegram.revoked", actor_user_id=actor_user_id, entity_type="telegram_account",
        entity_id=account.id, details={"user_id": account.user_id}, ip_address=ip_address,
    )
    return account


def link_status(db: Session, user_id: int) -> dict:
    accounts = (
        db.execute(
            select(TelegramAccount)
            .where(TelegramAccount.user_id == user_id)
            .order_by(TelegramAccount.id.desc())
        )
        .scalars()
        .all()
    )
    active = next((a for a in accounts if a.is_active), None)
    return {
        "is_linked": active is not None,
        "bot_username": settings.telegram_bot_username or None,
        "telegram_user_id": active.telegram_user_id if active else None,
        "telegram_username": active.telegram_username if active else None,
        "linked_at": active.linked_at if active else None,
        "history": [
            {
                "id": a.id,
                "telegram_user_id": a.telegram_user_id,
                "telegram_username": a.telegram_username,
                "linked_at": a.linked_at,
                "is_active": a.is_active,
                "revoked_at": a.revoked_at,
            }
            for a in accounts
        ],
    }
