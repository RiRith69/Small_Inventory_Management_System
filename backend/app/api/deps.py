"""FastAPI dependencies: authentication, CSRF, authorization, bot auth."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import constant_time_equals
from app.database.session import get_db
from app.models.user import User, UserSession
from app.services import auth_service, settings_service

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    ``X-Forwarded-For`` is honoured because the documented deployment puts the
    app behind a reverse proxy; only the first hop is taken.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> UserSession:
    """Resolve the session cookie and enforce CSRF on state-changing requests."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    session = auth_service.resolve_session(db, raw_token)
    if session is None:
        raise AuthenticationError("Please sign in to continue", code="not_authenticated")

    if request.method in UNSAFE_METHODS:
        if not auth_service.session_has_csrf(session, x_csrf_token):
            raise PermissionDeniedError(
                "Your session token is invalid or expired. Please sign in again.",
                code="csrf_invalid",
            )
    return session


def get_current_user(session: UserSession = Depends(get_current_session)) -> User:
    return session.user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    raw_token = request.cookies.get(settings.session_cookie_name)
    session = auth_service.resolve_session(db, raw_token)
    return session.user if session else None


def requires(permission: str) -> Callable[..., User]:
    """Dependency factory enforcing a named permission from settings policy."""

    def _dependency(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not settings_service.permissions_for(db, user).get(permission):
            raise PermissionDeniedError(
                "You do not have permission to perform this action", code="forbidden"
            )
        return user

    return _dependency


def require_bot_token(x_bot_token: str | None = Header(default=None, alias="X-Bot-Token")) -> None:
    """Authenticate the internal Telegram bot service."""
    from app.core.errors import AuthenticationError as _AuthError

    if not x_bot_token or not constant_time_equals(x_bot_token, settings.bot_api_token):
        raise _AuthError("Invalid bot credentials", code="bot_unauthorized")
