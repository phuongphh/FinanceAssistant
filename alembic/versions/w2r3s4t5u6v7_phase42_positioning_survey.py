"""phase4.2 epic3 positioning survey

Revision ID: w2r3s4t5u6v7
Revises: v1q2r3s4t5u6
Create Date: 2026-05-13 00:00:02.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "w2r3s4t5u6v7"
down_revision = "v1q2r3s4t5u6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positioning_survey_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("response", sa.String(length=32), nullable=False),
        sa.Column("source_prompt_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_positioning_survey_user_id"),
    )
    op.create_index(
        "idx_positioning_survey_response",
        "positioning_survey_responses",
        ["response"],
    )
    op.create_index(
        "idx_positioning_survey_created_at",
        "positioning_survey_responses",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_positioning_survey_created_at", table_name="positioning_survey_responses")
    op.drop_index("idx_positioning_survey_response", table_name="positioning_survey_responses")
    op.drop_table("positioning_survey_responses")
