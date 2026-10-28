"""Payment schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DeliveryStatus


class AllocationIn(BaseModel):
    delivery_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1_000_000)


class PaymentConfirmRequest(BaseModel):
    """Confirm a payment.

    * Omit ``allocations`` to let the **server** calculate and pay the full
      remaining unpaid quantity of every delivery matching ``supplier_id`` and
      the delivery-date range (the normal "pay the whole accumulated total"
      workflow).
    * Supply ``allocations`` for a **partial** payment, or to deliberately pay a
      specific delivery outside the range - the authorised alternative workflow.

    Totals are never accepted from the client.
    """

    supplier_id: int = Field(gt=0)
    roll_type_id: int | None = Field(default=None, gt=0)
    payment_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    allocations: list[AllocationIn] | None = None
    idempotency_key: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _check_range(self) -> "PaymentConfirmRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        if not self.allocations and not (self.start_date and self.end_date):
            # Allowing an open range is intentional but must be explicit.
            pass
        if self.allocations is not None and len(self.allocations) == 0:
            raise ValueError("allocations must not be empty when provided")
        return self


class PaymentAllocationOut(BaseModel):
    allocation_id: int
    delivery_id: int
    delivery_date: date
    roll_type_id: int
    roll_type_name: str | None = None
    roll_type_name_km: str | None = None
    roll_type_name_en: str | None = None
    roll_type_code: str | None = None
    quantity_paid: int
    quantity_received: int


class PaymentOut(BaseModel):
    id: int
    reference: str
    supplier_id: int
    supplier_name: str | None = None
    payment_date: date
    total_quantity: int
    note: str | None = None
    created_by: int
    created_by_username: str | None = None
    created_at: datetime
    is_reversed: bool
    reversed_at: datetime | None = None
    reversal_reason: str | None = None
    delivery_date_from: date | None = None
    delivery_date_to: date | None = None
    roll_type_breakdown: list[dict] = []


class PaymentDetailOut(PaymentOut):
    allocations: list[PaymentAllocationOut] = []


class PaymentReversalRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class UnpaidDeliveryOut(BaseModel):
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


class UnpaidPreviewOut(BaseModel):
    supplier: dict
    start_date: date | None = None
    end_date: date | None = None
    deliveries: list[UnpaidDeliveryOut] = []
    totals: dict
    by_roll_type: list["UnpaidRollTypeTotals"] = []
    delivery_dates: list[date] = []
    delivery_count: int


class UnpaidRollTypeTotals(BaseModel):
    roll_type_id: int
    roll_type_code: str
    roll_type_name: str
    roll_type_name_en: str
    received: int
    paid: int
    unpaid: int
    quantity_unpaid: int
    delivery_count: int
