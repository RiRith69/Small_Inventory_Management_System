"""Incoming deliveries (the immutable record of what was received)."""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import DeliverySource
from app.models.types import enum_column


class Delivery(Base):
    """One bulk delivery of rolls from a supplier.

    ``delivery_date`` is when the rolls physically arrived and is never changed
    by the payment process.  Paid/unpaid quantities are *derived* from
    ``payment_allocations`` (single source of truth) - never stored here.
    """

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    roll_type_id: Mapped[int] = mapped_column(
        ForeignKey("roll_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[DeliverySource] = mapped_column(
        enum_column(DeliverySource, "delivery_source"),
        nullable=False,
        default=DeliverySource.web,
        server_default=DeliverySource.web.value,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Client-supplied de-duplication key: a retried/double-tapped submission
    # returns the original delivery instead of creating a second one.
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    idempotency_hash: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    supplier: Mapped["Supplier"] = relationship(lazy="joined")  # noqa: F821
    roll_type: Mapped["RollType"] = relationship(lazy="joined")  # noqa: F821
    creator: Mapped["User"] = relationship(foreign_keys=[created_by], lazy="joined")  # noqa: F821
    updater: Mapped["User | None"] = relationship(foreign_keys=[updated_by], lazy="joined")  # noqa: F821
    allocations: Mapped[list["PaymentAllocation"]] = relationship(  # noqa: F821
        back_populates="delivery", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("quantity_received > 0", name="ck_deliveries_quantity_positive"),
        Index("ix_deliveries_supplier_date", "supplier_id", "delivery_date"),
        Index("ix_deliveries_rolltype_date", "roll_type_id", "delivery_date"),
    )
