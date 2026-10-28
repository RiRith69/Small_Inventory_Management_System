"""Supplier / roll-type schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class NameCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class NameUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


class NamedOut(ORMModel):
    id: int
    name: str
    is_active: bool
    created_at: datetime


class CatalogOut(BaseModel):
    suppliers: list[NamedOut]
    roll_types: list["RollTypeOut"]


class RollTypeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$")
    name_km: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)


class RollTypeUpdate(BaseModel):
    name_km: str | None = Field(default=None, min_length=1, max_length=120)
    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


class RollTypeOut(BaseModel):
    id: int
    code: str
    name_km: str
    name_en: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


CatalogOut.model_rebuild()
