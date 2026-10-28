from __future__ import annotations

from datetime import timedelta

from app.core.errors import ConflictError, ValidationError
from app.core.timezone import now_utc
from app.models.enums import UserRole
from app.models.telegram import TelegramAccount
from app.services import telegram_service, user_service


def test_login_create_user_and_protected_delivery(authenticated_client, suppliers):
    client = authenticated_client
    suppliers_list, roll_types = suppliers

    unauthenticated = client.get("/api/auth/me")
    assert unauthenticated.status_code == 200

    created_user = client.post(
        "/api/users",
        json={
            "username": "warehouse01",
            "password": "warehouse-password",
            "role": "warehouse_user",
        },
    )
    assert created_user.status_code == 201
    assert created_user.json()["role"] == "warehouse_user"

    response = client.post(
        "/api/deliveries",
        json={
            "supplier_id": suppliers_list[0].id,
            "roll_type_id": roll_types[0].id,
            "quantity_received": 11,
            "delivery_date": "2026-10-17",
            "idempotency_key": "web-delivery-idem",
        },
    )
    assert response.status_code == 201
    assert response.json()["quantity_unpaid"] == 11
    listed = client.get("/api/deliveries?start_date=2026-10-17&end_date=2026-10-17")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_unauthenticated_api_is_rejected(client):
    response = client.get("/api/deliveries")
    assert response.status_code == 401


def test_bot_delivery_uses_same_database_and_rejects_unlinked_identity(client, db, admin, suppliers):
    suppliers_list, roll_types = suppliers
    db.add(
        TelegramAccount(
            user_id=admin.id,
            telegram_user_id=882233,
            telegram_username="warehouse_staff",
            telegram_chat_id=882233,
        )
    )
    db.commit()
    headers = {"X-Bot-Token": "test-only-bot-secret"}

    forbidden = client.get(
        "/api/bot/summary",
        params={"telegram_user_id": 882234},
        headers=headers,
    )
    assert forbidden.status_code == 403

    unauthorized = client.get(
        "/api/bot/summary",
        params={"telegram_user_id": 882233},
        headers={"X-Bot-Token": "wrong"},
    )
    assert unauthorized.status_code == 401

    created = client.post(
        "/api/bot/deliveries",
        headers=headers,
        json={
            "telegram_user_id": 882233,
            "supplier_id": suppliers_list[0].id,
            "roll_type_id": roll_types[0].id,
            "quantity_received": 7,
            "delivery_date": "2026-10-17",
            "idempotency_key": "bot-delivery-idem",
        },
    )
    assert created.status_code == 201
    assert created.json()["delivery"]["roll_type_name"] == roll_types[0].name_km
    assert created.json()["delivery"]["roll_type_name_en"] == roll_types[0].name_en
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-123"},
    )
    assert login.status_code == 200
    client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    website_list = client.get(
        "/api/deliveries?start_date=2026-10-17&end_date=2026-10-17"
    )
    assert website_list.status_code == 200
    assert website_list.json()["items"][0]["quantity_received"] == 7
    assert website_list.json()["items"][0]["roll_type_name"] == created.json()["delivery"]["roll_type_name"]
    bot_list = client.get(
        "/api/bot/deliveries",
        params={"telegram_user_id": 882233, "start_date": "2026-10-17", "end_date": "2026-10-17"},
        headers=headers,
    )
    assert bot_list.status_code == 200
    assert bot_list.json()["items"][0]["roll_type_name"] == website_list.json()["items"][0]["roll_type_name"]
    assert bot_list.json()["items"][0]["quantity_unpaid"] == website_list.json()["items"][0]["quantity_unpaid"]


