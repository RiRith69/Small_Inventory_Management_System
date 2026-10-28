"""Configurable policy + derived permission set.

Administrators can change *which roles* may confirm payments, edit deliveries or
delete them, without a code change.  Defaults are safe (admin-only).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.system import AppSetting
from app.models.user import User

# key -> (default value, human description)
SETTING_DEFINITIONS: dict[str, tuple[Any, str]] = {
    "payment_confirmer_roles": (
        [UserRole.admin.value],
        "Roles allowed to confirm payments (web + Telegram)",
    ),
    "delivery_editor_roles": (
        [UserRole.admin.value],
        "Roles allowed to edit/correct an existing delivery",
    ),
    "delivery_deleter_roles": (
        [UserRole.admin.value],
        "Roles allowed to delete an unallocated delivery",
    ),
}
VALID_ROLES = {r.value for r in UserRole}


def get_value(db: Session, key: str) -> Any:
    default, _ = SETTING_DEFINITIONS[key]
    row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    if row is None:
        return default
    return row.value


def set_value(db: Session, key: str, value: Any, *, actor_user_id: int | None = None) -> AppSetting:
    row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    if row is None:
        row = AppSetting(key=key, value=value, updated_by=actor_user_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by = actor_user_id
    db.flush()
    return row


def all_settings(db: Session) -> dict[str, Any]:
    return {key: get_value(db, key) for key in SETTING_DEFINITIONS}


def _roles_for(db: Session, key: str) -> set[str]:
    value = get_value(db, key) or []
    return {v for v in value if v in VALID_ROLES}


def permissions_for(db: Session, user: User) -> dict[str, bool]:
    """The single source of truth for what a user may do."""
    role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    is_admin = role == UserRole.admin.value
    return {
        "can_manage_users": is_admin,
        "can_manage_catalog": is_admin,
        "can_manage_settings": is_admin,
        "can_manage_telegram_links": is_admin,
        "can_view_audit": is_admin,
        "can_edit_deliveries": role in _roles_for(db, "delivery_editor_roles"),
        "can_delete_deliveries": role in _roles_for(db, "delivery_deleter_roles"),
        "can_confirm_payments": role in _roles_for(db, "payment_confirmer_roles"),
        "can_reverse_payments": is_admin,
        "can_record_deliveries": True,
    }
