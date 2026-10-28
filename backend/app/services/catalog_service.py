"""Suppliers and roll types - administrator-managed reference data."""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.catalog import RollType, Supplier
from app.models.delivery import Delivery
from app.services import audit_service

_NAME_MAX = 120


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Name is required")
    if len(name) > _NAME_MAX:
        raise ValidationError(f"Name must be at most {_NAME_MAX} characters")
    return name


# --------------------------------------------------------------------------- #
# Suppliers
# --------------------------------------------------------------------------- #
def list_suppliers(db: Session, *, only_active: bool = False) -> list[Supplier]:
    stmt = select(Supplier).order_by(Supplier.name)
    if only_active:
        stmt = stmt.where(Supplier.is_active.is_(True))
    return list(db.execute(stmt).scalars().all())


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError("Supplier not found", code="supplier_not_found")
    return supplier


def name_exists(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(Supplier.id).where(func.lower(Supplier.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(Supplier.id != exclude_id)
    return db.execute(stmt).first() is not None


def create_supplier(
    db: Session, *, name: str, actor_user_id: int | None = None, ip_address: str | None = None
) -> Supplier:
    name = _clean_name(name)
    if name_exists(db, name):
        raise ConflictError("A supplier with that name already exists", code="supplier_exists")
    supplier = Supplier(name=name)
    db.add(supplier)
    db.flush()
    audit_service.record(
        db, action="supplier.create", actor_user_id=actor_user_id, entity_type="supplier",
        entity_id=supplier.id, details={"name": name}, ip_address=ip_address,
    )
    return supplier


def update_supplier(
    db: Session,
    *,
    supplier_id: int,
    name: str | None = None,
    is_active: bool | None = None,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    changes: dict[str, object] = {}
    if name is not None:
        name = _clean_name(name)
        if name.lower() != supplier.name.lower():
            if name_exists(db, name, exclude_id=supplier.id):
                raise ConflictError("A supplier with that name already exists", code="supplier_exists")
            changes["name"] = [supplier.name, name]
            supplier.name = name
    if is_active is not None and is_active != supplier.is_active:
        changes["is_active"] = [supplier.is_active, is_active]
        supplier.is_active = is_active
    db.flush()
    if changes:
        audit_service.record(
            db, action="supplier.update", actor_user_id=actor_user_id, entity_type="supplier",
            entity_id=supplier.id, details=changes, ip_address=ip_address,
        )
    return supplier


def supplier_usage(db: Session, supplier_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Delivery.id)).where(Delivery.supplier_id == supplier_id)
        ).scalar_one()
    )


def delete_supplier(db: Session, *, supplier_id: int, actor_user_id: int | None = None) -> None:
    supplier = get_supplier(db, supplier_id)
    if supplier_usage(db, supplier_id) > 0:
        raise ConflictError(
            "This supplier is used by existing deliveries; deactivate it instead",
            code="supplier_in_use",
        )
    audit_service.record(
        db, action="supplier.delete", actor_user_id=actor_user_id, entity_type="supplier",
        entity_id=supplier.id, details={"name": supplier.name},
    )
    db.delete(supplier)


# --------------------------------------------------------------------------- #
# Roll types
# --------------------------------------------------------------------------- #
def list_roll_types(db: Session, *, only_active: bool = False) -> list[RollType]:
    stmt = select(RollType).order_by(RollType.code)
    if only_active:
        stmt = stmt.where(RollType.is_active.is_(True))
    return list(db.execute(stmt).scalars().all())


def get_roll_type(db: Session, roll_type_id: int) -> RollType:
    roll_type = db.get(RollType, roll_type_id)
    if roll_type is None:
        raise NotFoundError("Roll type not found", code="roll_type_not_found")
    return roll_type


def roll_type_code_exists(db: Session, code: str) -> bool:
    stmt = select(RollType.id).where(RollType.code == code)
    return db.execute(stmt).first() is not None


def create_roll_type(
    db: Session,
    *,
    code: str,
    name_km: str,
    name_en: str,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
) -> RollType:
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,39}", code):
        raise ValidationError("Code must contain uppercase letters, digits, and underscores")
    if roll_type_code_exists(db, code):
        raise ConflictError("A roll type with that code already exists", code="roll_type_exists")
    name_km = _clean_name(name_km)
    name_en = _clean_name(name_en)
    roll_type = RollType(code=code, name_km=name_km, name_en=name_en)
    db.add(roll_type)
    db.flush()
    audit_service.record(
        db, action="roll_type.create", actor_user_id=actor_user_id, entity_type="roll_type",
        entity_id=roll_type.id, details={"code": code, "name_km": name_km, "name_en": name_en},
        ip_address=ip_address,
    )
    return roll_type


def update_roll_type(
    db: Session,
    *,
    roll_type_id: int,
    name_km: str | None = None,
    name_en: str | None = None,
    is_active: bool | None = None,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
) -> RollType:
    roll_type = get_roll_type(db, roll_type_id)
    changes: dict[str, object] = {}
    if name_km is not None:
        name_km = _clean_name(name_km)
        if name_km != roll_type.name_km:
            changes["name_km"] = [roll_type.name_km, name_km]
            roll_type.name_km = name_km
    if name_en is not None:
        name_en = _clean_name(name_en)
        if name_en != roll_type.name_en:
            changes["name_en"] = [roll_type.name_en, name_en]
            roll_type.name_en = name_en
    if is_active is not None and is_active != roll_type.is_active:
        changes["is_active"] = [roll_type.is_active, is_active]
        roll_type.is_active = is_active
    db.flush()
    if changes:
        audit_service.record(
            db, action="roll_type.update", actor_user_id=actor_user_id, entity_type="roll_type",
            entity_id=roll_type.id, details=changes, ip_address=ip_address,
        )
    return roll_type


def roll_type_usage(db: Session, roll_type_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Delivery.id)).where(Delivery.roll_type_id == roll_type_id)
        ).scalar_one()
    )


def delete_roll_type(db: Session, *, roll_type_id: int, actor_user_id: int | None = None) -> None:
    roll_type = get_roll_type(db, roll_type_id)
    if roll_type_usage(db, roll_type_id) > 0:
        raise ConflictError(
            "This roll type is used by existing deliveries; deactivate it instead",
            code="roll_type_in_use",
        )
    audit_service.record(
        db, action="roll_type.delete", actor_user_id=actor_user_id, entity_type="roll_type",
        entity_id=roll_type.id, details={"code": roll_type.code, "name_km": roll_type.name_km},
    )
    db.delete(roll_type)


def ensure_default_catalog(db: Session) -> None:
    """Create example suppliers and ensure the two canonical glue types exist."""
    if not list_suppliers(db):
        for name in ("Supplier A", "Supplier B"):
            db.add(Supplier(name=name))
    existing_codes = set(db.execute(select(RollType.code)).scalars())
    defaults = (
        ("THICK_GLUE", "កាវក្រាស់", "Thick Glue"),
        ("THIN_GLUE", "កាវស្ដើង", "Thin Glue"),
    )
    for code, name_km, name_en in defaults:
        if code not in existing_codes:
            db.add(RollType(code=code, name_km=name_km, name_en=name_en))
    db.flush()
