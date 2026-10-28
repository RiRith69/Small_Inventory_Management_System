"""Authentication: password login, server-side sessions, rate limiting."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, RateLimitedError
from app.core.security import (
    constant_time_equals,
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)
from app.core.timezone import as_utc, now_utc
from app.models.user import LoginAttempt, User, UserSession
from app.services import audit_service

logger = logging.getLogger("app.auth")


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
def _failed_attempts(db: Session, *, username: str | None = None, ip: str | None = None) -> int:
    since = now_utc() - timedelta(minutes=settings.login_window_minutes)
    conditions = []
    if username:
        conditions.append(LoginAttempt.username == username.lower())
    if ip:
        conditions.append(LoginAttempt.ip_address == ip)
    if not conditions:
        return 0
    stmt = select(func.count(LoginAttempt.id)).where(
        LoginAttempt.successful.is_(False),
        LoginAttempt.created_at >= since,
        or_(*conditions),
    )
    return int(db.execute(stmt).scalar_one())


def _record_attempt(db: Session, *, username: str, ip: str | None, successful: bool) -> None:
    db.add(LoginAttempt(username=username.lower(), ip_address=ip, successful=successful))


def authenticate(db: Session, *, username: str, password: str, ip: str | None) -> User:
    """Verify credentials, apply rate limiting, and return the user.

    Always raises the *same* error for a bad username or a bad password so the
    endpoint does not reveal which accounts exist.
    """
    username = username.strip().lower()

    if _failed_attempts(db, username=username, ip=ip) >= settings.login_max_attempts:
        logger.warning("Login rate limit hit")
        raise RateLimitedError(
            "Too many failed attempts. Please wait a few minutes and try again."
        )

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        _record_attempt(db, username=username, ip=ip, successful=False)
        db.commit()
        raise AuthenticationError("Incorrect username or password")

    if not user.is_active:
        _record_attempt(db, username=username, ip=ip, successful=False)
        db.commit()
        raise AuthenticationError("This account is deactivated")

    # Transparently upgrade the hash if Argon2 parameters have changed.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    _record_attempt(db, username=username, ip=ip, successful=True)
    db.flush()
    return user


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
def create_session(
    db: Session, *, user: User, ip: str | None = None, user_agent: str | None = None
) -> tuple[str, UserSession]:
    """Create a brand-new session (prevents session fixation: always new token)."""
    raw_token = generate_token(32)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=generate_token(24),
        expires_at=now_utc() + timedelta(days=settings.session_ttl_days),
        ip_address=ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(session)
    db.flush()
    return raw_token, session


def resolve_session(db: Session, raw_token: str | None) -> UserSession | None:
    """Return a valid session for a raw cookie token, or ``None``."""
    if not raw_token:
        return None
    session = db.execute(
        select(UserSession).where(UserSession.token_hash == hash_token(raw_token))
    ).scalar_one_or_none()
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if as_utc(session.expires_at) <= now_utc():
        return None
    if not session.user or not session.user.is_active:
        return None

    session.last_used_at = now_utc()
    return session


def session_has_csrf(session: UserSession, csrf_token: str | None) -> bool:
    if not csrf_token:
        return False
    return constant_time_equals(session.csrf_token, csrf_token)


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = now_utc()


def revoke_all_sessions(db: Session, user_id: int, *, keep_session_id: int | None = None) -> int:
    """Used after a password reset/change and when an account is deactivated."""
    sessions = (
        db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for s in sessions:
        if keep_session_id is not None and s.id == keep_session_id:
            continue
        s.revoked_at = now_utc()
        count += 1
    return count


# --------------------------------------------------------------------------- #
# Login helper used by both web and tests
# --------------------------------------------------------------------------- #
def login(
    db: Session,
    *,
    username: str,
    password: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, UserSession, User]:
    user = authenticate(db, username=username, password=password, ip=ip)
    raw_token, session = create_session(db, user=user, ip=ip, user_agent=user_agent)
    audit_service.record(
        db, action="auth.login", actor_user_id=user.id, entity_type="user", entity_id=user.id,
        ip_address=ip,
    )
    db.commit()
    db.refresh(session)
    return raw_token, session, user
