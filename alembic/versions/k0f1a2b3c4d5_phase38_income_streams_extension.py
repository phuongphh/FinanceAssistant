"""phase 3.8 epic 2 — multi-income streams: extend income_streams schema

Revision ID: k0f1a2b3c4d5
Revises: j9e0f1a2b3c4
Create Date: 2026-05-06 05:00:00.000000

Phase 3.8 Epic 2 (Story P3.8-S4):

The ``income_streams`` table from Phase 3A was minimal — a single
``amount_monthly`` column assumed every income source pays monthly.
Reality is messier: dividends pay annually, freelance is ad-hoc,
rental from Epic 1 was bolted on via JSONB. Epic 2 promotes income
streams to first-class with explicit schedule + currency + lifecycle
+ proper FK to the source asset.

Schema changes:

- Rename ``source_type`` → ``stream_type`` (matches spec). VARCHAR(50)
  to leave room for future categories without another migration.
- Replace ``amount_monthly`` with raw ``amount`` + ``schedule_type``.
  Reading code (``threshold_service``, ``report_service``,
  ``market_service``) computes monthly equivalent via the model's
  ``monthly_equivalent`` property — single source of truth for the
  monthly/quarterly/annually/ad_hoc math.
- Add ``is_passive`` Bool — driven by stream type but stored explicitly
  so the agent's "thu nhập thụ động" filter is a single index-friendly
  predicate rather than an IN-list.
- Add ``currency`` (default VND), ``schedule_day`` (1-31 for monthly),
  ``schedule_month`` (1-12 for annually).
- Add ``start_date`` / ``end_date`` for stream lifecycle. ``end_date``
  null = ongoing. (Distinct from ``is_active``: a stream can be
  paused mid-life without ending.)
- Add ``source_asset_id`` UUID FK to ``assets.id`` — promotes the
  ``extra.source_asset_id`` JSONB workaround from Epic 1 to a real
  column. Backfilled from the JSONB on existing rows.
- Add ``notes`` TEXT for free-form annotations.

Backfill rules for existing rows (Phase 3A streams + Epic 1 rentals):
- ``stream_type`` ← ``source_type``
- ``amount`` ← ``amount_monthly``  (semantics: monthly amount, with
  ``schedule_type='monthly'`` so the equivalent is unchanged)
- ``schedule_type`` ← 'monthly'
- ``is_passive`` ← (source_type IN ('dividend', 'rental', 'interest'))
- ``start_date`` ← ``created_at::date``
- ``source_asset_id`` ← parsed from ``extra->>'source_asset_id'`` if
  present (Epic 1 rentals)

After backfill all NEW columns become NOT NULL where required.
``source_type`` and ``amount_monthly`` are dropped — keeping them
as transition shims would invite drift between the two
representations. Calling code is updated in the same PR.

Indexes:
- ``idx_income_user_active_streams`` (``user_id, is_active``) — kept
  for "list active streams" path.
- ``idx_income_streams_user_type`` (``user_id, stream_type, is_active``) — new,
  optimises agent's "thu nhập từ thuê BĐS" / type-filter queries. Named
  with the ``_streams_`` infix to avoid colliding with the legacy
  ``idx_income_user_type`` on ``income_records`` (Phase 2).
- ``idx_income_source_asset`` (``source_asset_id``) WHERE NOT NULL —
  partial; only rental streams populate this column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "k0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "j9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns nullable so the backfill UPDATE can run.
    op.add_column(
        "income_streams",
        sa.Column("stream_type", sa.String(50), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("is_passive", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("amount", sa.Numeric(20, 2), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column(
            "currency", sa.String(10),
            server_default=sa.text("'VND'"), nullable=False,
        ),
    )
    op.add_column(
        "income_streams",
        sa.Column("schedule_type", sa.String(20), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("schedule_day", sa.Integer(), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("schedule_month", sa.Integer(), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("start_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("end_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_income_source_asset",
        "income_streams",
        "assets",
        ["source_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Backfill from old columns. ``NULLIF`` guards against rows
    # where ``extra`` is NULL (the JSONB ``->>`` operator returns NULL
    # in that case anyway, but the explicit guard keeps the cast safe).
    op.execute("""
        UPDATE income_streams SET
            stream_type   = source_type,
            amount        = amount_monthly,
            schedule_type = 'monthly',
            start_date    = created_at::date,
            is_passive    = (source_type IN ('dividend', 'rental', 'interest')),
            source_asset_id = CASE
                WHEN extra IS NULL THEN NULL
                WHEN (extra->>'source_asset_id') IS NULL THEN NULL
                WHEN (extra->>'source_asset_id') = '' THEN NULL
                ELSE (extra->>'source_asset_id')::uuid
            END
    """)

    # 3. Lock down NOT NULL on backfilled columns.
    op.alter_column("income_streams", "stream_type", nullable=False)
    op.alter_column("income_streams", "is_passive", nullable=False)
    op.alter_column("income_streams", "amount", nullable=False)
    op.alter_column("income_streams", "schedule_type", nullable=False)
    op.alter_column("income_streams", "start_date", nullable=False)

    # 4. Drop deprecated columns. ``source_type`` and ``amount_monthly``
    # have lived their lives; calling code in this PR uses the new names.
    op.drop_column("income_streams", "source_type")
    op.drop_column("income_streams", "amount_monthly")

    # 5. New indexes for the agent's filtered queries.
    op.create_index(
        "idx_income_streams_user_type",
        "income_streams",
        ["user_id", "stream_type", "is_active"],
    )
    op.create_index(
        "idx_income_source_asset",
        "income_streams",
        ["source_asset_id"],
        postgresql_where=sa.text("source_asset_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop new fields and restore the Phase 3A two-column shape.

    Lossy: ``schedule_type``/``schedule_day``/``schedule_month``/
    ``start_date``/``end_date``/``notes`` data is dropped. Quarterly
    and annual streams are converted back to a monthly equivalent
    so downgrade still produces a coherent ``amount_monthly``."""
    op.drop_index("idx_income_source_asset", table_name="income_streams")
    op.drop_index("idx_income_streams_user_type", table_name="income_streams")

    op.add_column(
        "income_streams",
        sa.Column("source_type", sa.String(30), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("amount_monthly", sa.Numeric(15, 2), nullable=True),
    )
    op.execute("""
        UPDATE income_streams SET
            source_type    = stream_type,
            amount_monthly = CASE schedule_type
                WHEN 'monthly'    THEN amount
                WHEN 'quarterly'  THEN amount / 3
                WHEN 'annually'   THEN amount / 12
                ELSE amount
            END
    """)
    op.alter_column("income_streams", "source_type", nullable=False)
    op.alter_column("income_streams", "amount_monthly", nullable=False)

    op.drop_constraint(
        "fk_income_source_asset", "income_streams", type_="foreignkey"
    )
    op.drop_column("income_streams", "notes")
    op.drop_column("income_streams", "source_asset_id")
    op.drop_column("income_streams", "end_date")
    op.drop_column("income_streams", "start_date")
    op.drop_column("income_streams", "schedule_month")
    op.drop_column("income_streams", "schedule_day")
    op.drop_column("income_streams", "schedule_type")
    op.drop_column("income_streams", "currency")
    op.drop_column("income_streams", "amount")
    op.drop_column("income_streams", "is_passive")
    op.drop_column("income_streams", "stream_type")
