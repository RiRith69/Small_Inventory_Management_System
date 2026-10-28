"""Suppliers and roll types.

Everyone who can record a delivery may read the catalogue; only an
administrator may change it. Roll-type codes are stable while display names
are maintained separately in Khmer and English.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, requires
from app.api.serializers import named_payload, roll_type_payload
from app.database.session import get_db
from app.models.user import User
from app.schemas.catalog import (
    CatalogOut,
    NameCreate,
    NameUpdate,
    NamedOut,
    RollTypeCreate,
    RollTypeOut,
    RollTypeUpdate,
)
from app.schemas.common import Message
from app.services import catalog_service

router = APIRouter(prefix="/api", tags=["catalog"])


# --------------------------------------------------------------------------- #
# Combined catalogue (used by both the website forms and the Telegram bot)
# --------------------------------------------------------------------------- #
@router.get("/catalog", response_model=CatalogOut)
def get_catalog(
    only_active: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return {
        "suppliers": [
            named_payload(s) for s in catalog_service.list_suppliers(db, only_active=only_active)
        ],
        "roll_types": [
            roll_type_payload(r) for r in catalog_service.list_roll_types(db, only_active=only_active)
        ],
    }


# --------------------------------------------------------------------------- #
# Suppliers
# --------------------------------------------------------------------------- #
@router.get("/suppliers", response_model=list[NamedOut])
def list_suppliers(
    only_active: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    return [named_payload(s) for s in catalog_service.list_suppliers(db, only_active=only_active)]


@router.post("/suppliers", response_model=NamedOut, status_code=201)
def create_supplier(
    payload: NameCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_catalog")),
) -> dict:
    supplier = catalog_service.create_supplier(
        db, name=payload.name, actor_user_id=actor.id, ip_address=client_ip(request)
    )
    return named_payload(supplier)


@router.patch("/suppliers/{supplier_id}", response_model=NamedOut)
def update_supplier(
    supplier_id: int,
    payload: NameUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_catalog")),
) -> dict:
    supplier = catalog_service.update_supplier(
        db,
        supplier_id=supplier_id,
        name=payload.name,
        is_active=payload.is_active,
        actor_user_id=actor.id,
        ip_address=client_ip(request),
    )
    return named_payload(supplier)


@router.delete("/suppliers/{supplier_id}", response_model=Message)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_catalog")),
) -> Message:
    catalog_service.delete_supplier(db, supplier_id=supplier_id, actor_user_id=actor.id)
    return Message(message="Supplier deleted")


# --------------------------------------------------------------------------- #
# Roll types
# --------------------------------------------------------------------------- #
@router.get("/roll-types", response_model=list[RollTypeOut])
def list_roll_types(
    only_active: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    return [roll_type_payload(r) for r in catalog_service.list_roll_types(db, only_active=only_active)]


@router.post("/roll-types", response_model=RollTypeOut, status_code=201)
def create_roll_type(
    payload: RollTypeCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_catalog")),
) -> dict:
    roll_type = catalog_service.create_roll_type(
        db,
        code=payload.code,
        name_km=payload.name_km,
        name_en=payload.name_en,
        actor_user_id=actor.id,
        ip_address=client_ip(request),
    )
    return roll_type_payload(roll_type)


@router.patch("/roll-types/{roll_type_id}", response_model=RollTypeOut)
def update_roll_type(
    roll_type_id: int,
    payload: RollTypeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_catalog")),
) -> dict:
    roll_type = catalog_service.update_roll_type(
        db,
        roll_type_id=roll_type_id,
        name_km=payload.name_km,
        name_en=payload.name_en,
        is_active=payload.is_active,
        actor_user_id=actor.id,
        ip_address=client_ip(request),
    )
    return roll_type_payload(roll_type)


@router.delete("/roll-types/{roll_type_id}", response_model=Message)
def delete_roll_type(
    roll_type_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(requires("can_manage_catalog")),
) -> Message:
    catalog_service.delete_roll_type(db, roll_type_id=roll_type_id, actor_user_id=actor.id)
    return Message(message="Roll type deleted")
