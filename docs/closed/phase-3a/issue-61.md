# Issue #61

[P3A-3] Build AssetService (CRUD + soft delete)

## Epic
Epic 1 — Asset Data Model | **Week 1** | Depends: P3A-1, P3A-2 | Blocks: P3A-6, P3A-7, P3A-8

## Description
Core service để quản lý assets. Auto-create snapshot khi create/update.

## Acceptance Criteria
- [ ] `AssetService.create_asset()` — tạo asset + first snapshot
- [ ] `AssetService.update_current_value()` — update + create/update snapshot today
- [ ] `AssetService.get_user_assets()` — support include_inactive flag
- [ ] `AssetService.get_asset_by_id()` — với user_id check (security)
- [ ] `AssetService.soft_delete()` — mark is_active=False, không xóa data
- [ ] Unit tests cover all methods
- [ ] Edge case: create asset với current_value=None → default initial_value
- [ ] Edge case: multiple updates same day → update snapshot, không duplicate

## Technical Notes
- Async methods (AsyncSession)
- Raise ValueError nếu asset không thuộc user_id
- Transaction safety (flush trước commit)

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 1.3
