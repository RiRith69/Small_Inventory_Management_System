"""Payment preview, confirmation, history and auditable reversal.

Design rules implemented here
-----------------------------
* A payment records *that a quantity of rolls has been paid for*.  No money.
* Eligibility is always recalculated on the server; client-supplied totals are
  never trusted.
* The whole confirmation runs in one database transaction with the affected
  delivery rows locked (``SELECT ... FOR UPDATE``), so two users can never pay
  the same quantity twice.
* Allocations may be partial: ``quantity_paid`` may be less than
  ``quantity_received``; the remainder stays unpaid.
* Payments are never deleted - mistakes are corrected with an audited reversal
  which restores the unpaid quantity while preserving the original record.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import generate_payment_reference
from app.core.timezone import local_today, now_utc
from app.models.catalog import RollType, Supplier
from app.models.delivery import Delivery
from app.models.payment import Payment, PaymentAllocation
from app.services import audit_service
from app.services.queries import (
    DeliveryRow,
    fetch_delivery_rows,
    locked_deliveries,
    paid_quantities_for,
    totals_for_rows,
    validate_date_range,
)

logger = logging.getLogger("app.payments")

MAX_FUTURE_PAYMENT_DAYS = 365


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _validate_payment_date(d: date) -> date:
    if d is None:
        raise ValidationError("Payment date is required")
    if d < date(2000, 1, 1):
        raise ValidationError("Payment date is unrealistically far in the past", code="invalid_date")
    if d > local_today() + timedelta(days=MAX_FUTURE_PAYMENT_DAYS):
        raise ValidationError("Payment date is unrealistically far in the future", code="invalid_date")
    return d


def _supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found", code="supplier_not_found")
    return supplier


def row_to_dict(row: DeliveryRow) -> dict:
    d = row.delivery
    return {
        "id": d.id,
        "delivery_date": d.delivery_date,
        "supplier_id": d.supplier_id,
        "supplier_name": d.supplier.name if d.supplier else None,
        "roll_type_id": d.roll_type_id,
        "roll_type_name": d.roll_type.name_km if d.roll_type else None,
        "roll_type_name_km": d.roll_type.name_km if d.roll_type else None,
        "roll_type_name_en": d.roll_type.name_en if d.roll_type else None,
        "roll_type_code": d.roll_type.code if d.roll_type else None,
        "quantity_received": row.quantity_received,
        "quantity_paid": row.paid_quantity,
        "quantity_unpaid": row.unpaid_quantity,
        "status": row.status.value,
        "note": d.note,
    }


# --------------------------------------------------------------------------- #
# Preview (read-only)
# --------------------------------------------------------------------------- #
def preview_payment(
    db: Session,
    *,
    supplier_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    roll_type_id: int | None = None,
) -> dict:
    """Eligible unpaid deliveries for a supplier and delivery-date range."""
    validate_date_range(start_date, end_date)
    supplier = _supplier(db, supplier_id)

    rows = fetch_delivery_rows(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
        only_unpaid=True,
        order_desc=False,
    )
    all_rows = fetch_delivery_rows(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
        order_desc=False,
    )
    totals = totals_for_rows(all_rows)
    breakdown: dict[tuple[int, str], dict] = {}
    for row in all_rows:
        roll_type = row.delivery.roll_type
        key = (row.delivery.roll_type_id, roll_type.name_km if roll_type else "")
        bucket = breakdown.setdefault(
            key,
            {
                "roll_type_id": key[0],
                "roll_type_code": roll_type.code if roll_type else "",
                "roll_type_name": key[1],
                "roll_type_name_en": roll_type.name_en if roll_type else "",
                "received": 0,
                "paid": 0,
                "unpaid": 0,
                "quantity_unpaid": 0,
                "delivery_count": 0,
            },
        )
        bucket["received"] += row.quantity_received
        bucket["paid"] += row.paid_quantity
        bucket["unpaid"] += row.unpaid_quantity
        bucket["quantity_unpaid"] += row.unpaid_quantity
        bucket["delivery_count"] += 1

    delivery_dates = sorted({row.delivery.delivery_date for row in rows})

    return {
        "supplier": {"id": supplier.id, "name": supplier.name},
        "start_date": start_date,
        "end_date": end_date,
        "deliveries": [row_to_dict(r) for r in rows],
        "totals": totals,
        "by_roll_type": sorted(breakdown.values(), key=lambda x: x["roll_type_name"]),
        "delivery_dates": delivery_dates,
        "delivery_count": len(rows),
    }


# --------------------------------------------------------------------------- #
# Confirm (atomic, locked)
# --------------------------------------------------------------------------- #
def confirm_payment(
    db: Session,
    *,
    supplier_id: int,
    roll_type_id: int | None = None,
    actor_user_id: int,
    payment_date: date | None = None,
    note: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    allocations: list[dict] | None = None,
    idempotency_key: str | None = None,
    ip_address: str | None = None,
) -> Payment:
    """Create a payment covering the remaining unpaid quantity of deliveries.

    ``allocations`` = explicit mode: ``[{"delivery_id": 1, "quantity": 6}, ...]``
    (used for partial payments and for paying a delivery outside the selected
    range - the authorised alternative workflow).

    Without ``allocations`` the server pays the *full remaining unpaid* quantity
    of every delivery matching the supplier, roll type, and delivery-date range.
    """
    validate_date_range(start_date, end_date)

    _supplier(db, supplier_id)
    payment_date = _validate_payment_date(payment_date or local_today())

    # --- 1. determine the candidate deliveries ---------------------------
    if allocations:
        explicit: dict[int, int] = {}
        for item in allocations:
            delivery_id = int(item["delivery_id"])
            quantity = int(item["quantity"])
            if delivery_id in explicit:
                raise ValidationError(
                    "The same delivery appears twice in this payment",
                    code="duplicate_delivery_in_request",
                )
            if quantity <= 0:
                raise ValidationError("Each quantity must be greater than zero", code="invalid_quantity")
            explicit[delivery_id] = quantity
        candidate_ids = list(explicit.keys())
    else:
        candidate_ids = [
            row.id
            for row in fetch_delivery_rows(
                db,
                supplier_id=supplier_id,
                roll_type_id=roll_type_id,
                start_date=start_date,
                end_date=end_date,
                order_desc=False,
            )
        ]

    if not candidate_ids:
        raise ConflictError("There are no deliveries in the selected range to pay", code="nothing_to_pay")

    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "actor_user_id": actor_user_id,
                "allocations": sorted(plan for plan in explicit.items()) if allocations else None,
                "end_date": end_date.isoformat() if end_date else None,
                "note": (note or "").strip() or None,
                "payment_date": payment_date.isoformat(),
                "roll_type_id": roll_type_id,
                "start_date": start_date.isoformat() if start_date else None,
                "supplier_id": supplier_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    if idempotency_key:
        existing = db.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            if existing.idempotency_hash != fingerprint:
                raise ConflictError(
                    "This request key was already used for a different payment",
                    code="idempotency_key_reused",
                )
            logger.info("Idempotent payment replay for reference=%s", existing.reference)
            return existing

    # --- 2. lock the delivery rows (serialises concurrent confirmations) --
    locked = locked_deliveries(db, candidate_ids)
    if idempotency_key:
        existing = db.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            if existing.idempotency_hash != fingerprint:
                raise ConflictError(
                    "This request key was already used for a different payment",
                    code="idempotency_key_reused",
                )
            logger.info("Idempotent payment replay after lock for reference=%s", existing.reference)
            return existing

    missing = [i for i in candidate_ids if i not in locked]
    if missing:
        raise NotFoundError(
            "One or more deliveries no longer exist", code="delivery_not_found", details={"ids": missing}
        )

    for delivery_id, delivery in locked.items():
        if delivery.supplier_id != supplier_id:
            raise ValidationError(
                "A delivery from a different supplier was included in this payment",
                code="supplier_mismatch",
                details={"delivery_id": delivery_id},
            )
        if roll_type_id is not None and delivery.roll_type_id != roll_type_id:
            raise ValidationError(
                "A delivery from a different roll type was included in this payment",
                code="roll_type_mismatch",
                details={"delivery_id": delivery_id},
            )

    # --- 3. recompute remaining unpaid AFTER the lock --------------------
    paid_map = paid_quantities_for(db, candidate_ids)

    plan: list[tuple[int, int]] = []
    if allocations:
        for delivery_id, quantity in explicit.items():
            delivery = locked[delivery_id]
            remaining = delivery.quantity_received - paid_map.get(delivery_id, 0)
            if quantity > remaining:
                raise ConflictError(
                    f"Only {remaining} roll(s) of that delivery are still unpaid",
                    code="exceeds_unpaid_quantity",
                    details={"delivery_id": delivery_id, "requested": quantity, "remaining": remaining},
                )
            plan.append((delivery_id, quantity))
    else:
        for delivery_id, delivery in locked.items():
            remaining = delivery.quantity_received - paid_map.get(delivery_id, 0)
            if remaining > 0:
                plan.append((delivery_id, remaining))

    if not plan:
        raise ConflictError(
            "All selected deliveries have already been paid", code="nothing_to_pay"
        )

    plan_roll_types = {locked[delivery_id].roll_type_id for delivery_id, _ in plan}
    if len(plan_roll_types) > 1:
        raise ValidationError(
            "A payment can only allocate deliveries of one roll type",
            code="mixed_roll_types_in_payment",
        )

    total_quantity = sum(q for _, q in plan)

    # --- 4. persist atomically -------------------------------------------
    payment = Payment(
        reference=generate_payment_reference(payment_date),
        supplier_id=supplier_id,
        payment_date=payment_date,
        note=(note or "").strip() or None,
        created_by=actor_user_id,
        idempotency_key=idempotency_key,
        idempotency_hash=fingerprint if idempotency_key else None,
    )
    db.add(payment)
    db.flush()

    for delivery_id, quantity in plan:
        db.add(
            PaymentAllocation(payment_id=payment.id, delivery_id=delivery_id, quantity_paid=quantity)
        )

    try:
        db.flush()
    except IntegrityError as exc:  # pragma: no cover - safety net
        db.rollback()
        if idempotency_key:
            existing = db.execute(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
            if existing is not None and existing.idempotency_hash == fingerprint:
                logger.info("Concurrent idempotent payment replay for reference=%s", existing.reference)
                return existing
            if existing is not None:
                raise ConflictError(
                    "This request key was already used for a different payment",
                    code="idempotency_key_reused",
                ) from exc
        logger.warning("Payment allocation rejected by database guard: %s", exc)
        raise ConflictError(
            "These rolls have just been paid by someone else. Please reload and try again.",
            code="allocation_conflict",
        ) from exc

    audit_service.record(
        db,
        action="payment.confirm",
        actor_user_id=actor_user_id,
        entity_type="payment",
        entity_id=payment.id,
        details={
            "reference": payment.reference,
            "supplier_id": supplier_id,
            "payment_date": payment_date.isoformat(),
            "total_quantity": total_quantity,
            "delivery_ids": [d for d, _ in plan],
        },
        ip_address=ip_address,
    )
    return payment


# --------------------------------------------------------------------------- #
# History / detail
# --------------------------------------------------------------------------- #
def _roll_type_breakdown(db: Session, payment_ids: list[int]) -> dict[int, list[dict]]:
    if not payment_ids:
        return {}
    stmt = (
        select(
            PaymentAllocation.payment_id,
            Delivery.roll_type_id,
            RollType.code,
            RollType.name_km,
            RollType.name_en,
            func.coalesce(func.sum(PaymentAllocation.quantity_paid), 0),
        )
        .join(Delivery, Delivery.id == PaymentAllocation.delivery_id)
        .join(RollType, RollType.id == Delivery.roll_type_id)
        .where(PaymentAllocation.payment_id.in_(payment_ids))
        .group_by(
            PaymentAllocation.payment_id,
            Delivery.roll_type_id,
            RollType.code,
            RollType.name_km,
            RollType.name_en,
        )
    )
    out: dict[int, list[dict]] = {}
    for payment_id, roll_type_id, code, name_km, name_en, qty in db.execute(stmt).all():
        out.setdefault(int(payment_id), []).append(
            {
                "roll_type_id": int(roll_type_id),
                "roll_type_code": code,
                "roll_type_name": name_km,
                "roll_type_name_km": name_km,
                "roll_type_name_en": name_en,
                "quantity": int(qty),
            }
        )
    for items in out.values():
        items.sort(key=lambda x: x["roll_type_name"])
    return out


def _delivery_date_span(db: Session, payment_ids: list[int]) -> dict[int, tuple[date, date]]:
    if not payment_ids:
        return {}
    stmt = (
        select(
            PaymentAllocation.payment_id,
            func.min(Delivery.delivery_date),
            func.max(Delivery.delivery_date),
        )
        .join(Delivery, Delivery.id == PaymentAllocation.delivery_id)
        .where(PaymentAllocation.payment_id.in_(payment_ids))
        .group_by(PaymentAllocation.payment_id)
    )
    return {int(r[0]): (r[1], r[2]) for r in db.execute(stmt).all()}


def list_payments(
    db: Session,
    *,
    supplier_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    delivery_start_date: date | None = None,
    delivery_end_date: date | None = None,
    roll_type_id: int | None = None,
    include_reversed: bool = True,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[dict], int]:
    """Paid history, filtered by payment date and/or original delivery date."""
    validate_date_range(start_date, end_date)
    validate_date_range(delivery_start_date, delivery_end_date)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    total_alloc = (
        select(
            PaymentAllocation.payment_id.label("payment_id"),
            func.coalesce(func.sum(PaymentAllocation.quantity_paid), 0).label("total_quantity"),
        )
        .group_by(PaymentAllocation.payment_id)
        .subquery()
    )

    conditions = []
    if supplier_id is not None:
        conditions.append(Payment.supplier_id == supplier_id)
    if start_date is not None:
        conditions.append(Payment.payment_date >= start_date)
    if end_date is not None:
        conditions.append(Payment.payment_date <= end_date)
    if not include_reversed:
        conditions.append(Payment.reversed_at.is_(None))

    if roll_type_id is not None or delivery_start_date is not None or delivery_end_date is not None:
        sub = [PaymentAllocation.payment_id == Payment.id]
        if roll_type_id is not None:
            sub.append(Delivery.roll_type_id == roll_type_id)
        if delivery_start_date is not None:
            sub.append(Delivery.delivery_date >= delivery_start_date)
        if delivery_end_date is not None:
            sub.append(Delivery.delivery_date <= delivery_end_date)
        conditions.append(
            exists(
                select(1)
                .select_from(PaymentAllocation)
                .join(Delivery, Delivery.id == PaymentAllocation.delivery_id)
                .where(*sub)
            )
        )

    total = int(
        db.execute(select(func.count(Payment.id)).where(*conditions)).scalar_one()
    )
    id_stmt = (
        select(Payment.id)
        .where(*conditions)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    page_ids = [int(r[0]) for r in db.execute(id_stmt).all()]

    if not page_ids:
        return [], total

    payments = {
        p.id: p
        for p in db.execute(select(Payment).where(Payment.id.in_(page_ids))).scalars().all()
    }
    totals = {
        int(r[0]): int(r[1])
        for r in db.execute(
            select(total_alloc.c.payment_id, total_alloc.c.total_quantity).where(
                total_alloc.c.payment_id.in_(page_ids)
            )
        ).all()
    }
    breakdowns = _roll_type_breakdown(db, page_ids)
    spans = _delivery_date_span(db, page_ids)

    items = []
    for pid in page_ids:
        payment = payments[pid]
        span = spans.get(pid)
        items.append(
            {
                "id": payment.id,
                "reference": payment.reference,
                "supplier_id": payment.supplier_id,
                "supplier_name": payment.supplier.name if payment.supplier else None,
                "payment_date": payment.payment_date,
                "total_quantity": totals.get(pid, 0),
                "note": payment.note,
                "created_by": payment.created_by,
                "created_by_username": payment.creator.username if payment.creator else None,
                "created_at": payment.created_at,
                "is_reversed": payment.reversed_at is not None,
                "reversed_at": payment.reversed_at,
                "reversal_reason": payment.reversal_reason,
                "delivery_date_from": span[0] if span else None,
                "delivery_date_to": span[1] if span else None,
                "roll_type_breakdown": breakdowns.get(pid, []),
            }
        )
    return items, total


def payment_detail(db: Session, payment_id: int) -> dict:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found", code="payment_not_found")

    allocs = (
        db.execute(
            select(PaymentAllocation)
            .where(PaymentAllocation.payment_id == payment_id)
            .order_by(PaymentAllocation.id)
        )
        .scalars()
        .all()
    )
    delivery_ids = [a.delivery_id for a in allocs]
    deliveries = {
        d.id: d
        for d in db.execute(select(Delivery).where(Delivery.id.in_(delivery_ids))).scalars().all()
    } if delivery_ids else {}

    items = []
    for a in allocs:
        d = deliveries.get(a.delivery_id)
        if d is None:  # defensive: delivery removed is impossible (RESTRICT)
            continue
        items.append(
            {
                "allocation_id": a.id,
                "delivery_id": d.id,
                "delivery_date": d.delivery_date,
                "roll_type_id": d.roll_type_id,
                "roll_type_name": d.roll_type.name_km if d.roll_type else None,
                "roll_type_name_km": d.roll_type.name_km if d.roll_type else None,
                "roll_type_name_en": d.roll_type.name_en if d.roll_type else None,
                "roll_type_code": d.roll_type.code if d.roll_type else None,
                "quantity_paid": a.quantity_paid,
                "quantity_received": d.quantity_received,
            }
        )

    breakdown: dict[tuple[int, str], int] = {}
    for item in items:
        key = (item["roll_type_id"], item["roll_type_name"] or "")
        breakdown[key] = breakdown.get(key, 0) + item["quantity_paid"]

    dates = sorted({i["delivery_date"] for i in items})
    return {
        "id": payment.id,
        "reference": payment.reference,
        "supplier_id": payment.supplier_id,
        "supplier_name": payment.supplier.name if payment.supplier else None,
        "payment_date": payment.payment_date,
        "note": payment.note,
        "created_by": payment.created_by,
        "created_by_username": payment.creator.username if payment.creator else None,
        "created_at": payment.created_at,
        "is_reversed": payment.reversed_at is not None,
        "reversed_at": payment.reversed_at,
        "reversal_reason": payment.reversal_reason,
        "total_quantity": sum(i["quantity_paid"] for i in items),
        "delivery_date_from": dates[0] if dates else None,
        "delivery_date_to": dates[-1] if dates else None,
        "allocations": items,
        "roll_type_breakdown": [
            {
                "roll_type_id": k[0],
                "roll_type_code": next(
                    (item["roll_type_code"] for item in items if item["roll_type_id"] == k[0]),
                    None,
                ),
                "roll_type_name": k[1],
                "roll_type_name_km": k[1],
                "roll_type_name_en": next(
                    (item["roll_type_name_en"] for item in items if item["roll_type_id"] == k[0]),
                    None,
                ),
                "quantity": v,
            }
            for k, v in sorted(breakdown.items(), key=lambda x: x[0][1])
        ],
    }


# --------------------------------------------------------------------------- #
# Reversal (auditable correction - never deletes anything)
# --------------------------------------------------------------------------- #
def reverse_payment(
    db: Session,
    *,
    payment_id: int,
    reason: str,
    actor_user_id: int,
    ip_address: str | None = None,
) -> Payment:
    payment = db.execute(
        select(Payment).where(Payment.id == payment_id).with_for_update(of=Payment)
    ).scalar_one_or_none()
    if payment is None:
        raise NotFoundError("Payment not found", code="payment_not_found")
    if payment.reversed_at is not None:
        raise ConflictError("This payment has already been reversed", code="already_reversed")

    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ValidationError("A reason is required to reverse a payment", code="reason_required")

    # Lock the affected deliveries so a concurrent payment cannot race us.
    allocation_ids = [
        int(r[0])
        for r in db.execute(
            select(PaymentAllocation.delivery_id).where(PaymentAllocation.payment_id == payment_id)
        ).all()
    ]
    locked_deliveries(db, allocation_ids)

    payment.reversed_at = now_utc()
    payment.reversed_by = actor_user_id
    payment.reversal_reason = reason
    db.flush()

    audit_service.record(
        db,
        action="payment.reverse",
        actor_user_id=actor_user_id,
        entity_type="payment",
        entity_id=payment.id,
        details={"reference": payment.reference, "reason": reason, "delivery_ids": allocation_ids},
        ip_address=ip_address,
    )
    return payment


def recent_payments(db: Session, *, limit: int = 5) -> list[dict]:
    items, _ = list_payments(db, page=1, page_size=limit, include_reversed=True)
    return items
