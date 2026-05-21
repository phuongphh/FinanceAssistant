# Issue #783

[Epic] Life Assurance — Bảo hiểm nhân thọ

## Summary
Add Life Assurance (Bảo hiểm nhân thọ) as a sub-type of Asset. Users can create and manage life insurance contracts, view them in the Asset menu, and see them in asset reports and dashboard.

## Motivation
Life insurance is a significant financial commitment for many Vietnamese users. Tracking these contracts alongside other assets gives a complete financial picture. Users need to know their total paid amount, monthly obligation, and contract end date — all in one place.

## Issues
- [#784](https://github.com/phuongphh/FinanceAssistant/issues/784) Life Assurance Data Model & Service
- [#785](https://github.com/phuongphh/FinanceAssistant/issues/785) Add "Bảo hiểm nhân thọ" Button in Asset Menu
- [#786](https://github.com/phuongphh/FinanceAssistant/issues/786) Life Assurance Contract List View
- [#787](https://github.com/phuongphh/FinanceAssistant/issues/787) Life Assurance in Asset Report & Dashboard

## Acceptance Criteria
- [ ] Life Assurance model created with all required fields (company, monthly payment date, monthly amount, contract end year, total paid)
- [ ] Button "Bảo hiểm nhân thọ" in Asset submenu under "Quản lý tài sản"
- [ ] Contract list view shows all contracts with details + foot buttons
- [ ] Asset Report and Asset Dashboard include life insurance contracts with total paid amount
- [ ] 0 P0 regression on existing asset features

## Out of Scope
- Insurance claim tracking
- Beneficiary management
- Policy document upload

## Claude Code Implementation Prompt
```
Read Epic #783 and all sub-issues (#784-#787) in phuongphh/FinanceAssistant.

Implement Life Assurance as asset sub-type:
1. Create life_insurance_contracts model (company_name, monthly_payment_date, monthly_amount, contract_end_year, total_paid)
2. Add "Bảo hiểm nhân thọ" button in Asset submenu
3. Contract list view with details + foot buttons
4. Include in Asset Report and Asset Dashboard

Guidelines:
- Branch: feature/life-assurance
- Life assurance is a sub-type of Asset (extend existing asset model)
- Vietnamese UI text
- Conventional commits (feat:)
- Write tests for CRUD + report inclusion
- Create draft PR linking to epic #783
```

