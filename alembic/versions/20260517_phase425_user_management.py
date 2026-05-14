"""Phase 4.2.5 user management manual status

Revision ID: 20260517p425users
Revises: 20260516p425tenant
Create Date: 2026-05-17 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260517p425users"
down_revision: Union[str, Sequence[str], None] = "20260516p425tenant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("manual_status", sa.String(length=50), nullable=True)
    )
    op.create_index("ix_users_manual_status", "users", ["manual_status"])


def downgrade() -> None:
    op.drop_index("ix_users_manual_status", table_name="users")
    op.drop_column("users", "manual_status")
