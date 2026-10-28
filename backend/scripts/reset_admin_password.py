"""Reset an existing administrator password through a private prompt."""

from __future__ import annotations

from getpass import getpass

from app.core.errors import NotFoundError, ValidationError
from app.database.session import SessionLocal
from app.models.enums import UserRole
from app.services import user_service


def main() -> None:
    username = input("Administrator username: ").strip().lower()
    new_password = getpass("New administrator password: ")
    confirmation = getpass("Confirm new password: ")
    if new_password != confirmation:
        raise ValidationError("The passwords do not match")

    with SessionLocal() as db:
        user = user_service.get_by_username(db, username)
        if user is None or user.role != UserRole.admin or not user.is_active:
            raise NotFoundError("Active administrator account not found", code="admin_not_found")
        user_service.reset_password(db, user_id=user.id, new_password=new_password)
        db.commit()
        print(f"Administrator password reset for account: {user.username}")


if __name__ == "__main__":
    main()
