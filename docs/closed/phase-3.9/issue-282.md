# Issue #282

[Story] P3.9-S15: News LLM summarization tied to holdings

**Parent Epic:** #265 (Epic 3: Gold + Bank Rates + News)

## User Story
As a user, I want brief personalized news summaries relevant to my stock holdings.

## Acceptance Criteria
- [ ] `app/market_data/analytics/news_relevance.py`:
  - tag_news_with_symbols(article): pattern match title+first 200 chars vs stock ticker dict (~700 HOSE/HNX)
  - Update news_articles.related_symbols
- [ ] get_relevant_news(user_id, limit=3): holdings intersect related_symbols
- [ ] summarize_for_user(user_id) → list[str]: 1 LLM call (DeepSeek), 3 sentence summaries
- [ ] Cost: P95 < $0.0015 per call (~500 tokens)
- [ ] Manual test: 3 personas → correct summaries

## Estimate: ~0.75 day
## Depends on: P3.9-S14
