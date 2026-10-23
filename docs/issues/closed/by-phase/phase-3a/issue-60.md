# Issue #60

[P3A-2] Implement Asset + AssetSnapshot + IncomeStream models

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-1 | Blocks: P3A-3, P3A-4

## Description
Tạo SQLAlchemy models matching với migrations. Thêm helper methods và enums.

## Acceptance Criteria
- [ ] File `app/wealth/models/asset.py` — Asset model đầy đủ columns
- [ ] File `app/wealth/models/asset_snapshot.py` — AssetSnapshot model
- [ ] File `app/wealth/models/income_stream.py` — IncomeStream model
- [ ] File `app/wealth/models/asset_types.py` — AssetType enum (CASH, STOCK, REAL_ESTATE, CRYPTO, GOLD, OTHER)
- [ ] File `content/asset_categories.yaml` — đầy đủ 6 loại với icons, labels, subtypes
- [ ] Helper `get_asset_config(asset_type)` load từ YAML
- [ ] Helper `get_subtypes(asset_type)` return subtypes dict
- [ ] Unit tests cho models (create, read, update)

## Technical Notes
- Dùng `relationship()` để link Asset ↔ AssetSnapshot
- Hybrid property cho `gain_loss = current_value - initial_value`

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.1 & § 1.2
