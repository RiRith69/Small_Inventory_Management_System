"""Delivery management (recording, correcting, listing, summaries).

Deliveries are the permanent record of what was received.  Payment processing
never modifies them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.timezone import local_today
from app.models.catalog import RollType, Supplier
from app.models.delivery import Delivery
from app.models.enums import DeliverySource
from app.models.payment import PaymentAllocation
from app.services import audit_service, catalog_service
from app.services.queries import (
    DeliveryRow,
    fetch_delivery_rows,
    group_rows_by,
    count_deliveries,
    totals_for_rows,
    validate_date_range,
)

EARLIEST_DELIVERY_DATE = date(2000, 1, 1)
MAX_FUTURE_DAYS = 365


def _validate_delivery_date(d: date) -> date:
    if d is None:
        raise ValidationError("Delivery date is required")
    if d < EARLIEST_DELIVERY_DATE:
        raise ValidationError("Delivery date is unrealistically far in the past", code="invalid_date")
    if d > local_today() + timedelta(days=MAX_FUTURE_DAYS):
        raise ValidationError("Delivery date is unrealistically far in the future", code="invalid_date")
    return d


def _validate_quantity(quantity: int) -> int:
    if quantity is None or not isinstance(quantity, int) or isinstance(quantity, bool):
        raise ValidationError("Quantity must be a whole number", code="invalid_quantity")
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than zero", code="invalid_quantity")
    if quantity > 1_000_000:
        raise ValidationError("Quantity is too large", code="invalid_quantity")
    return quantity


def _resolve_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found", code="supplier_not_found")
    if not supplier.is_active:
        raise ValidationError("That supplier is deactivated", code="supplier_inactive")
    return supplier


def _resolve_roll_type(db: Session, roll_type_id: int) -> RollType:
    roll_type = db.get(RollType, roll_type_id)
    if roll_type is None:
        raise NotFoundError("Roll type not found", code="roll_type_not_found")
    if not roll_type.is_active:
        raise ValidationError("That roll type is deactivated", code="roll_type_inactive")
    return roll_type


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
def create_delivery(
    db: Session,
    *,
    supplier_id: int,
    roll_type_id: int,
    quantity_received: int,
    delivery_date: date | None = None,
    note: str | None = None,
    created_by: int,
    source: DeliverySource | str = DeliverySource.web,
    idempotency_key: str | None = None,
    ip_address: str | None = None,
) -> Delivery:
    delivery_date = _validate_delivery_date(delivery_date or local_today())
    quantity_received = _validate_quantity(quantity_received)
    supplier = _resolve_supplier(db, supplier_id)
    roll_type = _resolve_roll_type(db, roll_type_id)
    source_enum = source if isinstance(source, DeliverySource) else DeliverySource(source)
    cleaned_note = (note or "").strip() or None
    idempotency_hash = hashlib.sha256(
        json.dumps(
            {
                "created_by": created_by,
                "delivery_date": delivery_date.isoformat(),
                "note": cleaned_note,
                "quantity_received": quantity_received,
                "roll_type_id": roll_type.id,
                "source": source_enum.value,
                "supplier_id": supplier.id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    if idempotency_key:
        existing = db.execute(
            select(Delivery).where(Delivery.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            if existing.idempotency_hash != idempotency_hash:
                raise ConflictError(
                    "This request key was already used for a different delivery",
                    code="idempotency_key_reused",
                )
            return existing

    delivery = Delivery(
        delivery_date=delivery_date,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        quantity_received=quantity_received,
        note=cleaned_note,
        created_by=created_by,
        source=source_enum,
        idempotency_key=idempotency_key,
        idempotency_hash=idempotency_hash if idempotency_key else None,
    )
    db.add(delivery)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if idempotency_key:
            existing = db.execute(
                select(Delivery).where(Delivery.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
            if existing is not None and existing.idempotency_hash == idempotency_hash:
                return existing
            if existing is not None:
                raise ConflictError(
                    "This request key was already used for a different delivery",
                    code="idempotency_key_reused",
                ) from exc
        raise
    audit_service.record(
        db,
        action="delivery.create",
        actor_user_id=created_by,
        entity_type="delivery",
        entity_id=delivery.id,
        details={
            "supplier_id": supplier_id,
            "roll_type_id": roll_type_id,
            "quantity_received": quantity_received,
            "delivery_date": delivery_date.isoformat(),
            "source": source_enum.value,
        },
        ip_address=ip_address,
    )
    return delivery


# --------------------------------------------------------------------------- #
# Read
# --------------------------------------------------------------------------- #
def get_delivery_row(db: Session, delivery_id: int) -> DeliveryRow:
    """A single delivery with its derived paid/unpaid quantities."""
    from sqlalchemy import func

    from app.services.queries import base_delivery_query

    stmt = base_delivery_query().where(Delivery.id == delivery_id)
    row = db.execute(stmt).first()
    if row is None:
        raise NotFoundError("Delivery not found", code="delivery_not_found")
    return DeliveryRow(delivery=row[0], paid_quantity=int(row[1] or 0))


def get_delivery(db: Session, delivery_id: int) -> Delivery:
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise NotFoundError("Delivery not found", code="delivery_not_found")
    return delivery


def list_deliveries(
    db: Session,
    *,
    supplier_id: int | None = None,
    roll_type_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    only_unpaid: bool = False,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[DeliveryRow], int]:
    validate_date_range(start_date, end_date)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    rows = fetch_delivery_rows(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
        only_unpaid=only_unpaid,
        order_desc=True,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    total = count_deliveries(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
        only_unpaid=only_unpaid,
    )
    return rows, total


def delivery_summary(
    db: Session,
    *,
    supplier_id: int | None = None,
    roll_type_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    rows = fetch_delivery_rows(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
    )
    totals = totals_for_rows(rows)
    by_roll_type = [
        {
            "roll_type_id": k[0],
            "roll_type_code": k[1],
            "roll_type_name": k[2],
            "roll_type_name_en": k[3],
            **v,
        }
        for k, v in group_rows_by(
            rows,
            lambda r: (
                r.delivery.roll_type_id,
                r.delivery.roll_type.code,
                r.delivery.roll_type.name_km,
                r.delivery.roll_type.name_en,
            ),
        ).items()
    ]
    by_roll_type.sort(key=lambda x: x["roll_type_name"])
    return {
        "totals": totals,
        "delivery_count": len(rows),
        "by_roll_type": by_roll_type,
    }


# --------------------------------------------------------------------------- #
# Update / delete (auditable corrections)
# --------------------------------------------------------------------------- #
def update_delivery(
    db: Session,
    *,
    delivery_id: int,
    actor_user_id: int,
    supplier_id: int | None = None,
    roll_type_id: int | None = None,
    quantity_received: int | None = None,
    delivery_date: date | None = None,
    note: str | None = None,
    note_provided: bool = False,
    ip_address: str | None = None,
) -> Delivery:
    delivery = db.execute(
        select(Delivery).where(Delivery.id == delivery_id).with_for_update(of=Delivery)
    ).scalar_one_or_none()
    if delivery is None:
        raise NotFoundError("Delivery not found", code="delivery_not_found")

    if supplier_id is not None and supplier_id != delivery.supplier_id:
        _resolve_supplier(db, supplier_id)
        if _allocated_quantity(db, delivery_id) > 0:
            raise ConflictError(
                "This delivery already has payments recorded; the supplier cannot be changed. "
                "Reverse the payment first.",
                code="delivery_has_payments",
            )
        delivery.supplier_id = supplier_id

    if roll_type_id is not None and roll_type_id != delivery.roll_type_id:
        _resolve_roll_type(db, roll_type_id)
        delivery.roll_type_id = roll_type_id

    if quantity_received is not None:
        quantity_received = _validate_quantity(quantity_received)
        allocated = _allocated_quantity(db, delivery_id)
        if quantity_received < allocated:
            raise ValidationError(
                f"{allocated} rolls of this delivery are already paid; the received quantity "
                f"cannot be lower than that.",
                code="quantity_below_allocated",
                details={"allocated": allocated, "requested": quantity_received},
            )
        delivery.quantity_received = quantity_received

    if delivery_date is not None:
        delivery.delivery_date = _validate_delivery_date(delivery_date)

    if note_provided:
        delivery.note = (note or "").strip() or None

    delivery.updated_by = actor_user_id
    db.flush()
    audit_service.record(
        db,
        action="delivery.update",
        actor_user_id=actor_user_id,
        entity_type="delivery",
        entity_id=delivery.id,
        details={
            "delivery_date": delivery.delivery_date.isoformat(),
            "supplier_id": delivery.supplier_id,
            "roll_type_id": delivery.roll_type_id,
            "quantity_received": delivery.quantity_received,
        },
        ip_address=ip_address,
    )
    return delivery


def _allocated_quantity(db: Session, delivery_id: int, *, exclude_payment_id: int | None = None) -> int:
    from sqlalchemy import func

    from app.models.payment import Payment

    stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.quantity_paid), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.delivery_id == delivery_id, Payment.reversed_at.is_(None))
    )
    if exclude_payment_id is not None:
        stmt = stmt.where(PaymentAllocation.payment_id != exclude_payment_id)
    return int(db.execute(stmt).scalar_one())


def delete_delivery(
    db: Session, *, delivery_id: int, actor_user_id: int, ip_address: str | None = None
) -> None:
    delivery = db.execute(
        select(Delivery).where(Delivery.id == delivery_id).with_for_update(of=Delivery)
    ).scalar_one_or_none()
    if delivery is None:
        raise NotFoundError("Delivery not found", code="delivery_not_found")
    if _allocated_quantity(db, delivery_id) > 0:
        raise ConflictError(
            "This delivery has payments recorded and cannot be deleted. "
            "Reverse the payment first if it was a mistake.",
            code="delivery_has_payments",
        )
    audit_service.record(
        db,
        action="delivery.delete",
        actor_user_id=actor_user_id,
        entity_type="delivery",
        entity_id=delivery.id,
        details={
            "supplier_id": delivery.supplier_id,
            "roll_type_id": delivery.roll_type_id,
            "quantity_received": delivery.quantity_received,
            "delivery_date": delivery.delivery_date.isoformat(),
        },
        ip_address=ip_address,
    )
    db.delete(delivery)
    db.flush()


def recent_deliveries(db: Session, *, limit: int = 5) -> list[DeliveryRow]:
    return fetch_delivery_rows(db, order_desc=True, limit=limit)
