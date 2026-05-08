# Issue #283

[Story] P3.9-S16: Morning briefing enrichment (real data)

**Parent Epic:** #266 (Epic 4: Enhanced Briefing + Analytics + Alerts)

## User Story
As a user, I want my morning briefing to show real market data, portfolio performance, and relevant news — so I start my day informed.

## Acceptance Criteria
- [ ] `content/briefing.yaml` template mới 5 sections:
  1. Tổng tài sản + change vs hôm qua/tuần
  2. Thị trường sáng nay (VN-Index, Gold, BTC)
  3. Portfolio breakdown (% allocation, today's change)
  4. Top 3 relevant news
  5. Insights (rule-based, max 2)
- [ ] `app/briefing/morning_briefing.py`: parallel fetch via asyncio.gather
- [ ] Render time <2s P95
- [ ] Insights generator (rule-based, không LLM):
  - Stock tăng >5% → "Có thể chốt lời 1 phần?"
  - Bank rate thấp hơn VCB >0.5% → "Cân nhắc chuyển ngân hàng"
- [ ] Stale data banner footer nếu price is_stale=True
- [ ] All existing tests pass + 8 new tests
- [ ] Manual: 4 personas → briefing render đúng

## Estimate: ~1.5 days
## Depends on: P3.9-S9, P3.9-S12, P3.9-S15
