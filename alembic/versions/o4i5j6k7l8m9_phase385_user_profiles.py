"""phase 3.8.5 epic 2 — user profiles

Revision ID: o4i5j6k7l8m9
Revises: n3h4i5j6k7l8
Create Date: 2026-05-07 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "o4i5j6k7l8m9"
down_revision: Union[str, Sequence[str], None] = "n3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(50), nullable=True),
        sa.Column("age_range", sa.String(10), nullable=True),
        sa.Column("briefing_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("briefing_time", sa.Time(), nullable=False, server_default=sa.text("'07:00:00'")),
        sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reminder_time", sa.Time(), nullable=False, server_default=sa.text("'09:00:00'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "age_range IS NULL OR age_range IN ('20-29', '30-39', '40-49', '50+')",
            name="ck_user_profiles_age_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_profiles")
