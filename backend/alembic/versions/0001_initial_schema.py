"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="warehouse_user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('admin','warehouse_user')", name="ck_users_role"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # ----------------------------------------------------------- user_sessions
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip_address", sa.String(64)),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    # ----------------------------------------------------------- login_attempts
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("successful", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_login_attempts_username", "login_attempts", ["username"])
    op.create_index("ix_login_attempts_ip_address", "login_attempts", ["ip_address"])
    op.create_index("ix_login_attempts_username_created", "login_attempts", ["username", "created_at"])

    # --------------------------------------------------------- telegram_accounts
    op.create_table(
        "telegram_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(64)),
        sa.Column("telegram_chat_id", sa.BigInteger()),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("telegram_user_id", name="uq_telegram_accounts_telegram_user_id"),
    )
    op.create_index("ix_telegram_accounts_user_id", "telegram_accounts", ["user_id"])
    op.create_index("ix_telegram_accounts_telegram_user_id", "telegram_accounts", ["telegram_user_id"])

    # ------------------------------------------------------- telegram_link_tokens
    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_ip", sa.String(64)),
        sa.UniqueConstraint("token_hash", name="uq_telegram_link_tokens_token_hash"),
    )
    op.create_index("ix_telegram_link_tokens_user_id", "telegram_link_tokens", ["user_id"])

    # --------------------------------------------------------------- suppliers
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_suppliers_name"),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"])

    # -------------------------------------------------------------- roll_types
    op.create_table(
        "roll_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_roll_types_name"),
    )
    op.create_index("ix_roll_types_name", "roll_types", ["name"])

    # --------------------------------------------------------------- deliveries
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("roll_type_id", sa.Integer(), sa.ForeignKey("roll_types.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("source", sa.String(32), nullable=False, server_default="web"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity_received > 0", name="ck_deliveries_quantity_positive"),
        sa.CheckConstraint("source IN ('web','telegram')", name="ck_deliveries_source"),
    )
    op.create_index("ix_deliveries_delivery_date", "deliveries", ["delivery_date"])
    op.create_index("ix_deliveries_supplier_id", "deliveries", ["supplier_id"])
    op.create_index("ix_deliveries_roll_type_id", "deliveries", ["roll_type_id"])
    op.create_index("ix_deliveries_supplier_date", "deliveries", ["supplier_id", "delivery_date"])
    op.create_index("ix_deliveries_rolltype_date", "deliveries", ["roll_type_id", "delivery_date"])

    # ----------------------------------------------------------------- payments
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(32), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reversal_reason", sa.Text()),
        sa.UniqueConstraint("reference", name="uq_payments_reference"),
    )
    op.create_index("ix_payments_payment_date", "payments", ["payment_date"])
    op.create_index("ix_payments_supplier_id", "payments", ["supplier_id"])
    op.create_index("ix_payments_supplier_date", "payments", ["supplier_id", "payment_date"])

    # -------------------------------------------------------- payment_allocations
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("deliveries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity_paid", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity_paid > 0", name="ck_allocations_quantity_positive"),
        sa.UniqueConstraint("payment_id", "delivery_id", name="uq_allocations_payment_delivery"),
    )
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_delivery_id", "payment_allocations", ["delivery_id"])

    # -------------------------------------------------------------- app_settings
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )

    # --------------------------------------------------------------- audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64)),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("details", sa.JSON()),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ------------------------------------------------------------------- guards
    # Database-level safety net for the core invariant:
    #   sum(quantity_paid) over a delivery must never exceed quantity_received.
    # Deferred so several allocations for the same delivery can be inserted in
    # one transaction; the check runs at COMMIT.
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
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_check_allocation_total
        AFTER INSERT OR UPDATE ON payment_allocations
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION check_allocation_total();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_check_allocation_total ON payment_allocations")
    op.execute("DROP FUNCTION IF EXISTS check_allocation_total()")
    op.drop_table("audit_logs")
    op.drop_table("app_settings")
    op.drop_table("payment_allocations")
    op.drop_table("payments")
    op.drop_table("deliveries")
    op.drop_table("roll_types")
    op.drop_table("suppliers")
    op.drop_table("telegram_link_tokens")
    op.drop_table("telegram_accounts")
    op.drop_table("login_attempts")
    op.drop_table("user_sessions")
    op.drop_table("users")
