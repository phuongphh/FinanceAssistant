"""phase 3.8 epic 1 — rental fields on assets

Revision ID: j9e0f1a2b3c4
Revises: i8d9e0f1a2b3
Create Date: 2026-05-06 04:30:00.000000

Phase 3.8 Epic 1 (Story P3.8-S1):

Adds two columns to ``assets`` so a real-estate row can carry the
landlord-side rental data (rent, expenses, occupancy, optional
tenant info, lease dates, deposit) without an extra table:

- ``is_rental`` (Boolean, default False, NOT NULL) — fast filter for
  "BĐS đang cho thuê" queries. Defaulting False keeps every existing
  asset unchanged on upgrade.
- ``rental_metadata`` (JSONB, nullable) — per-property landlord data.
  JSONB shape is validated by ``backend.wealth.schemas.rental.RentalMetadata``
  in the service layer; the DB stays permissive so future schema
  evolution doesn't need another migration.

A partial index on ``(user_id) WHERE is_rental AND is_active`` keeps
"list my rentals" snappy without bloating writes for the 95% of users
with no rental. Non-rentals don't touch the index at all.

Money inside ``rental_metadata`` (monthly_rent, monthly_expenses,
deposit_held) is stored as JSON numbers and parsed back through
``Decimal`` in the schema layer — same convention as ``Asset.extra``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "j9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "i8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "is_rental",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "assets",
        sa.Column("rental_metadata", postgresql.JSONB(), nullable=True),
    )
    # Partial index — only the small subset of (active rental) rows
    # land in the index, so reads of "list my rentals" stay O(active
    # rentals) regardless of how many cash/stock/gold assets the user
    # has, and writes on non-rental assets cost nothing.
    op.create_index(
        "idx_assets_rental_active",
        "assets",
        ["user_id"],
        postgresql_where=sa.text("is_rental = true AND is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_assets_rental_active", table_name="assets")
    op.drop_column("assets", "rental_metadata")
    op.drop_column("assets", "is_rental")
