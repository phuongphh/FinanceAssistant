from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.market_data.analytics.news_relevance import tag_news_with_symbols
from backend.market_data.providers.news_rss import NewsRSSProvider

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_news_rss_provider_parses_fixture():
    items = NewsRSSProvider.parse((FIXTURES / "news_sample.xml").read_text(), source="cafef")
    assert len(items) == 2
    assert items[0].title.startswith("VNM")
    assert items[0].related_symbols == []


def test_tag_news_with_symbols_updates_article():
    article = SimpleNamespace(title="VNM và HPG tăng mạnh", summary="Nhóm cổ phiếu thép tích cực", related_symbols=[])
    assert tag_news_with_symbols(article, {"VNM", "HPG", "VIC"}) == ["HPG", "VNM"]
    assert article.related_symbols == ["HPG", "VNM"]
