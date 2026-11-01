# Issue #126

[Story] P3.5-S13: Implement wealth-level adaptive responses

**Parent Epic:** #112 (Epic 3: Personality & Advisory)

## User Story
As a Starter user với 15tr tiền mặt, tôi muốn simple "💵 Tiền mặt: 15tr — đang xây dựng tài sản!" — không phải wall of YTD returns và Sharpe ratios dành cho HNW user.

## Wealth-Level Response Matrix

| Level | Range | Response Style |
|-------|-------|---------------|
| Starter | 0-30tr | Simple, encouraging, no jargon, hide metrics |
| Young Professional | 30-200tr | Growth context, suggest investments |
| Mass Affluent | 200tr-1tỷ | Full breakdown, change tracking, allocation % |
| HNW | 1tỷ+ | Portfolio analytics, YTD return, advisor-level |

## Acceptance Criteria
- [ ] Update 4 handlers để wealth-level aware: query_assets, query_net_worth, query_portfolio, query_cashflow
- [ ] Detect level từ `app/wealth/ladder.py`
- [ ] Starter: simple language, encouraging ("đang xây dựng", "bước đầu tốt"), ẩn %, rates
- [ ] Young Prof: add growth context (vs last month), suggest investment options
- [ ] Mass Affluent: full breakdown, change tracking, analytics
- [ ] HNW: detailed portfolio analytics, YTD return, diversification
- [ ] **Test: Same query "tài sản của tôi có gì" → 4 distinctly different responses cho 4 mock users**
- [ ] No starter user sees HNW-level metrics
- [ ] Dùng composition, không duplicate handler code

## Estimate: ~1 day
## Depends on: P3.5-S12
## Reference: `docs/current/phase-3.5-detailed.md` § 2.3
