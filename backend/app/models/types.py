"""Small helpers for building portable enum columns.

We store enums as ``VARCHAR`` + ``CHECK`` constraint instead of native
PostgreSQL enum types: adding a new value later only needs a constraint update
and avoids the awkward ``ALTER TYPE`` migration dance.
"""

from __future__ import annotations

import enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=enum.Enum)


def enum_column(enum_cls: type[E], name: str):
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )
