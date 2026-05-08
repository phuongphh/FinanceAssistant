"""News relevance tagging and personalized summaries."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select

from backend.database import get_session_factory
from backend.models.news_article import NewsArticle
from backend.services.llm_service import LLMError, call_llm
from backend.wealth.models.asset import Asset

COMMON_SYMBOLS = {
    "VNM", "HPG", "VIC", "VCB", "FPT", "MWG", "MSN", "SSI", "VND", "GAS", "BID", "CTG",
    "TCB", "MBB", "ACB", "VPB", "STB", "HDB", "SHB", "TPB", "OCB", "VIB", "LPB", "EIB",
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
}


@dataclass(frozen=True, slots=True)
class RelevantNews:
    title: str
    summary: str | None
    url: str
    source: str
    related_symbols: list[str]


def tag_news_with_symbols(article: Any, symbols: set[str] | None = None) -> list[str]:
    """Pattern-match article title + first 200 summary chars against ticker dictionary."""
    dictionary = symbols or COMMON_SYMBOLS
    title = str(getattr(article, "title", "") or "")
    summary = str(getattr(article, "summary", "") or "")[:200]
    text = f"{title} {summary}".upper()
    matches = sorted(symbol for symbol in dictionary if re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", text))
    if hasattr(article, "related_symbols"):
        article.related_symbols = matches
    return matches


async def _user_symbols(db, user_id) -> set[str]:
    stmt = select(Asset.asset_type, Asset.extra, Asset.name).where(Asset.user_id == user_id, Asset.is_active.is_(True), Asset.asset_type.in_(["stock", "crypto"]))
    result = await db.execute(stmt)
    symbols: set[str] = set()
    for asset_type, extra, name in result.all():
        extra = extra or {}
        symbol = str(extra.get("ticker") or extra.get("symbol") or name or "").upper().strip()
        if symbol:
            symbols.add(symbol)
    return symbols


async def get_relevant_news(user_id, limit: int = 3) -> list[RelevantNews]:
    """Return news ordered by user-holding mentions first, then newest general news."""
    async with get_session_factory()() as db:
        user_symbols = await _user_symbols(db, user_id)
        result = await db.execute(select(NewsArticle).order_by(desc(NewsArticle.published_at)).limit(max(limit * 5, 10)))
        articles = result.scalars().all()
    def score(article: NewsArticle) -> tuple[int, Any]:
        related = set(article.related_symbols or [])
        return (1 if user_symbols and related.intersection(user_symbols) else 0, article.published_at)
    ranked = sorted(articles, key=score, reverse=True)[:limit]
    return [RelevantNews(a.title, a.summary, a.url, a.source, list(a.related_symbols or [])) for a in ranked]


def _build_prompt(news: list[RelevantNews]) -> str:
    lines = ["News last 24h:"]
    for idx, item in enumerate(news, start=1):
        tag = ",".join(item.related_symbols) if item.related_symbols else "Market"
        lines.append(f'{idx}. [{tag}]: "{item.title}" - {item.summary or ""}')
    lines.append("Task: Summarize top 3 most relevant news for THIS user, max 1 sentence each. Filter rule: news mentioning user's tickers > general market news > others.")
    return "\n".join(lines)


async def summarize_for_user(user_id) -> list[str]:
    """Generate three short personalized market-news summaries using one DeepSeek call."""
    news = await get_relevant_news(user_id, limit=3)
    if not news:
        return []
    try:
        raw = await call_llm(_build_prompt(news), task_type="market_news_summary", user_id=user_id, use_cache=False)
    except LLMError:
        return [item.title for item in news]
    summaries: list[str] = []
    for line in raw.splitlines():
        clean = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if clean:
            summaries.append(clean)
    return summaries[:3]
