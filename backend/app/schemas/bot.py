"""Schemas for the internal bot API.

The Telegram bot authenticates with a shared ``X-Bot-Token`` secret and passes
the *verified* numeric ``telegram_user_id``.  It never sends a username as proof
of identity and never computes any totals itself.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import UserRole
from app.schemas.catalog import NamedOut, RollTypeOut
from app.schemas.delivery import DeliveryOut
from app.schemas.payment import AllocationIn


class BotLinkRequest(BaseModel):
    token: str = Field(min_length=4, max_length=200)
    telegram_user_id: int = Field(gt=0)
    telegram_username: str | None = Field(default=None, max_length=64)
    telegram_chat_id: int | None = None


class BotLinkResponse(BaseModel):
    linked: bool
    username: str
    role: UserRole
    message: str


class BotPrincipalOut(BaseModel):
    """Who the bot is talking to (resolved from the verified telegram id)."""

    linked: bool
    user_id: int | None = None
    username: str | None = None
    role: UserRole | None = None
    permissions: dict[str, bool] = {}
    message: str = ""


class BotCatalogOut(BaseModel):
    suppliers: list[NamedOut]
    roll_types: list[RollTypeOut]


class BotDeliveryCreate(BaseModel):
    telegram_user_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    roll_type_id: int = Field(gt=0)
    quantity_received: int = Field(gt=0, le=1_000_000)
    delivery_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=80)


class BotDeliveryCreatedOut(BaseModel):
    delivery: DeliveryOut
    message: str


class BotPaymentConfirm(BaseModel):
    telegram_user_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    roll_type_id: int | None = Field(default=None, gt=0)
    payment_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    allocations: list[AllocationIn] | None = None
    idempotency_key: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _check_range(self) -> "BotPaymentConfirm":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


class BotSummaryOut(BaseModel):
    today: date
    total_received: int
    received_today: int
    total_paid: int
    total_unpaid: int
    by_supplier: list[dict] = []
    by_roll_type: list[dict] = []
    by_supplier_and_roll_type: list[dict] = []


class BotDeliveryListItem(BaseModel):
    id: int
    delivery_date: date
    supplier_name: str | None = None
    roll_type_name: str | None = None
    roll_type_name_km: str | None = None
    roll_type_name_en: str | None = None
    roll_type_code: str | None = None
    quantity_received: int
    quantity_paid: int
    quantity_unpaid: int
    status: str
    created_at: datetime | None = None
