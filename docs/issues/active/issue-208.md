# Issue #208

[Epic] Phase 3.8 — Epic 5: Goals Management Complete

## Phase 3.8 — Epic 5: Goals Management Complete

> **Type:** Epic | **Week:** 2 | **Stories:** 3

## Tại Sao Epic Này Quan Trọng
Phase 3.6 menu có goals actions nhưng đang là **stubs** ("Tính năng đang phát triển"). Epic này replace toàn bộ stubs bằng full CRUD với 7 goal templates + projection service.

## "Templates > Wizards"
User goals thường fall vào 5-7 patterns (mua xe, mua nhà, du lịch, hưu trí, học vấn, đám cưới, quỹ khẩn cấp). Templates nhanh hơn blank wizard.

## Success Definition
- ✅ User chọn từ 7 templates HOẶC tạo custom goal
- ✅ Projection: months_remaining, required_monthly_savings, feasibility level
- ✅ Phase 3.6 menu actions ALL functional (no more stubs)
- ✅ Phase 3.7 agent query được goals

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.8-S13: Goal model + templates YAML
- [ ] [Story] P3.8-S14: GoalProjectionService + feasibility analysis
- [ ] [Story] P3.8-S15: Goal wizard + CRUD via Telegram

## Dependencies
✅ Epic 4 (cashflow data needed for saving rate calculation)

## Reference
`docs/current/phase-3.8/phase-3.8-detailed.md` § 2.2
