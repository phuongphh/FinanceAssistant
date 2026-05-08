"""Shared parsing helpers for Vietnamese gold scrapers."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from bs4 import BeautifulSoup

from backend.market_data.exceptions import ParserError, SymbolNotFound


# Vietnamese gold sites (sjc.com.vn, pnj.com.vn) reject the default
# python-httpx User-Agent at the WAF/CDN layer. SJC also runs a
# stricter WAF that checks for browser-shaped Sec-Fetch-* / encoding
# headers, so we send a full Chrome 124 fingerprint.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}


_GOLD_ALIASES = {
    "SJC_GOLD": ("sjc",),
    "RING_24K": ("nhẫn", "nhan", "24k", "9999"),
}


def parse_vnd_decimal(value: str) -> Decimal:
    """Parse Vietnamese price strings into VND Decimal values."""
    text = value.replace("\xa0", " ").strip().lower()
    numbers = re.findall(r"\d+(?:[.,]\d+)*", text)
    if not numbers:
        raise ParserError(f"Missing numeric gold price: {value!r}")
    raw = numbers[-1]
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        raw = raw.replace(",", ".") if len(parts[-1]) <= 2 else raw.replace(",", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    parsed = Decimal(raw)
    if parsed < Decimal("1000"):
        parsed *= Decimal("1000000")
    elif parsed < Decimal("100000"):
        parsed *= Decimal("1000")
    return parsed


def _html_preview(html: str, limit: int = 240) -> str:
    """Collapse whitespace and truncate HTML for diagnostic logs.

    Keeps parser error messages diagnosable without dumping multi-KB pages
    into the log. Logs first N chars of the body (post-collapse) plus the
    response length, so a structurally-empty/JS-rendered page is obvious.
    """
    collapsed = re.sub(r"\s+", " ", html).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit] + f"... [+{len(collapsed) - limit} chars]"


def parse_gold_table(html: str, *, symbol: str, source_label: str) -> tuple[Decimal, Decimal, str | None]:
    """Extract buy/sell prices and update text from SJC/PNJ-like HTML tables."""
    soup = BeautifulSoup(html, "lxml")
    update_text = None
    page_text = soup.get_text(" ", strip=True)
    match = re.search(r"(?:cập nhật|update)[^0-9]*(\d{1,2}[:/]\d{1,2}[^|]*)", page_text, re.I)
    if match:
        update_text = match.group(1).strip()

    rows = soup.find_all("tr")
    if not rows:
        raise ParserError(
            f"{source_label} gold table not found "
            f"(html_len={len(html)} table_count={len(soup.find_all('table'))} "
            f"preview={_html_preview(html)!r})"
        )

    aliases = _GOLD_ALIASES.get(symbol.upper())
    if aliases is None:
        raise SymbolNotFound(f"Unsupported gold symbol: {symbol}")

    for row in rows:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        name = cells[0].lower()
        normalized_name = name.replace("ẫ", "a").replace("ắ", "a")
        if not any(alias in name or alias in normalized_name for alias in aliases):
            continue
        numeric_cells = [cell for cell in cells[1:] if re.search(r"\d", cell)]
        if len(numeric_cells) < 2:
            raise ParserError(f"{source_label} gold row missing buy/sell prices")
        return parse_vnd_decimal(numeric_cells[0]), parse_vnd_decimal(numeric_cells[1]), update_text

    raise SymbolNotFound(f"{source_label} gold symbol not found: {symbol}")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
