# Issue #375

[Story] P4A-S1: Asset class return distributions

**Parent Epic:** #369 (Epic 1: Twin Engine)

## Description
Define μ (mean annual return) và σ (annual std) cho 7 asset classes dựa vào historical VN + global data.

## Acceptance Criteria
- [ ] `backend/twin/engine/distributions.py` exports `get_distribution(asset_class) → ReturnDistribution`
- [ ] 7 classes: stocks_vn, stocks_global, crypto, gold, cash_savings, real_estate_vn, bonds_vn
- [ ] Source citation in docstring
- [ ] Externalizable to `content/twin_distributions.yaml`
- [ ] Unit test: all classes return non-zero μ, σ > 0
- [ ] Disclaimer "historical ≠ future" prominent

## Estimate: ~0.5 day
## Dependencies: None

Close #369
