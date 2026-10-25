# Issue #785

[Story 2] Add Bảo hiểm nhân thọ Button in Asset Menu

## Summary
Add "Bảo hiểm nhân thọ" button in the Asset submenu, right below "Quản lý tài sản" button, with its own callback handler.

## Requirements
- [ ] Add "🛡️ Bảo hiểm nhân thọ" button in Asset submenu
- [ ] Position: immediately below "Quản lý tài sản" button
- [ ] Button has dedicated callback handler that routes to life assurance contract list view
- [ ] If no contracts exist: show "Chưa có hợp đồng bảo hiểm nhân thọ nào. Thêm mới?"
- [ ] Wire callback to Story 3 (contract list view)

## Acceptance Criteria
- [ ] Button visible in Asset submenu at correct position
- [ ] Clicking button triggers correct callback
- [ ] Empty state when no contracts
- [ ] 0 regression on Asset menu

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Add "🛡️ Bảo hiểm nhân thọ" button in Asset submenu under "Quản lý tài sản" with dedicated callback handler.

Branch: feature/life-assurance-menu-button
PR closes #[ISSUE_NUMBER]
```

