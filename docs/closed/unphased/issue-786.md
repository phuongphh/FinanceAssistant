# Issue #786

[Story 3] Life Assurance Contract List View

## Summary
Create the life assurance contract list view. Shows all user's life insurance contracts with details and foot buttons for management and navigation.

## Requirements
- [ ] When "Bảo hiểm nhân thọ" is clicked, show list of all contracts:
  - Card format per contract:
    ```
    🛡️ [Company Name]
    📅 Đóng ngày: [day] hàng tháng
    💰 Số tiền/tháng: [formatted_amount]
    📆 Tất toán: [year]
    💵 Tổng đã đóng: [formatted_total]
    ```
- [ ] If no contracts: show empty state with "Thêm hợp đồng mới" prompt
- [ ] Foot buttons:
  - "⚙️ Quản lý hợp đồng BHNT" → opens CRUD flow (create/edit/delete)
  - "🔙 Quay về" → back to Asset main menu
- [ ] Each contract card can be tapped for details/edit

## Acceptance Criteria
- [ ] Contract list renders correctly with all fields
- [ ] Empty state handled
- [ ] Foot buttons work (Quản lý + Quay về)
- [ ] UI consistent with existing Asset menu styling

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Create Life Assurance contract list view:
1. List all user's contracts with full details
2. Empty state handling
3. Foot buttons: "Quản lý hợp đồng BHNT" + "Quay về"
4. Tap contract for details/edit

Branch: feature/life-assurance-contract-list
PR closes #[ISSUE_NUMBER]
```

