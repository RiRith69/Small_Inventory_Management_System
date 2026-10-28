from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, ValidationError
from app.models.catalog import RollType, Supplier
from app.models.delivery import Delivery
from app.models.enums import UserRole
from app.models.payment import Payment
from app.services import catalog_service, delivery_service, payment_service, user_service


def test_multiple_delivery_dates_partial_payment_and_later_delivery(db, admin, suppliers):
    suppliers_list, roll_types = suppliers
    supplier = suppliers_list[0]
    roll_type = roll_types[0]
    first = delivery_service.create_delivery(
        db,
        supplier_id=supplier.id,
        roll_type_id=roll_type.id,
        quantity_received=10,
        delivery_date=date(2026, 10, 13),
        created_by=admin.id,
    )
    second = delivery_service.create_delivery(
        db,
        supplier_id=supplier.id,
        roll_type_id=roll_type.id,
        quantity_received=8,
        delivery_date=date(2026, 10, 14),
        created_by=admin.id,
    )

    partial = payment_service.confirm_payment(
        db,
        supplier_id=supplier.id,
        actor_user_id=admin.id,
        payment_date=date(2026, 10, 17),
        allocations=[{"delivery_id": first.id, "quantity": 6}],
        idempotency_key="partial-1",
    )
    preview = payment_service.preview_payment(
        db,
        supplier_id=supplier.id,
        start_date=date(2026, 10, 13),
        end_date=date(2026, 10, 14),
    )
    assert preview["totals"] == {"received": 18, "paid": 6, "unpaid": 12}
    assert next(row for row in preview["deliveries"] if row["id"] == first.id)["quantity_unpaid"] == 4

    remaining = payment_service.confirm_payment(
        db,
        supplier_id=supplier.id,
        actor_user_id=admin.id,
        payment_date=date(2026, 10, 17),
        start_date=date(2026, 10, 13),
        end_date=date(2026, 10, 14),
        idempotency_key="range-1",
    )
    assert payment_service.payment_detail(db, partial.id)["total_quantity"] == 6
    assert payment_service.payment_detail(db, remaining.id)["total_quantity"] == 12
    assert payment_service.preview_payment(db, supplier_id=supplier.id)["totals"]["unpaid"] == 0

    later = delivery_service.create_delivery(
        db,
        supplier_id=supplier.id,
        roll_type_id=roll_type.id,
        quantity_received=5,
        delivery_date=date(2026, 10, 15),
        created_by=admin.id,
    )
    current = payment_service.preview_payment(db, supplier_id=supplier.id)
    assert current["totals"]["unpaid"] == 5
    assert [row["id"] for row in current["deliveries"]] == [later.id]
    db.commit()