def test_bot_unpaid_preview_returns_delivery_dates_from_matching_records(client, db, admin, suppliers):
    from datetime import date

    from app.services import delivery_service

    suppliers_list, roll_types = suppliers
    db.add(
        TelegramAccount(
            user_id=admin.id,
            telegram_user_id=882239,
            telegram_chat_id=882239,
        )
    )
    db.commit()
    for supplier_id, roll_type_id, delivery_date in (
        (suppliers_list[0].id, roll_types[0].id, date(2026, 10, 13)),
        (suppliers_list[0].id, roll_types[0].id, date(2026, 10, 15)),
        (suppliers_list[0].id, roll_types[1].id, date(2026, 10, 14)),
        (suppliers_list[1].id, roll_types[0].id, date(2026, 10, 16)),
    ):
        delivery_service.create_delivery(
            db,
            supplier_id=supplier_id,
            roll_type_id=roll_type_id,
            quantity_received=4,
            delivery_date=delivery_date,
            created_by=admin.id,
        )

    response = client.get(
        "/api/bot/payments/unpaid",
        headers={"X-Bot-Token": "test-only-bot-secret"},
        params={
            "telegram_user_id": 882239,
            "supplier_id": suppliers_list[0].id,
            "roll_type_id": roll_types[0].id,
        },
    )

    assert response.status_code == 200
    assert response.json()["delivery_dates"] == ["2026-10-13", "2026-10-15"]
    assert {row["delivery_date"] for row in response.json()["deliveries"]} == {
        "2026-10-13",
        "2026-10-15",
    }


def test_localized_roll_type_catalog_is_consistent_for_website_and_bot(client, authenticated_client, db, admin, suppliers):
    _, roll_types = suppliers
    db.add(
        TelegramAccount(
            user_id=admin.id,
            telegram_user_id=882238,
            telegram_chat_id=882238,
        )
    )
    db.commit()
    website = authenticated_client.get("/api/catalog")
    bot = client.get(
        "/api/bot/catalog",
        params={"telegram_user_id": 882238},
        headers={"X-Bot-Token": "test-only-bot-secret"},
    )
    assert website.status_code == bot.status_code == 200
    expected = {
        row["code"]: (row["name_km"], row["name_en"])
        for row in website.json()["roll_types"]
    }
    assert expected == {
        item.code: (item.name_km, item.name_en)
        for item in roll_types
    }
    assert {
        row["code"]: (row["name_km"], row["name_en"])
        for row in bot.json()["roll_types"]
    } == expected


def test_link_tokens_are_single_use_and_expired_tokens_are_rejected(db, admin):
    token, record = telegram_service.create_link_token(db, user_id=admin.id)
    linked = telegram_service.consume_link_token(
        db,
        raw_token=token,
        telegram_user_id=882235,
        telegram_username="staff",
    )
    assert linked.telegram_user_id == 882235
    try:
        telegram_service.consume_link_token(
            db,
            raw_token=token,
            telegram_user_id=882235,
        )
    except ConflictError as exc:
        assert exc.code == "link_token_used"
    else:
        raise AssertionError("A reused Telegram link token must be rejected")

    expired_token, expired = telegram_service.create_link_token(db, user_id=admin.id)
    expired.expires_at = now_utc() - timedelta(seconds=1)
    db.flush()
    try:
        telegram_service.consume_link_token(
            db,
            raw_token=expired_token,
            telegram_user_id=882236,
        )
    except ValidationError as exc:
        assert exc.code == "link_token_expired"
    else:
        raise AssertionError("An expired Telegram link token must be rejected")


def test_warehouse_role_cannot_confirm_payment_by_default(client, admin, suppliers, db):
    suppliers_list, roll_types = suppliers
    warehouse_user = user_service.create(
        db,
        username="worker02",
        password="warehouse-password",
        role=UserRole.warehouse_user,
    )
    from app.services import delivery_service
    from datetime import date

    delivery_service.create_delivery(
        db,
        supplier_id=suppliers_list[0].id,
        roll_type_id=roll_types[0].id,
        quantity_received=5,
        delivery_date=date(2026, 10, 17),
        created_by=admin.id,
    )
    db.add(
        TelegramAccount(
            user_id=warehouse_user.id,
            telegram_user_id=882237,
            telegram_chat_id=882237,
        )
    )
    db.commit()

    response = client.post(
        "/api/bot/payments/confirm",
        headers={"X-Bot-Token": "test-only-bot-secret"},
        json={
            "telegram_user_id": 882237,
            "supplier_id": suppliers_list[0].id,
            "start_date": "2026-10-17",
            "end_date": "2026-10-17",
        },
    )
    assert response.status_code == 403
