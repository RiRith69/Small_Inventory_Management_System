"""Create the first administrator without putting a password on the command line."""

from __future__ import annotations

from getpass import getpass

from app.core.config import settings
from app.core.errors import ConflictError
from app.database.session import SessionLocal
from app.models.enums import UserRole
from app.services import catalog_service, user_service


def main() -> None:
    username = settings.admin_username or input("Administrator username: ").strip()
    password = settings.admin_password or getpass("Administrator password: ")

    with SessionLocal() as db:
        if user_service.count_admins(db):
            raise ConflictError(
                "An active administrator already exists; use user management to add another.",
                code="admin_already_exists",
            )
        user = user_service.create(
            db,
            username=username,
            password=password,
            role=UserRole.admin,
        )
        catalog_service.ensure_default_catalog(db)
        db.commit()
        print(f"Created administrator account: {user.username}")


if __name__ == "__main__":
    main()
