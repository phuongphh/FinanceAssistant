"""phase4.1 founding member flag + invite codes + onboarding sessions

Revision ID: u0p1q2r3s4t5
Revises: t9n0p1q2r3s4
Create Date: 2026-05-12 00:00:03.000000

Phase 4.1 — Stories A.1, A.2, C.1, C.4.

Three concerns merged into one migration because they all land together
for the soft-launch DB scaffolding:

1. ``users`` — founding-member flag + sequence + activation timestamp +
   acquisition source (for source-aware welcome copy).
2. ``invite_codes`` — new table; tracks which token grants founding
   status. Each invite is single-use to keep the 50-cohort tight.
3. ``onboarding_sessions`` — state machine row per user with goal,
   inferred wealth segment, resume-nudge bookkeeping, in-onboarding
   emoji signal, and first-Twin timing for TTFT analytics.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "u0p1q2r3s4t5"
down_revision = "t9n0p1q2r3s4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users: founding member columns + acquisition_source -----------
    op.add_column(
        "users",
        sa.Column(
            "is_founding_member",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("founding_member_sequence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("founding_member_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("acquisition_source", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_founding_sequence",
        "users",
        ["founding_member_sequence"],
    )
    op.execute(
        "CREATE INDEX idx_users_founding ON users (is_founding_member) "
        "WHERE is_founding_member = TRUE"
    )

    # --- invite_codes ---------------------------------------------------
    op.create_table(
        "invite_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token", sa.String(length=64), nullable=False, unique=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("batch_name", sa.String(length=64), nullable=True),
        sa.Column(
            "grants_founding_status",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "redeemed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_invite_codes_source", "invite_codes", ["source"])

    # --- onboarding_sessions -------------------------------------------
    op.create_table(
        "onboarding_sessions",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            primary_key=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "current_step",
            sa.String(length=32),
            server_default=sa.text("'goal_question'"),
            nullable=False,
        ),
        sa.Column("goal_choice", sa.String(length=32), nullable=True),
        sa.Column("inferred_wealth_segment", sa.String(length=32), nullable=True),
        sa.Column("first_asset_value_vnd", sa.Numeric(20, 2), nullable=True),
        sa.Column("demo_mode_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("first_twin_shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nudge_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarding_feedback_signal", sa.String(length=16), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    # Stuck-onboarding worker query: only ever scans incomplete & un-nudged.
    op.execute(
        "CREATE INDEX idx_onboarding_stuck "
        "ON onboarding_sessions (updated_at) "
        "WHERE current_step != 'completed' AND nudge_sent_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_onboarding_stuck")
    op.drop_table("onboarding_sessions")

    op.drop_index("idx_invite_codes_source", table_name="invite_codes")
    op.drop_table("invite_codes")

    op.execute("DROP INDEX IF EXISTS idx_users_founding")
    op.drop_constraint("uq_users_founding_sequence", "users", type_="unique")
    op.drop_column("users", "acquisition_source")
    op.drop_column("users", "founding_member_at")
    op.drop_column("users", "founding_member_sequence")
    op.drop_column("users", "is_founding_member")
