# Issue #655

[Bug] 'Chi tiêu dashboard' → Bé Tiền show báo cáo thay vì mở Dashboard

## Summary
When user types "Chi tiêu dashboard", Bé Tiền shows expense report instead of opening Expense Dashboard.

## Actual Behavior
User input: "Chi tiêu dashboard"
Bé Tiền: shows expense report
Wrong action triggered.

## Expected Behavior
Bé Tiền should parse:
- Intent keywords: "chi" or "chi tiêu" = expense
- Menu keyword: "dashboard"
→ Action: open Expense Dashboard (not just show report)

## Steps to Reproduce
1. User types "chi tiêu dashboard"
2. Bé Tiền shows expense report instead of opening dashboard

## Technical Notes
- Need to map "chi"/"chi tiêu" to expense context AND detect "dashboard" as specific menu item
- Current NLU only sees "chi tiêu" → expense report, ignores "dashboard" as sub-menu

## Acceptance Criteria
- [ ] "Chi tiêu dashboard" opens Expense Dashboard
- [ ] "Chi dashboard" also works (short form)
- [ ] Other "chi tiêu [menu]" patterns work correctly

## Claude Code Implementation Prompt
```
Read GitHub issue #655 in phuongphh/FinanceAssistant.

Fix: "Chi tiêu dashboard" should open Expense Dashboard, not show report.

Requirements:
- Parse "chi"/"chi tiêu" as expense intent
- Detect "dashboard" as specific sub-menu target
- Route to Expense Dashboard view

Guidelines:
- Branch: fix/nlu-expense-dashboard
- Handle both "chi tiêu" and "chi" short form
- Write tests
- Conventional commits
- Create draft PR linking to issue #655
```

