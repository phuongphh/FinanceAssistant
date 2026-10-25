# Issue #59

[P3A-1] Create database migrations for assets, snapshots, income_streams

## Epic
Epic 1 — Asset Data Model | **Week 1** | Blocks: P3A-2, P3A-3, P3A-4

## Description
Setup 4 database migrations để support wealth tracking:
1. `assets` table — store user's assets với JSON metadata
2. `asset_snapshots` table — daily historical values
3. `income_streams` table — salary, dividend, interest (simple)
4. Update `users` table — add wealth-related fields

## Acceptance Criteria
- [ ] Migration `xxx_create_assets.py` applied với đầy đủ columns: id, user_id, asset_type, subtype, name, description, initial_value, current_value, acquired_at, last_valued_at, metadata JSON, is_active, sold_at, sold_value, timestamps
- [ ] Migration `xxx_create_asset_snapshots.py` applied với (id, asset_id, user_id, snapshot_date, value, source) + unique constraint on (asset_id, snapshot_date)
- [ ] Migration `xxx_create_income_streams.py` applied (source_type, amount_monthly, metadata)
- [ ] Migration `xxx_add_user_wealth_fields.py` applied (primary_currency, wealth_level, expense_threshold_micro, expense_threshold_major, briefing_enabled, briefing_time)
- [ ] Indexes tạo đúng (idx_assets_user, idx_assets_type, idx_snapshots_user_date, idx_income_user)
- [ ] `downgrade()` hoạt động (test rollback)

## Technical Notes
- Dùng `sa.Numeric(20, 2)` cho money fields (không dùng Float)
- JSON metadata flexible cho mỗi loại asset
- `on_delete` cascade cho foreign keys

## Estimate
~0.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.1 — Database Schema
