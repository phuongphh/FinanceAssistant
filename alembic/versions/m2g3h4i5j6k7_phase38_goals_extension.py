"""phase 3.8 epic 5 — goals extension: templates, status, projection cache

Revision ID: m2g3h4i5j6k7
Revises: l1f2a3b4c5d6
Create Date: 2026-05-06 06:30:00.000000

Phase 3.8 Epic 5 (Stories P3.8-S13..S15):

The Phase 3A ``goals`` table was a stub — single goal per user with
just (goal_name, target_amount, current_amount, deadline, priority,
is_active). Epic 5 promotes goals to first-class:

- Renames ``goal_name → name`` and ``deadline → target_date`` so
  Pydantic schemas and the agent tool match spec field names.
- Adds template linkage (``template_id``, ``icon``) so the bot can
  surface "🚗 Mua xe" patterns from ``content/goal_templates.yaml``.
- Adds ``monthly_savings_required`` cache so the wizard's projection
  step doesn't have to recompute on every list-view tap.
- Replaces the ``is_active`` Bool with a richer ``status`` enum
  (active | completed | paused | abandoned) so we can distinguish
  "user hit the target" from "user paused this goal".
- Adds ``linked_assets`` JSONB — Phase 4 will let users tag specific
  cash/savings assets as "counts toward emergency fund". Column is
  nullable now; the wizard doesn't surface it until that phase.
- Adds ``completed_at`` for celebration timing.
- Converts ``priority`` from string ("high"/"medium"/"low") to
  integer 1-10 (1=highest) so multi-goal ranking math works without
  string parsing. Backfills "high"=1, "medium"=5, "low"=10.
- Bumps ``target_amount`` / ``current_amount`` precision from
  ``Numeric(15,2)`` to ``Numeric(20,2)`` — "Mua nhà 10 tỷ" goals
  approach the 15,2 cap of 9.99 trillion.

All renames carry the data over (no DROP-then-ADD that would lose
existing rows). The ``priority`` conversion does drop+re-add but
backfills first so values transfer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "m2g3h4i5j6k7"
down_revision: Union[str, Sequence[str], None] = "l1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename existing columns. Postgres preserves data + indexes.
    op.alter_column("goals", "goal_name", new_column_name="name")
    op.alter_column("goals", "deadline", new_column_name="target_date")

    # 2. Bump money precision to match spec § 2.2.
    op.alter_column(
        "goals", "target_amount",
        type_=sa.Numeric(20, 2),
        existing_type=sa.Numeric(15, 2),
    )
    op.alter_column(
        "goals", "current_amount",
        type_=sa.Numeric(20, 2),
        existing_type=sa.Numeric(15, 2),
    )

    # 3. Add new columns nullable so backfill UPDATE works.
    op.add_column(
        "goals", sa.Column("template_id", sa.String(50), nullable=True)
    )
    op.add_column(
        "goals", sa.Column("icon", sa.String(20), nullable=True)
    )
    op.add_column(
        "goals",
        sa.Column("monthly_savings_required", sa.Numeric(20, 2), nullable=True),
    )
    op.add_column(
        "goals", sa.Column("status", sa.String(20), nullable=True)
    )
    op.add_column(
        "goals", sa.Column("linked_assets", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "goals", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # 4. Backfill ``status`` from ``is_active``. ``is_active=False``
    # is treated as "paused" not "completed" — completion needs an
    # explicit signal (current_amount ≥ target_amount). The wizard
    # at goal create-time will mark new goals 'active'.
    op.execute("""
        UPDATE goals
        SET status = CASE
            WHEN is_active = true THEN 'active'
            ELSE 'paused'
        END
    """)
    op.alter_column("goals", "status", nullable=False, server_default=sa.text("'active'"))

    # 5. Convert ``priority`` from string to integer. Drop + re-add
    # via a temporary column so existing string values transfer
    # through the CASE mapping.
    op.add_column(
        "goals", sa.Column("priority_int", sa.Integer(), nullable=True)
    )
    op.execute("""
        UPDATE goals
        SET priority_int = CASE priority
            WHEN 'high' THEN 1
            WHEN 'medium' THEN 5
            WHEN 'low' THEN 10
            ELSE 5
        END
    """)
    op.drop_column("goals", "priority")
    op.alter_column(
        "goals", "priority_int",
        new_column_name="priority",
        server_default=sa.text("5"),
        nullable=False,
    )

    # 6. Drop the legacy ``is_active`` flag now that ``status``
    # carries the same information (and more). The Phase 0 codebase
    # has been updated in this PR to read ``status`` instead.
    op.drop_column("goals", "is_active")

    # 7. New index for the agent's "active goals" query — ordered by
    # priority so the most important goal lands first in list views.
    op.create_index(
        "idx_goals_user_status_priority",
        "goals",
        ["user_id", "status", "priority"],
    )


def downgrade() -> None:
    """Reverse the upgrade. Lossy: ``template_id``, ``icon``,
    ``monthly_savings_required``, ``linked_assets``, ``completed_at``
    data is dropped. Priority converts back to string via the inverse
    of the upgrade mapping."""
    op.drop_index("idx_goals_user_status_priority", table_name="goals")

    # Restore is_active.
    op.add_column(
        "goals",
        sa.Column(
            "is_active", sa.Boolean(),
            server_default=sa.text("true"), nullable=True,
        ),
    )
    op.execute("""
        UPDATE goals
        SET is_active = (status IN ('active', 'paused'))
    """)
    op.alter_column("goals", "is_active", nullable=False)

    # Drop new columns.
    op.drop_column("goals", "completed_at")
    op.drop_column("goals", "linked_assets")
    op.drop_column("goals", "status")
    op.drop_column("goals", "monthly_savings_required")
    op.drop_column("goals", "icon")
    op.drop_column("goals", "template_id")

    # Convert priority back to string.
    op.add_column(
        "goals",
        sa.Column("priority_str", sa.String(20), nullable=True),
    )
    op.execute("""
        UPDATE goals
        SET priority_str = CASE
            WHEN priority <= 3 THEN 'high'
            WHEN priority <= 7 THEN 'medium'
            ELSE 'low'
        END
    """)
    op.drop_column("goals", "priority")
    op.alter_column(
        "goals", "priority_str",
        new_column_name="priority",
        server_default=sa.text("'medium'"),
        nullable=False,
    )

    # Restore precisions.
    op.alter_column(
        "goals", "current_amount",
        type_=sa.Numeric(15, 2),
        existing_type=sa.Numeric(20, 2),
    )
    op.alter_column(
        "goals", "target_amount",
        type_=sa.Numeric(15, 2),
        existing_type=sa.Numeric(20, 2),
    )

    op.alter_column("goals", "target_date", new_column_name="deadline")
    op.alter_column("goals", "name", new_column_name="goal_name")
