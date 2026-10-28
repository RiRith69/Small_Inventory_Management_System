"""Append-only audit trail.

Never store secrets (passwords, tokens) in ``details``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.system import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: Any = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
