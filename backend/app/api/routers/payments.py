"""Unpaid calculation, payment preview, confirmation and paid history.

The server always recalculates eligibility; a total sent by the browser or by the
Telegram bot is never trusted.  Confirmation runs in one locked transaction so
the same rolls can never be paid twice.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, requires
from app.api.serializers import delivery_row_payload
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import Page
from app.schemas.payment import (
    PaymentConfirmRequest,
    PaymentDetailOut,
    PaymentOut,
    PaymentReversalRequest,
    UnpaidPreviewOut,
)
from app.services import delivery_service, payment_service

router = APIRouter(prefix="/api/payments", tags=["payments"])


# --------------------------------------------------------------------------- #
# Unpaid view (read-only)
# --------------------------------------------------------------------------- #
@router.get("/unpaid", response_model=UnpaidPreviewOut)
def unpaid(
    supplier_id: int = Query(..., description="Supplier whose unpaid rolls to show"),
    start_date: date | None = Query(default=None, description="Delivery date >= (inclusive)"),
    end_date: date | None = Query(default=None, description="Delivery date <= (inclusive)"),
    roll_type_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Unpaid quantity for a supplier over a *delivery-date* range.

    This is the same calculation the payment preview uses, so the number the user
    reads on the Unpaid page is exactly the number that will be paid.
    """
    return payment_service.preview_payment(
        db,
        supplier_id=supplier_id,
        start_date=start_date,
        end_date=end_date,
        roll_type_id=roll_type_id,
    )


@router.get("/unpaid/all", response_model=Page[dict])
def unpaid_deliveries(
    supplier_id: int | None = Query(default=None),
    roll_type_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Paged list of every delivery that still has an unpaid remainder."""
    rows, total = delivery_service.list_deliveries(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
        only_unpaid=True,
        page=page,
        page_size=page_size,
    )
    return Page.build(
        [delivery_row_payload(r) for r in rows], total=total, page=page, page_size=page_size
    )


# --------------------------------------------------------------------------- #
# Confirm
# --------------------------------------------------------------------------- #
@router.post("/confirm", response_model=PaymentDetailOut, status_code=201)
def confirm_payment(
    payload: PaymentConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_confirm_payments")),
) -> dict:
    allocation_dicts = (
        [{"delivery_id": a.delivery_id, "quantity": a.quantity} for a in payload.allocations]
        if payload.allocations
        else None
    )
    payment = payment_service.confirm_payment(
        db,
        supplier_id=payload.supplier_id,
        roll_type_id=payload.roll_type_id,
        actor_user_id=actor.id,
        payment_date=payload.payment_date,
        note=payload.note,
        start_date=payload.start_date,
        end_date=payload.end_date,
        allocations=allocation_dicts,
        idempotency_key=payload.idempotency_key,
        ip_address=client_ip(request),
    )
    return payment_service.payment_detail(db, payment.id)


# --------------------------------------------------------------------------- #
# Paid history
# --------------------------------------------------------------------------- #
@router.get("", response_model=Page[PaymentOut])
def list_payments(
    supplier_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None, description="Payment date >="),
    end_date: date | None = Query(default=None, description="Payment date <="),
    delivery_start_date: date | None = Query(default=None, description="Original delivery date >="),
    delivery_end_date: date | None = Query(default=None, description="Original delivery date <="),
    roll_type_id: int | None = Query(default=None),
    include_reversed: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    items, total = payment_service.list_payments(
        db,
        supplier_id=supplier_id,
        start_date=start_date,
        end_date=end_date,
        delivery_start_date=delivery_start_date,
        delivery_end_date=delivery_end_date,
        roll_type_id=roll_type_id,
        include_reversed=include_reversed,
        page=page,
        page_size=page_size,
    )
    return Page.build(items, total=total, page=page, page_size=page_size)


@router.get("/{payment_id}", response_model=PaymentDetailOut)
def payment_detail(
    payment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """A payment plus the individual deliveries it covers."""
    return payment_service.payment_detail(db, payment_id)


@router.post("/{payment_id}/reverse", response_model=PaymentDetailOut)
def reverse_payment(
    payment_id: int,
    payload: PaymentReversalRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_reverse_payments")),
) -> dict:
    """Auditable correction.

    The original payment record is preserved; it is marked reversed and its
    quantities become unpaid again.  History is never silently rewritten.
    """
    payment_service.reverse_payment(
        db,
        payment_id=payment_id,
        reason=payload.reason,
        actor_user_id=actor.id,
        ip_address=client_ip(request),
    )
    return payment_service.payment_detail(db, payment_id)
