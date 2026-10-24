# Issue #339

[Story] P3.9.5-S1: Xoá câu "Đây là hình ảnh..." trong Tổng tài sản

**Parent Epic:** #334 (Epic 1: Tài sản)

## Description
Câu "Đây là hình ảnh..." dài, redundant với context, làm rối view "Tổng tài sản".

## Acceptance Criteria
- [ ] Identify exact YAML key chứa câu (likely content/menu_copy.yaml → action_assets_net_worth)
- [ ] Xoá câu (hoặc thay empty string nếu key still referenced)
- [ ] Render view "Tổng tài sản" không còn câu này
- [ ] vi-localization-checker pass
- [ ] No code references broken

## Technical Notes
- Pure content YAML change, no handler change

## Estimate: ~0.25 day
## Dependencies: None

Close #334
