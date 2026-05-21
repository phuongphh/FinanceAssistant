# Issue #787

[Story 4] Life Assurance in Asset Report & Dashboard

## Summary
Include life assurance contracts in the Asset Report and Asset Dashboard. Each contract's total paid amount should be listed and included in the overall asset summary.

## Requirements
- [ ] Asset Report: include life assurance contracts as a section
  - Header: "🛡️ Bảo hiểm nhân thọ"
  - List each contract with company name + total paid amount
  - Subtotal: "Tổng BHNT: [formatted_total]"
- [ ] Asset Dashboard: include life assurance in asset breakdown
  - Show under existing asset categories
  - Total contributed to net worth calculation
- [ ] Format matches existing asset report/dashboard styling
- [ ] Life assurance total included in "Tổng tài sản" (Total Assets) calculation

## Acceptance Criteria
- [ ] Asset Report shows life assurance contracts with company name + total paid
- [ ] Asset Dashboard includes life assurance in asset breakdown
- [ ] Life assurance total counted in net worth
- [ ] Format consistent with other asset types

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Include Life Assurance contracts in Asset Report and Asset Dashboard:
1. Add life assurance section in Asset Report
2. Include in Asset Dashboard breakdown
3. Count in net worth calculation
4. Match existing styling

Branch: feature/life-assurance-report
PR closes #[ISSUE_NUMBER]
```

