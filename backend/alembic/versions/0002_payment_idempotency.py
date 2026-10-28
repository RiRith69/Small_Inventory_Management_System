"""Add an idempotency key to payments.

Rationale: prevents duplicate payment confirmations when a client (especially a
Telegram user double-tapping a button, or a retried HTTP request) submits the
same confirmation twice.  The key is supplied by the client and is unique, so a
repeat submission returns the *original* payment instead of creating a second
one.

Revision ID: 0002_idempotency
Revises: 0001_initial
Create Date: 2026-10-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_idempotency"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("idempotency_key", sa.String(80), nullable=True))
    op.create_unique_constraint("uq_payments_idempotency_key", "payments", ["idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_payments_idempotency_key", "payments", type_="unique")
    op.drop_column("payments", "idempotency_key")
