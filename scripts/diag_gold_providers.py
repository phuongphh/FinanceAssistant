"""Bakeoff diagnostic — probe 10 candidate gold-price sources at once.

Use this when the production providers (SJC/PNJ/BTMC) all fail and we
need to pick a working source without iterating through commits. Each
probe records HTTP status, content-type, body length, a body preview,
and a format classification (JSON valid? gold-relevant keywords?).

Also checks whether the `vnstock` library exposes a gold-price API,
since it is already a project dependency.

Usage on the bot host:

    PYTHONPATH=. python scripts/diag_gold_providers.py

Paste the full output back. The "winner" — first source that returns
parseable, gold-relevant data — gets promoted to a real provider.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx

from backend.market_data.providers.gold_btmc import BTMCGoldProvider
from backend.market_data.providers.gold_common import BROWSER_HEADERS
from backend.market_data.providers.gold_pnj import PNJGoldProvider
from backend.market_data.providers.gold_sjc import SJCGoldProvider


@dataclass(frozen=True)
class Probe:
    label: str
    url: str
    expect: str  # "json" / "html" / "xml"


PROBES: tuple[Probe, ...] = (
    # Sources we've already seen fail — included to confirm and watch for changes.
    Probe("SJC textContent (current primary)", "https://sjc.com.vn/giavang/textContent.php", "html"),
    Probe("PNJ blog (current secondary)", "https://www.pnj.com.vn/blog/gia-vang/", "html"),
    Probe("BTMC API (current backup)", "http://api.btmc.vn/api/BTMCAPI/getpricebtmc?key=3kd8ub1llcg9t45hnoh8hmn7t5kc2v", "json"),
    # Alternatives worth probing — different infra/WAF profiles.
    Probe("SJC mobile", "https://sjc.com.vn/m/giavang.html", "html"),
    Probe("DOJI XML feed", "https://update.dojiland.com/update.aspx?dataformat=xml", "xml"),
    Probe("DOJI mobile", "https://giavang.doji.vn/Mobile/giavang.aspx", "html"),
    Probe("CafeF AJAX gold list", "https://s.cafef.vn/Ajax/Gold_pricegoldlist.ashx?type=2", "html"),
    Probe("CafeF data gold", "https://cafef.vn/du-lieu/Ajax/AjaxGoldList.ashx", "html"),
    Probe("WebGia", "https://webgia.com/gia-vang/", "html"),
    Probe("VietnamNet gold", "https://vietnamnet.vn/kinh-doanh/gia-vang", "html"),
)

GOLD_KEYWORDS = ("vàng", "gold", "sjc", "nhẫn", "9999", "999.9")


def classify_body(body: str) -> str:
    """Best-effort classification of response body."""
    stripped = body.lstrip()[:200].lower()
    if stripped.startswith(("{", "[")):
        return "looks like JSON"
    if stripped.startswith("<?xml"):
        return "looks like XML"
    if stripped.startswith(("<!doctype", "<html", "<")):
        return "looks like HTML"
    return "unknown format"


def gold_relevance(body: str) -> str:
    found = [kw for kw in GOLD_KEYWORDS if kw in body.lower()]
    return f"keywords found: {found}" if found else "NO gold keywords found"


async def probe(p: Probe) -> None:
    print(f"\n=== {p.label} ===")
    print(f"URL: {p.url}")
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers=BROWSER_HEADERS, follow_redirects=True
        ) as client:
            response = await client.get(p.url)
    except Exception as exc:
        print(f"NETWORK_ERROR: {type(exc).__name__}: {exc}")
        return

    ct = response.headers.get("content-type", "?")
    body = response.text
    print(f"HTTP {response.status_code} | content-type={ct} | len={len(body)}")
    print(f"Final URL: {response.url}")
    if response.status_code != 200:
        print(f"Body preview: {body[:300]!r}")
        return

    print(f"Format: {classify_body(body)}")
    print(f"Relevance: {gold_relevance(body)}")
    print(f"Body preview (first 300 chars): {body[:300]!r}")

    if p.expect == "json":
        try:
            data = json.loads(body)
            keys = list(data.keys()) if isinstance(data, dict) else "(list)"
            print(f"JSON parsed OK; top-level keys: {keys}")
        except Exception as exc:
            print(f"JSON parse FAILED: {type(exc).__name__}: {exc}")


def vnstock_check() -> None:
    print("\n=== vnstock library (already in deps) ===")
    try:
        import vnstock  # noqa: F401
    except Exception as exc:
        print(f"Import failed: {type(exc).__name__}: {exc}")
        return

    version = getattr(vnstock, "__version__", "unknown")
    print(f"vnstock {version} imported OK")

    candidate_attrs = (
        "gold",
        "gold_price",
        "sjc_gold",
        "Gold",
        "Vnstock",
        "Quote",
        "Listing",
    )
    for attr in candidate_attrs:
        if hasattr(vnstock, attr):
            obj = getattr(vnstock, attr)
            print(f"  has `vnstock.{attr}` -> {type(obj).__name__}")

    # Some versions expose a top-level API class.
    try:
        from vnstock import Vnstock  # type: ignore
        client = Vnstock()
        print(f"  Vnstock() instance: {type(client).__name__}")
        for attr in dir(client):
            if "gold" in attr.lower():
                print(f"    method/attr containing 'gold': {attr}")
    except Exception as exc:
        print(f"  Vnstock() unavailable: {type(exc).__name__}: {exc}")


async def probe_existing_providers() -> None:
    print("\n=== Existing providers (sanity check) ===")
    for label, provider in (
        ("SJCGoldProvider", SJCGoldProvider()),
        ("PNJGoldProvider", PNJGoldProvider()),
        ("BTMCGoldProvider", BTMCGoldProvider()),
    ):
        try:
            quote = await provider.fetch_quote("SJC_GOLD")
            print(f"{label}: OK buy={quote.metadata['buy_price']:,.0f} sell={quote.price:,.0f}")
        except Exception as exc:
            print(f"{label}: FAIL — {type(exc).__name__}: {exc}")


async def dump_btmc_rows() -> None:
    """Print BTMC rows that the classifier matches plus all gold-keyword rows.

    BTMC's endpoint returns 1000+ rows, the vast majority silver/jewelry.
    Dumping just the first 15 hides the rows that actually classify, so we
    instead surface (a) every row the current classifier picks up and
    (b) every row whose name contains a gold/SJC/nhẫn keyword. That's the
    minimum needed to design a tighter pattern.
    """
    from backend.market_data.providers.gold_btmc import (
        _BUY_PREFIXES,
        _NAME_PREFIXES,
        _SELL_PREFIXES,
    )

    print("\n=== BTMC matcher trace ===")
    provider = BTMCGoldProvider()
    try:
        response = await provider._fetch_response()
        rows = provider._parse_body(response.text, response.headers.get("content-type", ""))
    except Exception as exc:
        print(f"BTMC fetch/parse failed: {type(exc).__name__}: {exc}")
        return

    print(f"Total rows: {len(rows)}")

    def render(idx: int, row: dict, cls: str | None) -> str:
        suffix = provider._row_suffix(row) or "?"
        name = provider._row_field(row, suffix, _NAME_PREFIXES)
        buy = provider._row_field(row, suffix, _BUY_PREFIXES, prefer_k=True)
        sell = provider._row_field(row, suffix, _SELL_PREFIXES, prefer_k=True)
        return (
            f"  [{idx:4}] suffix={suffix!s:<4} cls={cls!s:<10} "
            f"name={str(name)[:60]!r:<65} buy={buy} sell={sell}"
        )

    # 1) Every row the current classifier matches — including the one that
    #    produced the suspicious 16.45M reading.
    print("\n-- Rows classified by current matcher --")
    classified: list[tuple[int, dict, str]] = []
    for i, row in enumerate(rows):
        suffix = provider._row_suffix(row)
        if suffix is None:
            continue
        name = provider._row_field(row, suffix, _NAME_PREFIXES)
        if not name:
            continue
        cls = provider._classify_name(str(name))
        if cls is not None:
            classified.append((i, row, cls))
    if not classified:
        print("  (no rows match — the previous SJC_GOLD response was a stale cache hit?)")
    for idx, row, cls in classified[:30]:
        print(render(idx, row, cls))
    if len(classified) > 30:
        print(f"  ... and {len(classified) - 30} more classified rows")

    # 2) Every gold-keyword row, regardless of current classifier verdict.
    #    Lets us see the canonical SJC bullion name BTMC actually uses.
    print("\n-- Rows with gold keywords (vàng / sjc / nhẫn / miếng) --")
    keywords = ("vàng", "sjc", "nhẫn", "nhan", "miếng", "mieng")
    matched_kw = []
    for i, row in enumerate(rows):
        suffix = provider._row_suffix(row)
        if suffix is None:
            continue
        name_raw = provider._row_field(row, suffix, _NAME_PREFIXES)
        if not name_raw:
            continue
        lowered = str(name_raw).lower()
        if any(kw in lowered for kw in keywords):
            matched_kw.append((i, row, provider._classify_name(str(name_raw))))
    print(f"  ({len(matched_kw)} rows match a gold keyword)")
    for idx, row, cls in matched_kw[:25]:
        print(render(idx, row, cls))
    if len(matched_kw) > 25:
        print(f"  ... and {len(matched_kw) - 25} more gold-keyword rows")


async def main() -> None:
    vnstock_check()
    for p in PROBES:
        await probe(p)
    await probe_existing_providers()
    await dump_btmc_rows()


if __name__ == "__main__":
    asyncio.run(main())
