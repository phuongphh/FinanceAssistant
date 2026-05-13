"""phase4.1 feedback SLA columns + partial index

Revision ID: s8m9n0p1q2r3
Revises: r7l8m9n0p1q2
Create Date: 2026-05-12 00:00:01.000000

Phase 4.1 — Story A.7 feedback triage. Adds the timestamp fields the
SLA worker uses for "answered" / "alerted" bookkeeping, plus a partial
index so the open-feedback scan is cheap as the table grows.

The spec uses ``status = 'open'`` in the partial index predicate, but
the existing schema (Phase 3.8.5) uses ``status = 'new'`` for unread
feedback. We index on the existing constant to avoid breaking the
classifier job that filters on the same column.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "s8m9n0p1q2r3"
down_revision = "r7l8m9n0p1q2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedbacks",
        sa.Column("first_responded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "feedbacks",
        sa.Column("sla_breach_alerted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "feedbacks",
        sa.Column("onboarding_emoji_signal", sa.String(length=16), nullable=True),
    )

    # Partial index for the SLA worker: unanswered feedback only.
    # ``status = 'new'`` mirrors FEEDBACK_STATUS_NEW from the model so
    # we don't need a schema-rewrite to align with the spec wording.
    op.execute(
        "CREATE INDEX idx_feedback_unanswered_age "
        "ON feedbacks (created_at) "
        "WHERE status = 'new' AND first_responded_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_feedback_unanswered_age")
    op.drop_column("feedbacks", "onboarding_emoji_signal")
    op.drop_column("feedbacks", "sla_breach_alerted_at")
    op.drop_column("feedbacks", "first_responded_at")
