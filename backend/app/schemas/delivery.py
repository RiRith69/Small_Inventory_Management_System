"""Delivery schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import DeliverySource, DeliveryStatus


class DeliveryCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    roll_type_id: int = Field(gt=0)
    quantity_received: int = Field(gt=0, le=1_000_000)
    delivery_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=80)

    @field_validator("note")
    @classmethod
    def _strip_note(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class DeliveryUpdate(BaseModel):
    supplier_id: int | None = Field(default=None, gt=0)
    roll_type_id: int | None = Field(default=None, gt=0)
    quantity_received: int | None = Field(default=None, gt=0, le=1_000_000)
    delivery_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class DeliveryOut(BaseModel):
    id: int
    delivery_date: date
    supplier_id: int
    supplier_name: str | None = None
    roll_type_id: int
    roll_type_name: str | None = None
    roll_type_name_km: str | None = None
    roll_type_name_en: str | None = None
    roll_type_code: str | None = None
    quantity_received: int
    quantity_paid: int
    quantity_unpaid: int
    status: DeliveryStatus
    note: str | None = None
    source: DeliverySource
    created_by: int
    created_by_username: str | None = None
    created_at: datetime
    updated_at: datetime


class RollTypeTotals(BaseModel):
    roll_type_id: int
    roll_type_name: str
    roll_type_name_en: str | None = None
    roll_type_code: str | None = None
    received: int = 0
    paid: int = 0
    unpaid: int = 0
    count: int = 0
    quantity_unpaid: int = 0
    delivery_count: int = 0


class Totals(BaseModel):
    received: int = 0
    paid: int = 0
    unpaid: int = 0


class DeliverySummaryOut(BaseModel):
    totals: Totals
    delivery_count: int
    by_roll_type: list[RollTypeTotals] = []
