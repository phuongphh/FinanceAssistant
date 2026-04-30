# Issue #118: [Story] P3.5-S5: Build read query handlers (8 handlers)

**GitHub:** https://github.com/phuongphh/FinanceAssistant/issues/118  
**Status:** Open

---

**Parent Epic:** #110 (Epic 1: Intent Foundation & Patterns)

## User Story
As a user asking "tài sản của tôi có gì?", I expect Bé Tiền to fetch my actual assets và respond với beautifully formatted summary reflecting my real data.

## Acceptance Criteria
- [ ] File `app/intent/handlers/base.py` với abstract `IntentHandler` class
- [ ] **8 concrete handlers** implemented:
  - `query_assets.py` — list assets by type, top 3 per type với "...và X mục nữa"
  - `query_net_worth.py` — total + change vs last month
  - `query_portfolio.py` — chỉ stocks/funds với current value
  - `query_expenses.py` — transactions in time range (top 10 by amount)
  - `query_expenses_by_category.py` — filtered by category + time
  - `query_income.py` — list income streams + total
  - `query_market.py` — current price + personal context (user's holding)
  - `query_goals.py` — list active goals với progress
- [ ] Mỗi handler implement `async handle(intent, user) -> str`
- [ ] Reuse existing services từ Phase 3A
- [ ] Handle empty state gracefully (not crash)
- [ ] Handle errors gracefully (no stack trace to user)
- [ ] Dùng `format_money_short()` và `format_money_full()` từ Phase 1

### Critical: query_market personal context
- [ ] Nếu user sở hữu ticker → show quantity + current value: "bạn sở hữu 100 cổ, giá trị 4.5tr"
- [ ] Unknown ticker → "Mình chưa biết về mã X"

- [ ] **Test: 11 real queries trigger correct handler và return non-empty response**
- [ ] Mỗi handler có ≥1 unit test

## Estimate: ~2 days
## Depends on: P3.5-S1, P3.5-S4
## Reference: `docs/current/phase-3.5-detailed.md` § 1.4
