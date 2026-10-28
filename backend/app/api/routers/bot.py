"""Internal API consumed only by the Telegram bot process."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_bot_token
from app.api.serializers import delivery_row_payload, named_payload, roll_type_payload
from app.core.errors import PermissionDeniedError
from app.database.session import get_db
from app.models.enums import DeliverySource
from app.schemas.bot import (
    BotCatalogOut,
    BotDeliveryCreate,
    BotDeliveryCreatedOut,
    BotDeliveryListItem,
    BotLinkRequest,
    BotLinkResponse,
    BotPaymentConfirm,
    BotPrincipalOut,
    BotSummaryOut,
)
from app.schemas.common import Page
from app.services import (
    catalog_service,
    dashboard_service,
    delivery_service,
    payment_service,
    settings_service,
    telegram_service,
)
from app.core.timezone import local_today

router = APIRouter(
    prefix="/api/bot",
    tags=["telegram-bot"],
    dependencies=[Depends(require_bot_token)],
)


def _identity(db: Session, telegram_user_id: int):
    return telegram_service.resolve(db, telegram_user_id)


@router.post("/link", response_model=BotLinkResponse)
def link_account(payload: BotLinkRequest, db: Session = Depends(get_db)) -> dict:
    account = telegram_service.consume_link_token(
        db,
        raw_token=payload.token,
        telegram_user_id=payload.telegram_user_id,
        telegram_username=payload.telegram_username,
        telegram_chat_id=payload.telegram_chat_id,
    )
    user, _ = telegram_service.resolve(db, account.telegram_user_id)
    return {
        "linked": True,
        "username": user.username,
        "role": user.role,
        "message": "Telegram account linked successfully.",
    }


@router.get("/me", response_model=BotPrincipalOut)
def current_principal(
    telegram_user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
) -> dict:
    try:
        user, _ = _identity(db, telegram_user_id)
    except PermissionDeniedError as exc:
        if exc.code not in {"telegram_not_linked", "telegram_link_revoked", "user_inactive"}:
            raise
        return {"linked": False, "message": exc.message}
    return {
        "linked": True,
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "permissions": settings_service.permissions_for(db, user),
        "message": "",
    }


@router.get("/catalog", response_model=BotCatalogOut)
def bot_catalog(
    telegram_user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
) -> dict:
    _identity(db, telegram_user_id)
    return {
        "suppliers": [
            named_payload(item) for item in catalog_service.list_suppliers(db, only_active=True)
        ],
        "roll_types": [
            roll_type_payload(item) for item in catalog_service.list_roll_types(db, only_active=True)
        ],
    }


@router.get("/summary", response_model=BotSummaryOut)
def bot_summary(
    telegram_user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
) -> dict:
    _identity(db, telegram_user_id)
    details = dashboard_service.dashboard_summary(db)
    summary = details["summary"]
    return {
        "today": local_today(),
        "total_received": summary["total_received"],
        "received_today": summary["received_today"],
        "total_paid": summary["total_paid"],
        "total_unpaid": summary["currently_unpaid"],
        "by_supplier": details["by_supplier"],
        "by_roll_type": details["by_roll_type"],
        "by_supplier_and_roll_type": details["by_supplier_and_roll_type"],
    }


@router.get("/deliveries", response_model=Page[BotDeliveryListItem])
def bot_deliveries(
    telegram_user_id: int = Query(gt=0),
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    _identity(db, telegram_user_id)
    rows, total = delivery_service.list_deliveries(
        db,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return Page.build(
        [
            {
                "id": row.id,
                "delivery_date": row.delivery.delivery_date,
                "supplier_name": row.delivery.supplier.name,
                "roll_type_name": row.delivery.roll_type.name_km,
                "roll_type_name_km": row.delivery.roll_type.name_km,
                "roll_type_name_en": row.delivery.roll_type.name_en,
                "roll_type_code": row.delivery.roll_type.code,
                "quantity_received": row.quantity_received,
                "quantity_paid": row.paid_quantity,
                "quantity_unpaid": row.unpaid_quantity,
                "status": row.status.value,
                "created_at": row.delivery.created_at,
            }
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/deliveries", response_model=BotDeliveryCreatedOut, status_code=201)
def create_bot_delivery(
    payload: BotDeliveryCreate,
    db: Session = Depends(get_db),
) -> dict:
    user, _ = _identity(db, payload.telegram_user_id)
    delivery = delivery_service.create_delivery(
        db,
        supplier_id=payload.supplier_id,
        roll_type_id=payload.roll_type_id,
        quantity_received=payload.quantity_received,
        delivery_date=payload.delivery_date,
        note=payload.note,
        created_by=user.id,
        source=DeliverySource.telegram,
        idempotency_key=payload.idempotency_key,
    )
    row = delivery_service.get_delivery_row(db, delivery.id)
    return {"delivery": delivery_row_payload(row), "message": "Delivery recorded."}


@router.get("/payments/unpaid")
def bot_unpaid(
    telegram_user_id: int = Query(gt=0),
    supplier_id: int = Query(gt=0),
    roll_type_id: int = Query(gt=0),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    _identity(db, telegram_user_id)
    return payment_service.preview_payment(
        db,
        supplier_id=supplier_id,
        roll_type_id=roll_type_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/payments/confirm")
def confirm_bot_payment(
    payload: BotPaymentConfirm,
    db: Session = Depends(get_db),
) -> dict:
    user, _ = _identity(db, payload.telegram_user_id)
    if not settings_service.permissions_for(db, user)["can_confirm_payments"]:
        raise PermissionDeniedError(
            "You do not have permission to confirm payments", code="forbidden"
        )
    payment = payment_service.confirm_payment(
        db,
        supplier_id=payload.supplier_id,
        roll_type_id=payload.roll_type_id,
        actor_user_id=user.id,
        payment_date=payload.payment_date,
        note=payload.note,
        start_date=payload.start_date,
        end_date=payload.end_date,
        allocations=(
            [{"delivery_id": item.delivery_id, "quantity": item.quantity} for item in payload.allocations]
            if payload.allocations
            else None
        ),
        idempotency_key=payload.idempotency_key,
    )
    return payment_service.payment_detail(db, payment.id)


@router.get("/payments/history")
def bot_payment_history(
    telegram_user_id: int = Query(gt=0),
    supplier_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    _identity(db, telegram_user_id)
    items, total = payment_service.list_payments(
        db,
        supplier_id=supplier_id,
        start_date=start_date,
        end_date=end_date,
        page=1,
        page_size=20,
    )
    return {"items": items, "total": total}


@router.get("/payments/{payment_id}")
def bot_payment_detail(
    payment_id: int,
    telegram_user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
) -> dict:
    _identity(db, telegram_user_id)
    return payment_service.payment_detail(db, payment_id)
