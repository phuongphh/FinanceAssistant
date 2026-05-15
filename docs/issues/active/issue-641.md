# Issue #641

[Epic] Enhance UI/UX 5 — Asset privacy, Bé Tiền tone, natural language, cashflow fixes

## Summary
Enhance UI/UX for the Finance Assistant app focusing on Asset menu improvements, cashflow display fixes, and natural language chat-first positioning.

## Motivation
Based on user feedback, several UI/UX pain points need addressing: asset privacy, inconsistent labels, missing date context, and incorrect income logic in cashflow view. These changes make the app more intuitive and user-friendly.

## Issues

### Asset Menu (Issues 1-6)
- [ ] **Issue 1:** Hide/show total asset amount with eye button
- [ ] **Issue 2:** Reword Bé Tiền note with natural chat tone
- [ ] **Issue 3:** Add asset category note in Asset Management
- [ ] **Issue 4:** Rename foot button "BĐS cho thuê" → "Cho thuê BĐS"
- [ ] **Issue 5:** Change "Hủy" → "Quay về menu" in new asset form
- [ ] **Issue 6:** Change land asset icon from house to tree icon

### Expense Menu (Issue 7)
- [ ] **Issue 7:** Reorder guidance in Expense Management — chat-first

### Cashflow Menu (Issues 8-9)
- [ ] **Issue 8:** Add today's date to cashflow title
- [ ] **Issue 9:** Fix recurring income calculation logic in cashflow view

## Acceptance Criteria
- [ ] All 9 sub-issues are implemented and verified
- [ ] Asset total can be toggled hide/show
- [ ] All text changes use Bé Tiền's natural tone
- [ ] Cashflow title includes today's date
- [ ] Recurring income shows correct fixed amounts

## Out of Scope
- Backend API changes (unless required by Issue 9)
- Other menus not listed above

## Claude Code Implementation Prompt
```
Read GitHub issues for Epic "Enhance UI/UX 5" in phuongphh/FinanceAssistant (issues covering Asset privacy, Bé Tiền tone, natural language, cashflow fixes).

Implement ALL sub-issues under this epic. Guidelines:
- Branch: improve/enhance-ui-ux-5
- All text changes must use Bé Tiền's natural, friendly tone (Vietnamese)
- Follow existing UI patterns (Telegram Mini App / webapp)
- Conventional commits (improve:, fix:)
- Create draft PR linking to this epic

Key changes:
1. Add eye toggle button to hide/show total asset amount (mask with *)
2. Reword Bé Tiền note in Asset menu with natural chat tone
3. Add asset category note in Asset Management
4. Rename "BĐS cho thuê" → "Cho thuê BĐS" foot button
5. "Hủy" → "Quay về menu" in new asset form, triggers return to main menu
6. Change land asset icons from house 🏠 to tree 🌳 icon in rental real estate card
7. Move natural language guidance to top in Expense Management
8. Add today's date to "Dòng tiền tháng này" title
9. Fix cashflow income logic: recurring income (salary 50tr/th, rent 10tr/th) shows exact fixed amounts
```

