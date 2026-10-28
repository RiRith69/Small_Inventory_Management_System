"""Add bot link throttling and harden allocation idempotency guards.

Revision ID: 0003_runtime_integrity
Revises: 0002_idempotency
Create Date: 2026-10-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_runtime_integrity"
down_revision = "0002_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deliveries", sa.Column("idempotency_key", sa.String(80), nullable=True))
    op.add_column("deliveries", sa.Column("idempotency_hash", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_deliveries_idempotency_key", "deliveries", ["idempotency_key"]
    )
    op.add_column("payments", sa.Column("idempotency_hash", sa.String(64), nullable=True))

    op.create_table(
        "telegram_link_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("successful", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_telegram_link_attempts_telegram_user_id",
        "telegram_link_attempts",
        ["telegram_user_id"],
    )
    op.create_index(
        "ix_telegram_link_attempts_created_at", "telegram_link_attempts", ["created_at"]
    )
    op.create_index(
        "ix_telegram_link_attempts_user_created",
        "telegram_link_attempts",
        ["telegram_user_id", "created_at"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_allocation_total() RETURNS trigger AS $$
        DECLARE
            total_paid integer;
            received integer;
            affected_delivery_id integer;
        BEGIN
            affected_delivery_id := COALESCE(NEW.delivery_id, OLD.delivery_id);
            SELECT COALESCE(SUM(a.quantity_paid), 0) INTO total_paid
              FROM payment_allocations a
              JOIN payments p ON p.id = a.payment_id
             WHERE a.delivery_id = affected_delivery_id
               AND p.reversed_at IS NULL;
            SELECT quantity_received INTO received
              FROM deliveries WHERE id = affected_delivery_id;
            IF received IS NOT NULL AND total_paid > received THEN
                RAISE EXCEPTION
                    'allocated quantity % exceeds received quantity % for delivery %',
                    total_paid, received, affected_delivery_id
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_delivery_quantity_against_allocations()
        RETURNS trigger AS $$
        DECLARE
            total_paid integer;
        BEGIN
            SELECT COALESCE(SUM(a.quantity_paid), 0) INTO total_paid
              FROM payment_allocations a
              JOIN payments p ON p.id = a.payment_id
             WHERE a.delivery_id = NEW.id
               AND p.reversed_at IS NULL;
            IF total_paid > NEW.quantity_received THEN
                RAISE EXCEPTION
                    'allocated quantity % exceeds received quantity % for delivery %',
                    total_paid, NEW.quantity_received, NEW.id
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_check_delivery_quantity_allocations
        AFTER UPDATE OF quantity_received ON deliveries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION check_delivery_quantity_against_allocations();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_check_delivery_quantity_allocations ON deliveries"
    )
    op.execute("DROP FUNCTION IF EXISTS check_delivery_quantity_against_allocations()")
    op.drop_index("ix_telegram_link_attempts_user_created", table_name="telegram_link_attempts")
    op.drop_index("ix_telegram_link_attempts_created_at", table_name="telegram_link_attempts")
    op.drop_index(
        "ix_telegram_link_attempts_telegram_user_id", table_name="telegram_link_attempts"
    )
    op.drop_table("telegram_link_attempts")
    op.drop_column("payments", "idempotency_hash")
    op.drop_constraint("uq_deliveries_idempotency_key", "deliveries", type_="unique")
    op.drop_column("deliveries", "idempotency_hash")
    op.drop_column("deliveries", "idempotency_key")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_allocation_total() RETURNS trigger AS $$
        DECLARE
            total_paid integer;
            received integer;
        BEGIN
            SELECT COALESCE(SUM(quantity_paid), 0) INTO total_paid
              FROM payment_allocations WHERE delivery_id = NEW.delivery_id;
            SELECT quantity_received INTO received FROM deliveries WHERE id = NEW.delivery_id;
            IF total_paid > received THEN
                RAISE EXCEPTION
                    'allocated quantity % exceeds received quantity % for delivery %',
                    total_paid, received, NEW.delivery_id
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