def test_default_roll_types_filtering_localized_names_and_per_type_payment_totals(db, admin, suppliers):
    suppliers_list, roll_types = suppliers
    types_by_code = {roll_type.code: roll_type for roll_type in roll_types}
    assert set(types_by_code) == {"THICK_GLUE", "THIN_GLUE"}
    assert len(roll_types) == 2
    assert types_by_code["THICK_GLUE"].name_km == "កាវក្រាស់"
    assert types_by_code["THICK_GLUE"].name_en == "Thick Glue"
    assert types_by_code["THIN_GLUE"].name_km == "កាវស្ដើង"
    assert types_by_code["THIN_GLUE"].name_en == "Thin Glue"

    supplier = suppliers_list[0]
    thick = delivery_service.create_delivery(
        db,
        supplier_id=supplier.id,
        roll_type_id=types_by_code["THICK_GLUE"].id,
        quantity_received=20,
        delivery_date=date(2026, 10, 16),
        created_by=admin.id,
    )
    thin = delivery_service.create_delivery(
        db,
        supplier_id=supplier.id,
        roll_type_id=types_by_code["THIN_GLUE"].id,
        quantity_received=10,
        delivery_date=date(2026, 10, 16),
        created_by=admin.id,
    )

    thick_rows, thick_count = delivery_service.list_deliveries(
        db, supplier_id=supplier.id, roll_type_id=types_by_code["THICK_GLUE"].id
    )
    assert thick_count == 1
    assert [row.id for row in thick_rows] == [thick.id]

    payment_service.confirm_payment(
        db,
        supplier_id=supplier.id,
        roll_type_id=types_by_code["THICK_GLUE"].id,
        actor_user_id=admin.id,
        payment_date=date(2026, 10, 17),
        allocations=[{"delivery_id": thick.id, "quantity": 12}],
    )
    payment_service.confirm_payment(
        db,
        supplier_id=supplier.id,
        roll_type_id=types_by_code["THIN_GLUE"].id,
        actor_user_id=admin.id,
        payment_date=date(2026, 10, 17),
        allocations=[{"delivery_id": thin.id, "quantity": 3}],
    )
    thick_preview = payment_service.preview_payment(
        db, supplier_id=supplier.id, roll_type_id=types_by_code["THICK_GLUE"].id
    )
    thin_preview = payment_service.preview_payment(
        db, supplier_id=supplier.id, roll_type_id=types_by_code["THIN_GLUE"].id
    )
    assert thick_preview["totals"] == {"received": 20, "paid": 12, "unpaid": 8}
    assert thick_preview["by_roll_type"][0]["roll_type_name"] == "កាវក្រាស់"
    assert thin_preview["totals"] == {"received": 10, "paid": 3, "unpaid": 7}
    assert thin_preview["by_roll_type"][0]["roll_type_name"] == "កាវស្ដើង"
    with pytest.raises(ValidationError, match="different roll type"):
        payment_service.confirm_payment(
            db,
            supplier_id=supplier.id,
            roll_type_id=types_by_code["THIN_GLUE"].id,
            actor_user_id=admin.id,
            allocations=[{"delivery_id": thick.id, "quantity": 1}],
        )
    with pytest.raises(ConflictError, match="deactivate it"):
        catalog_service.delete_roll_type(
            db, roll_type_id=types_by_code["THICK_GLUE"].id, actor_user_id=admin.id
        )
    assert db.get(RollType, types_by_code["THICK_GLUE"].id).is_active
    db.commit()


def test_roll_type_code_is_unique_and_localized_names_update_independently(db, admin):
    created = catalog_service.create_roll_type(
        db,
        code="TEST_TYPE",
        name_km="ប្រភេទសាកល្បង",
        name_en="Test type",
        actor_user_id=admin.id,
    )
    with pytest.raises(ConflictError, match="code already exists"):
        catalog_service.create_roll_type(
            db,
            code="TEST_TYPE",
            name_km="ប្រភេទថ្មី",
            name_en="New type",
            actor_user_id=admin.id,
        )
    catalog_service.update_roll_type(
        db,
        roll_type_id=created.id,
        name_en="Updated test type",
        actor_user_id=admin.id,
    )
    assert created.name_km == "ប្រភេទសាកល្បង"
    assert created.name_en == "Updated test type"
    db.commit()


def test_supplier_isolation_and_idempotency_request_binding(db, admin, suppliers):
    suppliers_list, roll_types = suppliers
    supplier_a, supplier_b = suppliers_list
    delivery = delivery_service.create_delivery(
        db,
        supplier_id=supplier_a.id,
        roll_type_id=roll_types[0].id,
        quantity_received=9,
        delivery_date=date(2026, 10, 16),
        created_by=admin.id,
    )

    with pytest.raises(ValidationError, match="different supplier"):
        payment_service.confirm_payment(
            db,
            supplier_id=supplier_b.id,
            actor_user_id=admin.id,
            allocations=[{"delivery_id": delivery.id, "quantity": 2}],
        )

    payment = payment_service.confirm_payment(
        db,
        supplier_id=supplier_a.id,
        actor_user_id=admin.id,
        payment_date=date(2026, 10, 17),
        allocations=[{"delivery_id": delivery.id, "quantity": 3}],
        idempotency_key="same-request",
    )
    duplicate = payment_service.confirm_payment(
        db,
        supplier_id=supplier_a.id,
        actor_user_id=admin.id,
        payment_date=date(2026, 10, 17),
        allocations=[{"delivery_id": delivery.id, "quantity": 3}],
        idempotency_key="same-request",
    )
    assert duplicate.id == payment.id
    with pytest.raises(ConflictError, match="different payment"):
        payment_service.confirm_payment(
            db,
            supplier_id=supplier_a.id,
            actor_user_id=admin.id,
            payment_date=date(2026, 10, 17),
            allocations=[{"delivery_id": delivery.id, "quantity": 4}],
            idempotency_key="same-request",
        )

    assert payment_service.preview_payment(db, supplier_id=supplier_a.id)["totals"]["unpaid"] == 6
    db.commit()


