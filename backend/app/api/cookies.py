"""Session cookie helpers.

The browser only ever stores an opaque, HttpOnly session token.  It is never
readable from JavaScript (so an XSS bug cannot exfiltrate it) and never written
to local storage.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Response

from app.core.config import settings

SESSION_COOKIE_PATH = "/"


def _cookie_kwargs() -> dict:
    kwargs: dict = {
        "key": settings.session_cookie_name,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": SESSION_COOKIE_PATH,
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        value=raw_token,
        max_age=int(timedelta(days=settings.session_ttl_days).total_seconds()),
        **_cookie_kwargs(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(**_cookie_kwargs())
