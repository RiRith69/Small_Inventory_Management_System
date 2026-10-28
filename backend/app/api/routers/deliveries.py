"""Daily deliveries: record, list/filter, summarise and correct.

Deliveries are the permanent record of what was received.  Marking rolls as paid
never modifies them.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, requires
from app.api.serializers import delivery_row_payload
from app.database.session import get_db
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.delivery import (
    DeliveryCreate,
    DeliveryOut,
    DeliverySummaryOut,
    DeliveryUpdate,
)
from app.services import delivery_service

router = APIRouter(prefix="/api/deliveries", tags=["deliveries"])


@router.post("", response_model=DeliveryOut, status_code=201)
def create_delivery(
    payload: DeliveryCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_record_deliveries")),
) -> dict:
    """Record an incoming delivery.  ``delivery_date`` defaults to today (Cambodia)."""
    delivery = delivery_service.create_delivery(
        db,
        supplier_id=payload.supplier_id,
        roll_type_id=payload.roll_type_id,
        quantity_received=payload.quantity_received,
        delivery_date=payload.delivery_date,
        note=payload.note,
        created_by=actor.id,
        idempotency_key=payload.idempotency_key,
        ip_address=client_ip(request),
    )
    return delivery_payload_for(db, delivery.id)


@router.get("", response_model=Page[DeliveryOut])
def list_deliveries(
    supplier_id: int | None = Query(default=None),
    roll_type_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None, description="Delivery date >= (inclusive)"),
    end_date: date | None = Query(default=None, description="Delivery date <= (inclusive)"),
    only_unpaid: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    rows, total = delivery_service.list_deliveries(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
        only_unpaid=only_unpaid,
        page=page,
        page_size=page_size,
    )
    return Page.build(
        [delivery_row_payload(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get("/summary", response_model=DeliverySummaryOut)
def delivery_summary(
    supplier_id: int | None = Query(default=None),
    roll_type_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Totals for the current filter - the number the user reads off the screen."""
    return delivery_service.delivery_summary(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{delivery_id}", response_model=DeliveryOut)
def get_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return delivery_payload_for(db, delivery_id)


@router.patch("/{delivery_id}", response_model=DeliveryOut)
def update_delivery(
    delivery_id: int,
    payload: DeliveryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_edit_deliveries")),
) -> dict:
    """Correct a delivery.  A delivery that already has payments cannot move to
    another supplier, and its quantity cannot drop below the paid quantity."""
    delivery_service.update_delivery(
        db,
        delivery_id=delivery_id,
        actor_user_id=actor.id,
        supplier_id=payload.supplier_id,
        roll_type_id=payload.roll_type_id,
        quantity_received=payload.quantity_received,
        delivery_date=payload.delivery_date,
        note=payload.note,
        note_provided="note" in payload.model_fields_set,
        ip_address=client_ip(request),
    )
    return delivery_payload_for(db, delivery_id)


@router.delete("/{delivery_id}", response_model=Message)
def delete_delivery(
    delivery_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_delete_deliveries")),
) -> Message:
    """Delete a delivery that has no payments.  Allowed only for correction of
    mistakes - anything already paid must be reversed first."""
    delivery_service.delete_delivery(
        db, delivery_id=delivery_id, actor_user_id=actor.id, ip_address=client_ip(request)
    )
    return Message(message="Delivery deleted")


def delivery_payload_for(db: Session, delivery_id: int) -> dict:
    """Re-read a single delivery with its derived paid/unpaid quantities."""
    row = delivery_service.get_delivery_row(db, delivery_id)
    return delivery_row_payload(row)
