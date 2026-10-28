"""Convert ORM objects / service results into API payloads.

Keeping this in one place guarantees the web API and the Telegram bot describe
the same data in the same shape.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.delivery import Delivery
from app.models.user import User, UserSession
from app.schemas.delivery import DeliveryOut
from app.services import settings_service, telegram_service
from app.services.queries import DeliveryRow


def user_payload(db: Session, user: User, session: UserSession | None = None) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "permissions": settings_service.permissions_for(db, user),
        "telegram": telegram_service.link_status(db, user.id),
        "csrf_token": session.csrf_token if session else None,
    }


def delivery_payload(delivery: Delivery, *, paid_quantity: int | None = None) -> dict:
    if paid_quantity is None:
        paid_quantity = sum(
            a.quantity_paid for a in delivery.allocations if a.payment and not a.payment.is_reversed
        )
    unpaid = delivery.quantity_received - paid_quantity
    if paid_quantity <= 0:
        status = "unpaid"
    elif paid_quantity >= delivery.quantity_received:
        status = "paid"
    else:
        status = "partial"

    return {
        "id": delivery.id,
        "delivery_date": delivery.delivery_date,
        "supplier_id": delivery.supplier_id,
        "supplier_name": delivery.supplier.name if delivery.supplier else None,
        "roll_type_id": delivery.roll_type_id,
        "roll_type_name": delivery.roll_type.name_km if delivery.roll_type else None,
        "roll_type_name_km": delivery.roll_type.name_km if delivery.roll_type else None,
        "roll_type_name_en": delivery.roll_type.name_en if delivery.roll_type else None,
        "roll_type_code": delivery.roll_type.code if delivery.roll_type else None,
        "quantity_received": delivery.quantity_received,
        "quantity_paid": paid_quantity,
        "quantity_unpaid": unpaid,
        "status": status,
        "note": delivery.note,
        "source": delivery.source,
        "created_by": delivery.created_by,
        "created_by_username": delivery.creator.username if delivery.creator else None,
        "created_at": delivery.created_at,
        "updated_at": delivery.updated_at,
    }


def delivery_row_payload(row: DeliveryRow) -> dict:
    return DeliveryOut(**delivery_payload(row.delivery, paid_quantity=row.paid_quantity))


def named_payload(obj) -> dict:
    return {
        "id": obj.id,
        "name": obj.name,
        "is_active": obj.is_active,
        "created_at": obj.created_at,
    }


def roll_type_payload(obj) -> dict:
    return {
        "id": obj.id,
        "code": obj.code,
        "name": obj.name_km,
        "name_km": obj.name_km,
        "name_en": obj.name_en,
        "is_active": obj.is_active,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }
