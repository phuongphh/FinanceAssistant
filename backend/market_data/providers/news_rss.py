"""RSS feed provider for Vietnamese market news."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
try:
    import feedparser
except ModuleNotFoundError:  # pragma: no cover - CI may install dependency later.
    feedparser = None
from xml.etree import ElementTree

from backend.market_data.exceptions import ParserError, ProviderUnavailable


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    summary: str | None
    url: str
    source: str
    published_at: datetime
    related_symbols: list[str]


DEFAULT_FEEDS = {
    "cafef": "https://cafef.vn/thi-truong-chung-khoan.rss",
    "vnexpress": "https://vnexpress.net/rss/kinh-doanh.rss",
}


class NewsRSSProvider:
    """Fetch and parse RSS feeds into normalized NewsItem objects."""

    def __init__(self, *, feeds: dict[str, str] | None = None, timeout: float = 5.0, client: httpx.AsyncClient | None = None) -> None:
        self.feeds = feeds or DEFAULT_FEEDS
        self.timeout = timeout
        self._client = client

    async def fetch_all(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        for source, url in self.feeds.items():
            html = await self._fetch(url)
            items.extend(self.parse(html, source=source))
        return items

    @staticmethod
    def parse(xml: str, *, source: str) -> list[NewsItem]:
        if feedparser is None:
            return _parse_with_elementtree(xml, source=source)
        parsed = feedparser.parse(xml)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ParserError(f"Invalid RSS feed for {source}")
        items: list[NewsItem] = []
        for entry in parsed.entries:
            url = str(getattr(entry, "link", "") or "").strip()
            title = str(getattr(entry, "title", "") or "").strip()
            if not url or not title:
                continue
            summary = str(getattr(entry, "summary", "") or "").strip() or None
            published = _entry_datetime(entry)
            items.append(NewsItem(title, summary, url, source, published, []))
        return items

    async def _fetch(self, url: str) -> str:
        if self._client is not None:
            response = await self._client.get(url)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
        if response.status_code >= 400:
            raise ProviderUnavailable(f"RSS source unavailable: HTTP {response.status_code}")
        return response.text


def _entry_datetime(entry: Any) -> datetime:
    for attr in ("published", "updated"):
        value = getattr(entry, attr, None)
        if value:
            try:
                dt = parsedate_to_datetime(str(value))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _parse_with_elementtree(xml: str, *, source: str) -> list[NewsItem]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ParserError(f"Invalid RSS feed for {source}") from exc
    items: list[NewsItem] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        url = (node.findtext("link") or "").strip()
        if not title or not url:
            continue
        summary = (node.findtext("description") or "").strip() or None
        pub = (node.findtext("pubDate") or "").strip()
        try:
            published_at = parsedate_to_datetime(pub) if pub else datetime.now(timezone.utc)
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except Exception:
            published_at = datetime.now(timezone.utc)
        items.append(NewsItem(title, summary, url, source, published_at, []))
    return items
