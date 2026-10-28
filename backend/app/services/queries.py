"""Shared inventory queries.

**This module is the single source of truth for paid / unpaid quantities.**

A delivery's paid quantity is always ``SUM(payment_allocations.quantity_paid)``
over payments that have not been reversed; the unpaid quantity is always
``quantity_received - paid``.  Nothing else in the system is allowed to store or
recompute these totals differently - the web API, the dashboard and the Telegram
bot all call into these helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.delivery import Delivery
from app.models.enums import DeliveryStatus
from app.models.payment import Payment, PaymentAllocation


def paid_totals_subquery():
    """``delivery_id -> paid_quantity`` for non-reversed payments."""
    return (
        select(
            PaymentAllocation.delivery_id.label("delivery_id"),
            func.coalesce(func.sum(PaymentAllocation.quantity_paid), 0).label("paid_quantity"),
        )
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(Payment.reversed_at.is_(None))
        .group_by(PaymentAllocation.delivery_id)
        .subquery("paid_totals")
    )


@dataclass(slots=True)
class DeliveryRow:
    """A delivery together with its derived payment status."""

    delivery: Delivery
    paid_quantity: int

    @property
    def id(self) -> int:
        return self.delivery.id

    @property
    def quantity_received(self) -> int:
        return self.delivery.quantity_received

    @property
    def unpaid_quantity(self) -> int:
        return self.delivery.quantity_received - self.paid_quantity

    @property
    def status(self) -> DeliveryStatus:
        if self.paid_quantity <= 0:
            return DeliveryStatus.unpaid
        if self.paid_quantity >= self.delivery.quantity_received:
            return DeliveryStatus.paid
        return DeliveryStatus.partial


def validate_date_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise ValidationError("The start date must not be after the end date", code="invalid_date_range")


def base_delivery_query() -> Select:
    """Deliveries joined with their paid totals (outer join keeps fully unpaid rows)."""
    paid = paid_totals_subquery()
    return (
        select(Delivery, func.coalesce(paid.c.paid_quantity, 0).label("paid_quantity"))
        .outerjoin(paid, paid.c.delivery_id == Delivery.id)
    )


def apply_delivery_filters(
    stmt: Select,
    *,
    supplier_id: int | None = None,
    roll_type_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Select:
    if supplier_id is not None:
        stmt = stmt.where(Delivery.supplier_id == supplier_id)
    if roll_type_id is not None:
        stmt = stmt.where(Delivery.roll_type_id == roll_type_id)
    if start_date is not None:
        stmt = stmt.where(Delivery.delivery_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Delivery.delivery_date <= end_date)
    return stmt


def fetch_delivery_rows(
    db: Session,
    *,
    supplier_id: int | None = None,
    roll_type_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    only_unpaid: bool = False,
    order_desc: bool = True,
    limit: int | None = None,
    offset: int | None = None,
) -> list[DeliveryRow]:
    validate_date_range(start_date, end_date)
    stmt = apply_delivery_filters(
        base_delivery_query(),
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
    )
    if only_unpaid:
        stmt = stmt.where(
            Delivery.quantity_received > stmt.selected_columns["paid_quantity"]
        )
    stmt = stmt.order_by(
        Delivery.delivery_date.desc() if order_desc else Delivery.delivery_date.asc(),
        Delivery.id.desc() if order_desc else Delivery.id.asc(),
    )
    if offset is not None:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)

    return [DeliveryRow(delivery=row[0], paid_quantity=int(row[1])) for row in db.execute(stmt).all()]


def count_deliveries(
    db: Session,
    *,
    supplier_id: int | None = None,
    roll_type_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    only_unpaid: bool = False,
) -> int:
    stmt = apply_delivery_filters(
        select(func.count(Delivery.id)),
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
    )
    if only_unpaid:
        paid = paid_totals_subquery()
        stmt = stmt.outerjoin(paid, paid.c.delivery_id == Delivery.id).where(
            Delivery.quantity_received > func.coalesce(paid.c.paid_quantity, 0)
        )
    return int(db.execute(stmt).scalar_one())


def totals_for_rows(rows: list[DeliveryRow]) -> dict[str, int]:
    received = sum(r.quantity_received for r in rows)
    paid = sum(r.paid_quantity for r in rows)
    return {"received": received, "paid": paid, "unpaid": received - paid}


def group_rows_by(rows: list[DeliveryRow], key) -> dict:
    grouped: dict = {}
    for row in rows:
        k = key(row)
        bucket = grouped.setdefault(k, {"received": 0, "paid": 0, "unpaid": 0, "count": 0})
        bucket["received"] += row.quantity_received
        bucket["paid"] += row.paid_quantity
        bucket["unpaid"] += row.unpaid_quantity
        bucket["count"] += 1
    return grouped


def locked_deliveries(db: Session, delivery_ids: list[int]) -> dict[int, Delivery]:
    """``SELECT ... FOR UPDATE`` the given deliveries.

    Serialises concurrent payment confirmations so two users can never allocate
    the same unpaid quantity twice.
    """
    if not delivery_ids:
        return {}
    stmt = (
        select(Delivery)
        .where(Delivery.id.in_(sorted(set(delivery_ids))))
        .order_by(Delivery.id)
        .with_for_update(of=Delivery)
    )
    return {d.id: d for d in db.execute(stmt).scalars().all()}


def paid_quantities_for(db: Session, delivery_ids: list[int]) -> dict[int, int]:
    """Re-read paid totals *after* the rows are locked."""
    if not delivery_ids:
        return {}
    paid = paid_totals_subquery()
    stmt = (
        select(paid.c.delivery_id, paid.c.paid_quantity)
        .select_from(paid)
        .where(paid.c.delivery_id.in_(delivery_ids))
    )
    return {int(r[0]): int(r[1]) for r in db.execute(stmt).all()}
