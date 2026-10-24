# Issue #166

[Story] P3.6-S6: Wire menu actions for Dòng tiền, Mục tiêu, Thị trường

**Parent Epic:** #158 (Epic 1: Menu Structure & Content)

## User Story
As a user exploring "Dòng tiền" và "Mục tiêu" categories mới, tôi muốn mỗi action dẫn tới useful information — không phải error messages.

## Acceptance Criteria

### Dòng tiền (4 actions):
- [ ] `menu:cashflow:overview` → reuse Phase 3.5 `QueryCashflowHandler`
- [ ] `menu:cashflow:income` → reuse Phase 3.5 `QueryIncomeHandler`
- [ ] `menu:cashflow:compare` → 6-month income vs expense (text-based + Mini App link)
- [ ] `menu:cashflow:saving_rate` → calculate và show monthly saving rate %

### Mục tiêu (4 actions):
- [ ] `menu:goals:list` → reuse Phase 3.5 `QueryGoalsHandler`
- [ ] `menu:goals:add` → add-goal wizard (stub nếu chưa có, tạo issue Phase 4)
- [ ] `menu:goals:update` → list goals → user chọn → update progress
- [ ] `menu:goals:advisor` → AdvisoryHandler với "lộ trình mục tiêu" context

### Thị trường (5 actions):
- [ ] `menu:market:vnindex` → Phase 3.5 `QueryMarketHandler` với ticker=VNINDEX
- [ ] `menu:market:stocks` → list user's owned stocks + watchlist
- [ ] `menu:market:crypto` → top 5 crypto prices (BTC, ETH, etc.)
- [ ] `menu:market:gold` → SJC + PNJ gold prices
- [ ] `menu:market:advisor` → AdvisoryHandler với "cơ hội đầu tư mới" context

### General:
- [ ] **Test:** All 13 actions handled gracefully (real data OR coming-soon message)
- [ ] No silent failures
- [ ] "Add goal" nếu chưa có wizard → stub "Tính năng đang phát triển" + tạo issue Phase 4
- [ ] Watchlist nếu chưa có → "feature coming soon"

## Estimate: ~1 day
## Depends on: P3.6-S4
