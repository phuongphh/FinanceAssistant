"""phase4.3 epic1 twin comprehension

Revision ID: 20260518p43twincomp
Revises: 20260518p425license
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260518p43twincomp"
down_revision = "20260518p425license"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twin_label_mapping",
        sa.Column("probability_code", sa.String(3), primary_key=True),
        sa.Column("vi_label", sa.String(50), nullable=False),
        sa.Column("emoji", sa.String(8), nullable=False),
        sa.Column("en_fallback", sa.String(50), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.bulk_insert(
        sa.table(
            "twin_label_mapping",
            sa.column("probability_code", sa.String),
            sa.column("vi_label", sa.String),
            sa.column("emoji", sa.String),
            sa.column("en_fallback", sa.String),
            sa.column("description", sa.String),
        ),
        [
            {
                "probability_code": "P10",
                "vi_label": "Khiêm tốn",
                "emoji": "🌧️",
                "en_fallback": "Conservative",
                "description": "Kịch bản thận trọng nhất",
            },
            {
                "probability_code": "P50",
                "vi_label": "Bình thường",
                "emoji": "⛅",
                "en_fallback": "Expected",
                "description": "Kịch bản trung tính Bé Tiền tin tưởng nhất",
            },
            {
                "probability_code": "P90",
                "vi_label": "Lạc quan",
                "emoji": "☀️",
                "en_fallback": "Optimistic",
                "description": "Kịch bản tốt nhất",
            },
        ],
    )
    op.add_column(
        "users",
        sa.Column(
            "twin_show_technical_terms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "twin_show_technical_terms")
    op.drop_table("twin_label_mapping")
