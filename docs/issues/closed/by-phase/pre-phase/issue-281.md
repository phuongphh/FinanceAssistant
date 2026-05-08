# Issue #281

[Story] P3.9-S14: News RSS feed integration

**Parent Epic:** #265 (Epic 3: Gold + Bank Rates + News)

## User Story
As a system, I need to fetch + parse RSS feeds và lưu articles vào DB.

## Acceptance Criteria
- [ ] `app/market_data/providers/news_rss.py` dùng feedparser
- [ ] Sources: cafef.vn (chứng khoán), vnexpress kinh doanh, ndh.vn (optional)
- [ ] Cron hourly: fetch → dedupe by URL → insert vào news_articles
- [ ] DB migration: bảng news_articles
- [ ] related_symbols field initially empty
- [ ] Test với fixture XML

## Estimate: ~0.5 day
## Depends on: P3.9-S1
