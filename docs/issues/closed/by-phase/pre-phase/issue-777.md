# Issue #777

[Story 3] Credit Card Menu in Chi Tiêu

## Summary
Add "Thẻ tín dụng" button in the Chi tiêu (Expense) main menu. When clicked, show a list of all user's credit cards with debt balance and closing date. Add foot buttons for management and navigation.

## Requirements
- [ ] Add "💳 Thẻ tín dụng" button in Chi tiêu main menu, right below "Quản lý chi tiêu" button
- [ ] When clicked, show a list of all user's credit cards:
  - Card format: "[bank_name] — 💳 Dư nợ: [formatted_amount]"
  - Subtitle: "Ngày tất toán: ngày [closing_date] hàng tháng"
- [ ] If no credit cards exist: show "Chưa có thẻ tín dụng nào. Tạo thẻ mới?"
- [ ] Foot buttons:
  - "⚙️ Quản lý thẻ tín dụng" → opens CRUD menu (create/edit/delete)
  - "🔙 Quay về" → back to Chi tiêu main menu
- [ ] Same UI style as current Chi tiêu menu components

## Acceptance Criteria
- [ ] "💳 Thẻ tín dụng" button visible in Chi tiêu menu
- [ ] Card list shows all cards with debt balance + closing date
- [ ] Empty state when no cards
- [ ] Foot buttons work correctly (Quản lý + Quay về)
- [ ] UI consistent with existing menu styling
- [ ] 0 regression on Chi tiêu menu

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Add Credit Card menu to Chi Tiêu:
1. Add "💳 Thẻ tín dụng" button below "Quản lý chi tiêu"
2. Card list view showing all cards (bank_name, debt_balance, closing_date)
3. Empty state handling
4. Foot buttons: "Quản lý thẻ tín dụng" + "Quay về"

Branch: feature/credit-card-menu
PR closes #[ISSUE_NUMBER]
```

