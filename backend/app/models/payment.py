"""Payments and the allocations that link them to delivered quantities.

A payment records *that a quantity of rolls has been paid for*.  There are no
monetary amounts anywhere in this system.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.delivery import Delivery


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    # Client-supplied de-duplication key (see migration 0002).
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    idempotency_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ---- Auditable reversal (payments are never deleted) ----
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reversal_reason: Mapped[str | None] = mapped_column(Text)

    supplier: Mapped["Supplier"] = relationship(lazy="joined")  # noqa: F821
    creator: Mapped["User"] = relationship(foreign_keys=[created_by], lazy="joined")  # noqa: F821
    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_payments_supplier_date", "supplier_id", "payment_date"),)

    @property
    def is_reversed(self) -> bool:
        return self.reversed_at is not None


class PaymentAllocation(Base):
    """Which delivery quantities a payment covers.

    ``sum(quantity_paid)`` per delivery may never exceed ``quantity_received``.
    That invariant is enforced in the service layer inside a ``SELECT ... FOR
    UPDATE`` transaction (a plain column constraint cannot express it), and
    additionally guarded by a DB trigger in the initial migration.
    """

    __tablename__ = "payment_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("deliveries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    payment: Mapped[Payment] = relationship(back_populates="allocations")
    delivery: Mapped[Delivery] = relationship(back_populates="allocations")

    __table_args__ = (
        CheckConstraint("quantity_paid > 0", name="ck_allocations_quantity_positive"),
        UniqueConstraint("payment_id", "delivery_id", name="uq_allocations_payment_delivery"),
    )
