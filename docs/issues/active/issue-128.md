# Issue #128

[Story] P3.5-S15: Add follow-up suggestions as inline buttons

**Parent Epic:** #112 (Epic 3: Personality & Advisory)

## User Story
As a user vừa nhận được câu trả lời, tôi muốn Bé Tiền suggest câu hỏi tiếp theo tự nhiên — turning each response thành launching pad cho deeper exploration.

## Acceptance Criteria
- [ ] Suggestions là **inline keyboard buttons**, không chỉ text
- [ ] Buttons trigger pre-defined intents on tap
- [ ] Wealth-aware: Starter sees beginner suggestions, HNW sees advanced
- [ ] Suggestions per intent (min 3 each):
  - query_assets → "📈 So với tháng trước", "🏠 Chỉ BĐS", "💎 Tổng net worth"
  - query_expenses → "📅 Tuần này", "🍕 Theo loại", "📊 So sánh"
  - query_market → "💼 Portfolio của tôi", "📊 Xem thêm mã"
  - query_net_worth → "📊 Phân bổ chi tiết", "📈 Trend 6 tháng"
- [ ] Suggestions không duplicate what user just asked
- [ ] Maximum 3 suggestions per response (không clutter)
- [ ] Callback format: `intent:{intent_type}:{params_encoded}`
- [ ] Callback handler translates back to intent execution
- [ ] All 8 read handlers return responses với relevant suggestions

## Estimate: ~0.5 day
## Depends on: P3.5-S12
