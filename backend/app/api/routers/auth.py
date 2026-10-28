"""Authentication endpoints: login, logout, current user, own password change.

There is deliberately **no public registration endpoint** - accounts are created
by an administrator (``/api/users``) or by the ``create_admin`` bootstrap CLI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.cookies import clear_session_cookie, set_session_cookie
from app.api.deps import client_ip, get_current_session
from app.api.serializers import user_payload
from app.database.session import get_db
from app.models.user import UserSession
from app.schemas.auth import CurrentUser, LoginRequest, PasswordChangeRequest
from app.schemas.common import Message
from app.services import audit_service, auth_service, user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=CurrentUser)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """Authenticate and start a persistent (30-day) server-side session.

    The session token is set as an HttpOnly cookie; the CSRF token is returned in
    the body so the SPA can send it back in the ``X-CSRF-Token`` header.
    """
    raw_token, session, user = auth_service.login(
        db,
        username=payload.username,
        password=payload.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, raw_token)
    return user_payload(db, user, session)


@router.post("/logout", response_model=Message)
def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> Message:
    auth_service.revoke_session(db, session)
    db.flush()
    clear_session_cookie(response)
    return Message(message="Signed out")


@router.get("/me", response_model=CurrentUser)
def me(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> dict:
    """Return the signed-in user.  Used on app start to restore a persistent login."""
    return user_payload(db, session.user, session)


@router.post("/password", response_model=Message)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> Message:
    """Change your own password (revokes every *other* session)."""
    user_service.change_own_password(
        db,
        user=session.user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        keep_session_id=session.id,
    )
    audit_service.record(
        db,
        action="auth.password_change",
        actor_user_id=session.user.id,
        entity_type="user",
        entity_id=session.user.id,
        ip_address=client_ip(request),
    )
    return Message(message="Password updated")
