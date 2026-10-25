# Issue #342

[Story] P3.9.5-S4: Click vào dòng tài sản → mở edit flow

**Parent Epic:** #335 (Epic 2: Dashboard)

## Description
Dashboard "Báo cáo tài sản" liệt kê assets theo group nhưng không actionable. Cho phép click row → mở edit wizard.

## Acceptance Criteria
- [ ] Mỗi row asset trong dashboard có inline button/callback dashboard:edit:<asset_id>
- [ ] Click → mở edit wizard của asset_entry.py cho asset đó (reuse existing)
- [ ] Nếu row đại diện 1 group → show list để chọn 1 asset cụ thể
- [ ] Edit thành công → quay về dashboard với data refreshed
- [ ] Layer contract: handler call asset_service.update, không direct DB write
- [ ] Service NEVER calls db.commit

## Estimate: ~0.5 day
## Dependencies: None

Close #335
