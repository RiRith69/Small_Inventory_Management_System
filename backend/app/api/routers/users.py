"""Administrator-only user management.

There is no public registration: an administrator creates accounts, assigns
roles, deactivates accounts and resets passwords.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, requires
from app.core.errors import ConflictError
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import Message
from app.schemas.user import (
    PasswordResetRequest,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import telegram_service, user_service

router = APIRouter(prefix="/api/users", tags=["users"])


def _payload(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "telegram_linked": user_service.telegram_link_count(db, user.id) > 0,
    }


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(requires("can_manage_users")),
) -> list[dict]:
    return [_payload(db, u) for u in user_service.list_users(db)]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_users")),
) -> dict:
    user = user_service.create(
        db,
        username=payload.username,
        password=payload.password,
        role=payload.role,
        is_active=payload.is_active,
        actor_user_id=actor.id,
        ip_address=client_ip(request),
    )
    return _payload(db, user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_users")),
) -> dict:
    # Guard against locking everybody out of the admin pages.
    if user_id == actor.id and payload.is_active is False:
        raise ConflictError("You cannot deactivate your own account", code="cannot_deactivate_self")

    target = user_service.get(db, user_id)
    demoting = payload.role is not None and payload.role != target.role
    deactivating = payload.is_active is False
    if (demoting or deactivating) and target.is_admin and user_service.count_admins(db) <= 1:
        raise ConflictError(
            "This is the last active administrator account", code="last_admin"
        )

    user = user_service.update(
        db,
        user_id=user_id,
        username=payload.username,
        role=payload.role,
        is_active=payload.is_active,
        actor_user_id=actor.id,
        ip_address=client_ip(request),
    )
    return _payload(db, user)


@router.post("/{user_id}/password", response_model=Message)
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_users")),
) -> Message:
    """Reset a user's password.  All of that user's sessions are revoked."""
    user_service.reset_password(
        db,
        user_id=user_id,
        new_password=payload.new_password,
        actor_user_id=actor.id,
        ip_address=client_ip(request),
    )
    return Message(message="Password reset")


@router.get("/{user_id}/telegram")
def user_telegram_status(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(requires("can_manage_telegram_links")),
) -> dict:
    user_service.get(db, user_id)
    return telegram_service.link_status(db, user_id)


@router.delete("/{user_id}/telegram", response_model=dict)
def revoke_user_telegram(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_telegram_links")),
) -> dict:
    """Revoke every Telegram link belonging to a user (admin override)."""
    user_service.get(db, user_id)
    status = telegram_service.link_status(db, user_id)
    revoked = 0
    for entry in status["history"]:
        if entry["is_active"]:
            telegram_service.revoke_link(
                db,
                telegram_account_id=entry["id"],
                actor_user_id=actor.id,
                ip_address=client_ip(request),
            )
            revoked += 1
    return {"revoked": revoked, "status": telegram_service.link_status(db, user_id)}
