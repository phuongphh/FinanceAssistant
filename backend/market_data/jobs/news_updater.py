"""Hourly RSS news updater."""
from __future__ import annotations

import logging
import time

from sqlalchemy.dialects.postgresql import insert

from backend.database import get_session_factory
from backend.market_data.providers.news_rss import NewsRSSProvider
from backend.models.news_article import NewsArticle

logger = logging.getLogger(__name__)


async def update_news_articles() -> dict[str, int]:
    started = time.perf_counter()
    items = await NewsRSSProvider().fetch_all()
    async with get_session_factory()() as db:
        inserted = 0
        for item in items:
            stmt = insert(NewsArticle).values(
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                published_at=item.published_at,
                related_symbols=item.related_symbols,
            ).on_conflict_do_nothing(index_elements=["url"])
            result = await db.execute(stmt)
            inserted += int(result.rowcount or 0)
        await db.commit()
    metrics = {"articles_fetched": len(items), "articles_inserted": inserted, "duration_ms": int((time.perf_counter() - started) * 1000)}
    logger.info("News updater complete: %s", metrics)
    return metrics
