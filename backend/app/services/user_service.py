"""Administrator-managed user accounts (there is no public registration)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.telegram import TelegramAccount
from app.models.user import User
from app.services import audit_service

MIN_PASSWORD_LENGTH = 8
MIN_USERNAME_LENGTH = 3


def _normalise_username(username: str) -> str:
    username = (username or "").strip().lower()
    if len(username) < MIN_USERNAME_LENGTH:
        raise ValidationError(f"Username must be at least {MIN_USERNAME_LENGTH} characters")
    if not all(c.isalnum() or c in "._-" for c in username):
        raise ValidationError("Username may only contain letters, digits, dot, dash and underscore")
    return username


def validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def get(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found", code="user_not_found")
    return user


def get_by_username(db: Session, username: str) -> User | None:
    return db.execute(select(User).where(User.username == (username or "").strip().lower())).scalar_one_or_none()


def create(
    db: Session,
    *,
    username: str,
    password: str,
    role: UserRole | str,
    is_active: bool = True,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
) -> User:
    username = _normalise_username(username)
    validate_password(password)
    try:
        role_enum = role if isinstance(role, UserRole) else UserRole(role)
    except ValueError as exc:
        raise ValidationError("Unknown role") from exc

    if get_by_username(db, username) is not None:
        raise ConflictError("That username is already taken", code="username_taken")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role_enum,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    audit_service.record(
        db,
        action="user.create",
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=user.id,
        details={"username": username, "role": role_enum.value},
        ip_address=ip_address,
    )
    return user


def list_users(db: Session) -> list[User]:
    return list(db.execute(select(User).order_by(User.username)).scalars().all())


def update(
    db: Session,
    *,
    user_id: int,
    role: UserRole | str | None = None,
    is_active: bool | None = None,
    username: str | None = None,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
) -> User:
    user = get(db, user_id)
    changes: dict[str, object] = {}

    if username is not None:
        new_username = _normalise_username(username)
        if new_username != user.username:
            existing = get_by_username(db, new_username)
            if existing is not None and existing.id != user.id:
                raise ConflictError("That username is already taken", code="username_taken")
            changes["username"] = [user.username, new_username]
            user.username = new_username

    if role is not None:
        role_enum = role if isinstance(role, UserRole) else UserRole(role)
        if role_enum != user.role:
            changes["role"] = [user.role.value, role_enum.value]
            user.role = role_enum

    if is_active is not None and is_active != user.is_active:
        changes["is_active"] = [user.is_active, is_active]
        user.is_active = is_active
        if not is_active:
            # Deactivating must immediately stop existing sessions.
            from app.services import auth_service

            auth_service.revoke_all_sessions(db, user.id)

    db.flush()
    if changes:
        audit_service.record(
            db,
            action="user.update",
            actor_user_id=actor_user_id,
            entity_type="user",
            entity_id=user.id,
            details=changes,
            ip_address=ip_address,
        )
    return user


def reset_password(
    db: Session,
    *,
    user_id: int,
    new_password: str,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
    revoke_sessions: bool = True,
) -> User:
    validate_password(new_password)
    user = get(db, user_id)
    user.password_hash = hash_password(new_password)
    if revoke_sessions:
        from app.services import auth_service

        auth_service.revoke_all_sessions(db, user.id)
    db.flush()
    audit_service.record(
        db,
        action="user.password_reset",
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=user.id,
        ip_address=ip_address,
    )
    return user


def change_own_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
    keep_session_id: int | None = None,
) -> User:
    from app.core.errors import AuthenticationError
    from app.core.security import verify_password
    from app.services import auth_service

    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect")
    validate_password(new_password)
    user.password_hash = hash_password(new_password)
    auth_service.revoke_all_sessions(db, user.id, keep_session_id=keep_session_id)
    db.flush()
    audit_service.record(
        db, action="user.password_change", actor_user_id=user.id, entity_type="user", entity_id=user.id
    )
    return user


def count_admins(db: Session) -> int:
    stmt = select(func.count(User.id)).where(User.role == UserRole.admin, User.is_active.is_(True))
    return int(db.execute(stmt).scalar_one())


def telegram_link_count(db: Session, user_id: int) -> int:
    stmt = select(func.count(TelegramAccount.id)).where(
        TelegramAccount.user_id == user_id, TelegramAccount.is_active.is_(True)
    )
    return int(db.execute(stmt).scalar_one())
