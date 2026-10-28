"""Enumerations shared by models, schemas and services."""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    warehouse_user = "warehouse_user"


class DeliverySource(str, enum.Enum):
    """Where a delivery was recorded (kept for auditing)."""

    web = "web"
    telegram = "telegram"


class DeliveryStatus(str, enum.Enum):
    """Derived status of a delivery (never stored - always calculated)."""

    unpaid = "unpaid"
    partial = "partial"
    paid = "paid"
