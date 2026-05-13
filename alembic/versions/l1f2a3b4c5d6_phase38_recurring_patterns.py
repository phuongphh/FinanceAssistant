"""phase 3.8 epic 3 — recurring patterns + reminder infra

Revision ID: l1f2a3b4c5d6
Revises: k0f1a2b3c4d5
Create Date: 2026-05-06 06:00:00.000000

Phase 3.8 Epic 3 (Stories P3.8-S7..S10):

Adds three things:

1. ``recurring_patterns`` table — first-class recurring expenses
   (rent, internet, gym, Netflix). Two creation paths:
   - Manual via the menu wizard (auto_detected=False).
   - Auto-detected by ``RecurringDetector`` analysing transaction
     history (auto_detected=True, user_confirmed flips after the
     suggestion is accepted).

2. ``pattern_suggestions_log`` — append-only log of suggestions
   delivered to users with their outcome (accepted/rejected/ignored).
   Auto-detection consults this to avoid re-suggesting a pattern the
   user already rejected (spec: "Don't spam").

3. ``expenses`` extension — ``is_recurring`` Bool + ``recurrence_id``
   FK so a transaction can be linked to the pattern it instantiates.
   Reminder scheduler uses this to skip "you owe" pings when the user
   already paid this period.

Indexes target the hot paths:
- ``idx_patterns_user_active`` for the "list active patterns" view
  and reminder-scheduler scan.
- ``idx_patterns_due_soon`` partial index on enabled+due dates so
  the daily 9 AM cron is O(due-soon) rather than O(all-patterns).
- ``idx_expenses_recurrence`` partial — only matched-to-pattern
  expenses populate ``recurrence_id``; the partial keeps the index
  small for the 95% of unrelated transactions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "l1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "k0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- recurring_patterns -----------------------------------------
    op.create_table(
        "recurring_patterns",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),

        # Pattern identity
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("expected_amount", sa.Numeric(20, 2), nullable=False),
        # ± tolerance for matching transactions to this pattern.
        # Default 10% covers "rent went up by 5%" without re-suggesting.
        sa.Column(
            "amount_variance_pct", sa.Float(),
            server_default=sa.text("10.0"), nullable=False,
        ),

        # Schedule. Phase 3.8 only ships ``monthly``; the column is
        # already a string so quarterly/annually can be added later
        # without migrating rows.
        sa.Column(
            "schedule_type", sa.String(20),
            server_default=sa.text("'monthly'"), nullable=False,
        ),
        # 1-31. Optional — some users don't know the exact day, the
        # scheduler then falls back to a "days since last occurrence"
        # rule.
        sa.Column("expected_day_of_month", sa.Integer(), nullable=True),

        # State
        sa.Column(
            "is_active", sa.Boolean(),
            server_default=sa.text("true"), nullable=False,
        ),
        sa.Column(
            "auto_detected", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
        sa.Column(
            "user_confirmed", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),

        # Reminders
        sa.Column(
            "enable_reminders", sa.Boolean(),
            server_default=sa.text("true"), nullable=False,
        ),
        sa.Column(
            "reminder_days_before", sa.Integer(),
            server_default=sa.text("2"), nullable=False,
        ),
        sa.Column("last_reminder_sent", sa.Date(), nullable=True),
        # Snooze-until — when the user taps "trễ vài ngày" we set
        # this to today+2 so the next scheduler scan skips the row.
        sa.Column("snooze_until", sa.Date(), nullable=True),

        # Tracking
        sa.Column("last_occurrence_date", sa.Date(), nullable=True),
        sa.Column(
            "occurrence_count", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),

        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_patterns_user_active",
        "recurring_patterns",
        ["user_id", "is_active"],
    )
    # Partial index on the daily reminder scanner's WHERE clause —
    # only "active + reminders enabled" rows ever land in this index
    # so the daily 9 AM cron stays O(due-soon).
    op.create_index(
        "idx_patterns_due_soon",
        "recurring_patterns",
        ["user_id", "expected_day_of_month"],
        postgresql_where=sa.text("is_active = true AND enable_reminders = true"),
    )

    # --- pattern_suggestions_log ------------------------------------
    op.create_table(
        "pattern_suggestions_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),

        # Suggestion fingerprint — used to dedup against future
        # detections. (category, amount-bucket) collapsed to a single
        # string so a small rent change doesn't bypass the rejection
        # we previously recorded.
        sa.Column("fingerprint", sa.String(120), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("suggested_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("typical_day", sa.Integer(), nullable=True),

        # Outcome — null when first sent, updated when user reacts.
        # Values: accepted | rejected | ignored | edited
        sa.Column("outcome", sa.String(20), nullable=True),
        # If accepted, points at the created pattern for traceability.
        sa.Column(
            "pattern_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),

        sa.Column(
            "suggested_at", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["pattern_id"], ["recurring_patterns.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Find recent rejections for a user fast — detector calls this
    # for every candidate group during the nightly scan.
    op.create_index(
        "idx_suggestions_user_fingerprint",
        "pattern_suggestions_log",
        ["user_id", "fingerprint", "suggested_at"],
    )

    # --- expenses extension -----------------------------------------
    op.add_column(
        "expenses",
        sa.Column(
            "is_recurring", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
    )
    op.add_column(
        "expenses",
        sa.Column(
            "recurrence_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_expenses_recurrence",
        "expenses",
        "recurring_patterns",
        ["recurrence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Partial — only matched-to-pattern expenses get indexed. Used by
    # ``was_paid_this_period`` to avoid double-reminders.
    op.create_index(
        "idx_expenses_recurrence",
        "expenses",
        ["recurrence_id", "expense_date"],
        postgresql_where=sa.text("recurrence_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_expenses_recurrence", table_name="expenses")
    op.drop_constraint(
        "fk_expenses_recurrence", "expenses", type_="foreignkey"
    )
    op.drop_column("expenses", "recurrence_id")
    op.drop_column("expenses", "is_recurring")

    op.drop_index(
        "idx_suggestions_user_fingerprint", table_name="pattern_suggestions_log"
    )
    op.drop_table("pattern_suggestions_log")

    op.drop_index("idx_patterns_due_soon", table_name="recurring_patterns")
    op.drop_index("idx_patterns_user_active", table_name="recurring_patterns")
    op.drop_table("recurring_patterns")