def test_concurrent_payment_idempotency_replays_after_delivery_lock(db, admin, suppliers, monkeypatch):
    suppliers_list, roll_types = suppliers
    delivery = delivery_service.create_delivery(
        db,
        supplier_id=suppliers_list[0].id,
        roll_type_id=roll_types[0].id,
        quantity_received=5,
        delivery_date=date(2026, 10, 16),
        created_by=admin.id,
    )
    request = {
        "supplier_id": suppliers_list[0].id,
        "actor_user_id": admin.id,
        "payment_date": date(2026, 10, 17),
        "allocations": [{"delivery_id": delivery.id, "quantity": 3}],
        "idempotency_key": "concurrent-request",
    }
    original_lock = payment_service.locked_deliveries
    first_payment = None
    injected = False

    def insert_concurrent_request(session, candidate_ids):
        nonlocal first_payment, injected
        if not injected:
            injected = True
            first_payment = payment_service.confirm_payment(session, **request)
        return original_lock(session, candidate_ids)

    monkeypatch.setattr(payment_service, "locked_deliveries", insert_concurrent_request)
    replay = payment_service.confirm_payment(db, **request)

    assert first_payment is not None
    assert replay.id == first_payment.id
    assert len(
        db.execute(select(Payment).where(Payment.idempotency_key == "concurrent-request"))
        .scalars()
        .all()
    ) == 1
    db.commit()


def test_reversal_restores_unpaid_quantity_and_retains_original_record(db, admin, suppliers):
    suppliers_list, roll_types = suppliers
    supplier = suppliers_list[0]
    delivery = delivery_service.create_delivery(
        db,
        supplier_id=supplier.id,
        roll_type_id=roll_types[0].id,
        quantity_received=10,
        delivery_date=date(2026, 10, 13),
        created_by=admin.id,
    )
    payment = payment_service.confirm_payment(
        db,
        supplier_id=supplier.id,
        actor_user_id=admin.id,
        payment_date=date(2026, 10, 17),
        allocations=[{"delivery_id": delivery.id, "quantity": 6}],
    )
    payment_service.reverse_payment(
        db,
        payment_id=payment.id,
        reason="Duplicate supplier record",
        actor_user_id=admin.id,
    )

    assert payment_service.preview_payment(db, supplier_id=supplier.id)["totals"]["unpaid"] == 10
    assert payment_service.payment_detail(db, payment.id)["is_reversed"] is True
    assert db.get(Delivery, delivery.id).delivery_date == date(2026, 10, 13)
    assert db.execute(select(Payment.id)).scalars().all() == [payment.id]


def test_delivery_idempotency_rejects_key_reuse_with_changed_data(db, admin, suppliers):
    suppliers_list, roll_types = suppliers
    request = {
        "supplier_id": suppliers_list[0].id,
        "roll_type_id": roll_types[0].id,
        "quantity_received": 4,
        "delivery_date": date(2026, 10, 17),
        "created_by": admin.id,
        "idempotency_key": "delivery-request",
    }
    first = delivery_service.create_delivery(db, **request)
    duplicate = delivery_service.create_delivery(db, **request)
    assert duplicate.id == first.id
    with pytest.raises(ConflictError, match="different delivery"):
        delivery_service.create_delivery(db, **{**request, "quantity_received": 5})
