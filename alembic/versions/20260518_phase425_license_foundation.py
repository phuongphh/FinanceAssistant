"""Phase 4.2.5 license foundation

Revision ID: 20260518p425license
Revises: 20260517p425users
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260518p425license"
down_revision: Union[str, Sequence[str], None] = "20260517p425users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LICENSE_PLAN_CHECK = "plan IN ('free', 'pro', 'founding', 'enterprise')"
_LICENSE_STATUS_CHECK = (
    "status IN ('active', 'trialing', 'past_due', 'canceled', 'expired')"
)


def upgrade() -> None:
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plan", sa.String(length=50), nullable=False, server_default="free"),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="active"
        ),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(_LICENSE_PLAN_CHECK, name="ck_licenses_plan"),
        sa.CheckConstraint(_LICENSE_STATUS_CHECK, name="ck_licenses_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_licenses_user_id"),
    )
    op.create_index("ix_licenses_tenant_id", "licenses", ["tenant_id"])
    op.create_index("ix_licenses_plan", "licenses", ["plan"])
    op.create_index("ix_licenses_status", "licenses", ["status"])
    op.create_index(
        "idx_licenses_tenant_plan_status", "licenses", ["tenant_id", "plan", "status"]
    )

    op.execute("""
        INSERT INTO licenses (user_id, tenant_id, plan, status, created_at, updated_at)
        SELECT id, tenant_id, 'free', 'active', now(), now()
        FROM users
        WHERE deleted_at IS NULL
        ON CONFLICT (user_id) DO NOTHING
        """)

    op.execute("""
        CREATE OR REPLACE FUNCTION create_free_license_for_user()
        RETURNS trigger AS $$
        BEGIN
            INSERT INTO licenses (user_id, tenant_id, plan, status, created_at, updated_at)
            VALUES (NEW.id, COALESCE(NEW.tenant_id, 1), 'free', 'active', now(), now())
            ON CONFLICT (user_id) DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER trg_users_create_free_license
        AFTER INSERT ON users
        FOR EACH ROW
        EXECUTE FUNCTION create_free_license_for_user();
        """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_create_free_license ON users")
    op.execute("DROP FUNCTION IF EXISTS create_free_license_for_user()")
    op.drop_index("idx_licenses_tenant_plan_status", table_name="licenses")
    op.drop_index("ix_licenses_status", table_name="licenses")
    op.drop_index("ix_licenses_plan", table_name="licenses")
    op.drop_index("ix_licenses_tenant_id", table_name="licenses")
    op.drop_table("licenses")
