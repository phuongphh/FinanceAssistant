# Issue #656

[Bug] 'Nhận lương 20tr vào tiền mặt' → ghi expense sai thay vì add income

## Summary
When user types "Hôm nay nhận lương 20tr vào tiền mặt", Bé Tiền incorrectly records it as an expense instead of adding income to asset.

## Actual Behavior
User input: "Hôm nay nhận lương 20tr vào tiền mặt"
Bé Tiền: records expense "hôm nay nhận lương 20tr vào tiền mặt" with amount 20tr
Wrong action triggered.

## Expected Behavior
Bé Tiền should parse:
- Intent: "nhận" = receive (income, NOT expense)
- Income type: "lương" = salary
- Amount: "20tr" = 20,000,000 VND
- Target asset: "tiền mặt" = cash
→ Action: add 20tr income to "tiền mặt" asset

## Steps to Reproduce
1. User types "hôm nay nhận lương 20tr vào tiền mặt"
2. Bé Tiền records it as expense instead of income to asset

## Technical Notes
- NLU incorrectly classifies "nhận" as expense instead of income/add-to-asset
- Need to distinguish between spending (expense) and receiving (income to asset)
- "nhận" = receive/incoming → ADD to asset, not expense

## Acceptance Criteria
- [ ] "Nhận" is classified as income/intake intent, NOT expense
- [ ] "Nhận lương 20tr vào tiền mặt" → adds 20tr to cash asset
- [ ] Amount, income type (lương), and target asset (tiền mặt) are correctly extracted
- [ ] General pattern "nhận [income_type] [amount] vào [asset]" works

## Claude Code Implementation Prompt
```
Read GitHub issue #656 in phuongphh/FinanceAssistant.

Fix: "Hôm nay nhận lương 20tr vào tiền mặt" should add income to asset, not record expense.

Requirements:
- Parse "nhận" as receive/income intent (NOT expense)
- Extract: income type (lương), amount (20tr), target asset (tiền mặt)
- Add amount to target asset as income

Guidelines:
- Branch: fix/nlu-receive-income
- Write tests for "nhận [type] [amount] vào [asset]" pattern
- Conventional commits
- Create draft PR linking to issue #656
```

