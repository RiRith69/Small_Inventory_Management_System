"""Configurable policy and the audit trail (administrator only).

``/api/settings`` lets an administrator change *which roles* may confirm
payments, edit deliveries or delete them - without a code change.  Every change
is recorded in ``audit_logs``.

``/api/audit`` exposes the append-only audit trail so corrections and
revocations can be reviewed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, requires
from app.core.errors import ValidationError
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.system import AuditLog
from app.models.user import User
from app.schemas.common import Message, Page
from app.services import audit_service, settings_service

router = APIRouter(prefix="/api", tags=["settings"])

ROLE_KEYS = {
    "payment_confirmer_roles",
    "delivery_editor_roles",
    "delivery_deleter_roles",
}


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    _: User = Depends(requires("can_manage_settings")),
) -> dict:
    return {
        "settings": settings_service.all_settings(db),
        "definitions": {
            key: {"default": default, "description": desc}
            for key, (default, desc) in settings_service.SETTING_DEFINITIONS.items()
        },
        "roles": [r.value for r in UserRole],
    }


@router.put("/settings/{key}", response_model=Message)
def update_setting(
    key: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_settings")),
) -> Message:
    if key not in settings_service.SETTING_DEFINITIONS:
        raise ValidationError("Unknown setting", code="unknown_setting")
    if key in ROLE_KEYS:
        value = payload.get("value")
        if not isinstance(value, list) or not value:
            raise ValidationError("Select at least one role", code="invalid_setting")
        invalid = [v for v in value if v not in settings_service.VALID_ROLES]
        if invalid:
            raise ValidationError("Unknown role", code="invalid_setting", details=invalid)
        settings_service.set_value(db, key, value, actor_user_id=actor.id)
    else:
        settings_service.set_value(db, key, payload.get("value"), actor_user_id=actor.id)

    audit_service.record(
        db,
        action="settings.update",
        actor_user_id=actor.id,
        entity_type="app_setting",
        details={"key": key, "value": payload.get("value")},
        ip_address=client_ip(request),
    )
    return Message(message="Setting saved")


@router.get("/audit", response_model=Page[dict])
def list_audit(
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(requires("can_view_audit")),
) -> dict:
    stmt = select(AuditLog).outerjoin(User, User.id == AuditLog.actor_user_id)
    count_stmt = select(func.count(AuditLog.id))
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
        count_stmt = count_stmt.where(AuditLog.entity_type == entity_type)

    total = int(db.execute(count_stmt).scalar_one())
    page_rows = db.execute(
        stmt.add_columns(User.username)
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "id": r.id,
            "action": r.action,
            "actor_user_id": r.actor_user_id,
            "actor_username": actor_username,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "details": r.details,
            "ip_address": r.ip_address,
            "created_at": r.created_at,
        }
        for r, actor_username in page_rows
    ]
    return Page.build(items, total=total, page=page, page_size=page_size)
