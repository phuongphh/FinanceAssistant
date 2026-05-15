# Issue #649

improve: Add today's date to cashflow title

## Summary
Add today's date to the cashflow title: change "Dòng tiền tháng này" to "Dòng tiền tháng này tính đến hôm nay [date]".

## Motivation
Users need to know the date context for cashflow data. Adding "tính đến hôm nay [date]" provides clarity on when the data was calculated.

## Requirements
- [ ] Change title from "Dòng tiền tháng này" to "Dòng tiền tháng này tính đến hôm nay DD/MM/YYYY"
- [ ] Use today's date in DD/MM/YYYY format (Vietnamese locale)
- [ ] Date updates dynamically each day

## Technical Notes
- Affected file(s): Cashflow menu view
- Use client-side date with DD/MM/YYYY format
- Dynamic date — not hardcoded

## Acceptance Criteria
- [ ] Title shows "Dòng tiền tháng này tính đến hôm nay 15/05/2026" (or current date)
- [ ] Date updates daily
- [ ] Format is DD/MM/YYYY

## Out of Scope
- Changing other cashflow texts or features

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

In Cashflow menu:
1. Change title from "Dòng tiền tháng này" to "Dòng tiền tháng này tính đến hôm nay DD/MM/YYYY"
2. Use dynamic client-side date in DD/MM/YYYY format
3. Date refreshes daily

Guidelines:
- Branch: improve/cashflow-date-title
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

