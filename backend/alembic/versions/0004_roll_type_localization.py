"""Add stable localized roll types and seed the two glue types.

Revision ID: 0004_roll_type_localization
Revises: 0003_runtime_integrity
Create Date: 2026-10-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_roll_type_localization"
down_revision = "0003_runtime_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_roll_types_name", table_name="roll_types")
    op.drop_constraint("uq_roll_types_name", "roll_types", type_="unique")
    op.alter_column("roll_types", "name", new_column_name="name_km")
    op.add_column("roll_types", sa.Column("code", sa.String(40), nullable=True))
    op.add_column("roll_types", sa.Column("name_en", sa.String(120), nullable=True))
    op.add_column(
        "roll_types",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    op.execute(
        """
        UPDATE roll_types
           SET code = 'LEGACY_' || id::text,
               name_en = name_km,
               updated_at = now()
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   CASE
                       WHEN lower(name_km) IN ('roll type 1', 'thick glue', 'កាវក្រាស់') THEN 'THICK_GLUE'
                       WHEN lower(name_km) IN ('roll type 2', 'thin glue', 'កាវស្ដើង') THEN 'THIN_GLUE'
                   END AS default_code,
                   row_number() OVER (
                       PARTITION BY CASE
                           WHEN lower(name_km) IN ('roll type 1', 'thick glue', 'កាវក្រាស់') THEN 'THICK_GLUE'
                           WHEN lower(name_km) IN ('roll type 2', 'thin glue', 'កាវស្ដើង') THEN 'THIN_GLUE'
                       END
                       ORDER BY id
                   ) AS match_number
              FROM roll_types
        )
        UPDATE roll_types AS target
           SET code = ranked.default_code,
               name_km = CASE ranked.default_code
                   WHEN 'THICK_GLUE' THEN 'កាវក្រាស់'
                   WHEN 'THIN_GLUE' THEN 'កាវស្ដើង'
               END,
               name_en = CASE ranked.default_code
                   WHEN 'THICK_GLUE' THEN 'Thick Glue'
                   WHEN 'THIN_GLUE' THEN 'Thin Glue'
               END,
               updated_at = now()
          FROM ranked
         WHERE target.id = ranked.id
           AND ranked.default_code IS NOT NULL
           AND ranked.match_number = 1
        """
    )
    op.alter_column("roll_types", "code", nullable=False)
    op.alter_column("roll_types", "name_en", nullable=False)
    op.alter_column("roll_types", "updated_at", nullable=False, server_default=sa.func.now())
    op.create_unique_constraint("uq_roll_types_code", "roll_types", ["code"])
    op.create_index("ix_roll_types_code", "roll_types", ["code"])
    op.execute(
        """
        INSERT INTO roll_types (code, name_km, name_en, is_active)
        SELECT defaults.code, defaults.name_km, defaults.name_en, TRUE
          FROM (VALUES
              ('THICK_GLUE', 'កាវក្រាស់', 'Thick Glue'),
              ('THIN_GLUE', 'កាវស្ដើង', 'Thin Glue')
          ) AS defaults(code, name_km, name_en)
         WHERE NOT EXISTS (
             SELECT 1 FROM roll_types existing WHERE existing.code = defaults.code
         )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_roll_types_code", table_name="roll_types")
    op.drop_constraint("uq_roll_types_code", "roll_types", type_="unique")
    op.drop_column("roll_types", "updated_at")
    op.drop_column("roll_types", "name_en")
    op.drop_column("roll_types", "code")
    op.alter_column("roll_types", "name_km", new_column_name="name")
    op.create_unique_constraint("uq_roll_types_name", "roll_types", ["name"])
    op.create_index("ix_roll_types_name", "roll_types", ["name"])
