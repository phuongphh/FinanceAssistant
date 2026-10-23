# Issue #650

fix: Fix recurring income calculation in cashflow view

## Summary
Fix the cashflow income calculation logic so that recurring/fixed income items (e.g., salary 50tr/tháng, rent 10tr/tháng) display their exact fixed amounts instead of being calculated incorrectly.

## Motivation
The current cashflow view may be calculating or averaging fixed recurring incomes incorrectly. For example, a salary of 50tr/month should display as exactly 50tr in the monthly cashflow, not a calculated or prorated amount. Users need accurate fixed income figures to understand their true monthly cashflow.

## Requirements
- [ ] Fixed/recurring income items show their exact fixed monthly amount
- [ ] Salary 50tr/tháng → displays as 50tr in cashflow
- [ ] Rent 10tr/tháng → displays as 10tr in cashflow
- [ ] Ensure the calculation does not prorate, average, or modify fixed amounts
- [ ] Variable income items can still use existing calculation logic

## Technical Notes
- Affected file(s): Cashflow income calculation logic
- Distinguish between fixed (recurring) and variable income sources
- Fixed income: use the exact recurring amount
- Variable income: use existing calculation

## Acceptance Criteria
- [ ] Salary 50tr/month shows exactly 50tr in cashflow
- [ ] Rent 10tr/month shows exactly 10tr in cashflow
- [ ] Variable income calculations remain unchanged
- [ ] Total income reflects correct sum of fixed + variable

## Out of Scope
- Changing expense calculation logic
- Changing how income is stored/entered

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Fix cashflow income calculation logic:
1. Identify fixed/recurring income items (e.g., salary, rent)
2. Display exact fixed monthly amounts (50tr salary → 50tr, 10tr rent → 10tr)
3. Do not prorate, average, or modify fixed amounts
4. Variable income items keep existing calculation logic
5. Total income = sum of fixed + variable

Guidelines:
- Branch: fix/cashflow-fixed-income
- Conventional commits
- Write tests for fixed vs variable income cases
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

