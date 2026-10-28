from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app
from app.models.enums import UserRole
from app.services import catalog_service, user_service


@pytest.fixture
def db_factory(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'warehouse-test.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_factory):
    session = db_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def admin(db):
    user = user_service.create(
        db,
        username="admin",
        password="correct-horse-123",
        role=UserRole.admin,
    )
    catalog_service.ensure_default_catalog(db)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client(db_factory, admin, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "bot_api_token", "test-only-bot-secret")
    application = create_app()

    def override_db():
        session = db_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as test_client:
        yield test_client
    application.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-123"},
    )
    assert response.status_code == 200
    client.headers.update({"X-CSRF-Token": response.json()["csrf_token"]})
    return client


@pytest.fixture
def suppliers(db):
    from sqlalchemy import select
    from app.models.catalog import Supplier, RollType

    return (
        list(db.execute(select(Supplier).order_by(Supplier.id)).scalars()),
        list(db.execute(select(RollType).order_by(RollType.id)).scalars()),
    )
