from __future__ import annotations

from app.core.security import verify_password
from app.models.user import UserSession
from app.services import auth_service, user_service


def test_admin_password_reset_hashes_new_password_and_revokes_sessions(db, admin):
    _, session = auth_service.create_session(db, user=admin)
    db.flush()

    user_service.reset_password(db, user_id=admin.id, new_password="new-secure-password")

    assert verify_password("new-secure-password", admin.password_hash)
    assert not verify_password("correct-horse-123", admin.password_hash)
    assert db.get(UserSession, session.id).revoked_at is not None
    db.commit()
