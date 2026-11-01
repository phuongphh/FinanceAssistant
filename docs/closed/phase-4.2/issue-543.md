# Issue #543

[Story] P4.2-1.2: Financial Data Quality Guardrails

**Parent Epic:** #539 (Epic 1: Trust & Data Integrity)

Hardening data input: amount validation, confirm step, currency disambiguation, placeholder isolation, duplicate detection.

- [ ] Validation: amount <10k or >100ty -> confirm step
- [ ] Confirm step: 3 button estimates + escape
- [ ] Currency: <10tr VND AND segment != starter -> confirm VND/USD
- [ ] Placeholder isolation: is_placeholder_asset flag, exclude tu net worth
- [ ] Duplicate detection: same user+type+amount+/-10% trong 10 phut
- [ ] KPI digest: data_quality_warning_count dong

Close #539
