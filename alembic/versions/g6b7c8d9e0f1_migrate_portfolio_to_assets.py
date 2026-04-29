"""migrate_portfolio_to_assets: copy active portfolio_assets rows into assets.

Revision ID: g6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-04-29

Data-only migration — no schema changes.

Maps portfolio_assets → assets:
  - asset_type: 'stocks'/'mutual_fund'/'fund' → 'stock';
                'life_insurance' → 'other'; others unchanged.
  - subtype:    'stocks' → 'vn_stock';
                'mutual_fund'/'fund' → 'fund'; else NULL.
  - initial_value: quantity * purchase_price  (or just purchase_price when
                   quantity is NULL, as for real-estate total-value entries).
  - current_value: quantity * current_price   (fallback chain through
                   purchase_price so the field is always non-NULL).
  - acquired_at:   created_at::date  (best-effort; no original purchase date).
  - extra:         original metadata merged with {quantity, avg_price} for
                   quantifiable assets so portfolio_service can reconstruct
                   the old API response shape.

After inserting assets, creates today's asset_snapshot for each migrated
asset (source='user_input') so net_worth_calculator.calculate_historical()
has a baseline from day-one.

Idempotent: both INSERT statements use NOT EXISTS guards so re-running on
an already-migrated database is safe.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'g6b7c8d9e0f1'
down_revision: Union[str, Sequence[str], None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Copy active portfolio_assets rows into assets
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO assets (
            id, user_id,
            asset_type, subtype,
            name,
            initial_value, current_value,
            acquired_at, last_valued_at,
            extra,
            is_active,
            created_at, updated_at
        )
        SELECT
            pa.id,
            pa.user_id,

            -- Normalise asset_type to Phase 3A enum values
            CASE pa.asset_type
                WHEN 'stocks'         THEN 'stock'
                WHEN 'mutual_fund'    THEN 'stock'
                WHEN 'fund'           THEN 'stock'
                WHEN 'life_insurance' THEN 'other'
                ELSE pa.asset_type          -- real_estate, crypto, gold, cash, other
            END,

            -- Derive subtype from old asset_type
            CASE pa.asset_type
                WHEN 'stocks'      THEN 'vn_stock'
                WHEN 'mutual_fund' THEN 'fund'
                WHEN 'fund'        THEN 'fund'
                ELSE NULL
            END,

            pa.name,

            -- initial_value = qty * purchase_price (unit_price when no qty)
            CASE
                WHEN pa.quantity IS NOT NULL AND pa.purchase_price IS NOT NULL
                    THEN ROUND((pa.quantity * pa.purchase_price)::numeric, 2)
                WHEN pa.purchase_price IS NOT NULL
                    THEN ROUND(pa.purchase_price::numeric, 2)
                ELSE 0
            END,

            -- current_value: prefer qty * current_price, fall back through chain
            CASE
                WHEN pa.quantity IS NOT NULL AND pa.current_price IS NOT NULL
                    THEN ROUND((pa.quantity * pa.current_price)::numeric, 2)
                WHEN pa.current_price IS NOT NULL
                    THEN ROUND(pa.current_price::numeric, 2)
                WHEN pa.quantity IS NOT NULL AND pa.purchase_price IS NOT NULL
                    THEN ROUND((pa.quantity * pa.purchase_price)::numeric, 2)
                WHEN pa.purchase_price IS NOT NULL
                    THEN ROUND(pa.purchase_price::numeric, 2)
                ELSE 0
            END,

            pa.created_at::date,    -- best-effort acquired_at
            NOW(),

            -- Merge original metadata with quantity/avg_price so that
            -- portfolio_service.enrich_asset_response() can reconstruct
            -- the legacy API response without extra DB queries.
            CASE
                WHEN pa.quantity IS NOT NULL
                    THEN COALESCE(pa.metadata, '{}')::jsonb
                         || jsonb_build_object(
                                'quantity',  pa.quantity,
                                'avg_price', pa.purchase_price
                            )
                ELSE COALESCE(pa.metadata, '{}')::jsonb
            END,

            true,               -- is_active
            pa.created_at,
            pa.updated_at

        FROM portfolio_assets pa
        WHERE pa.deleted_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM assets a WHERE a.id = pa.id)
    """)

    # ------------------------------------------------------------------
    # 2. Create today's snapshot for every migrated asset so that
    #    net_worth_calculator.calculate_historical() has a starting point.
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO asset_snapshots (asset_id, user_id, snapshot_date, value, source)
        SELECT
            a.id,
            a.user_id,
            CURRENT_DATE,
            a.current_value,
            'user_input'
        FROM assets a
        WHERE a.id IN (SELECT id FROM portfolio_assets WHERE deleted_at IS NULL)
          AND NOT EXISTS (
              SELECT 1 FROM asset_snapshots s
              WHERE s.asset_id = a.id
                AND s.snapshot_date = CURRENT_DATE
          )
    """)


def downgrade() -> None:
    # Cascade on asset_snapshots FK handles snapshot removal automatically.
    op.execute("""
        DELETE FROM assets
        WHERE id IN (SELECT id FROM portfolio_assets WHERE deleted_at IS NULL)
    """)
