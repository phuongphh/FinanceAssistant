"""Diagnostic — fetch SJC/PNJ gold pages and report status + parser outcome.

Run on the bot host (or any machine with network access to the gold sites)
to check whether the scraper-facing URLs return parseable HTML. Prints the
HTTP status, response length, table count, first match row preview, and
the ParserError details if parsing fails.

Usage:

    PYTHONPATH=. python scripts/diag_gold_providers.py
"""
from __future__ import annotations

import asyncio

import httpx

from backend.market_data.providers.gold_common import (
    BROWSER_HEADERS,
    parse_gold_table,
)
from backend.market_data.providers.gold_pnj import PNJGoldProvider
from backend.market_data.providers.gold_sjc import SJCGoldProvider


async def probe(label: str, url: str, symbol: str) -> None:
    print(f"\n=== {label} ===")
    print(f"URL: {url}")
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers=BROWSER_HEADERS, follow_redirects=True
        ) as client:
            response = await client.get(url)
    except Exception as exc:
        print(f"NETWORK_ERROR: {type(exc).__name__}: {exc}")
        return

    print(f"HTTP {response.status_code} (len={len(response.text)})")
    print(f"Final URL after redirects: {response.url}")
    if response.status_code != 200:
        print(f"Body preview: {response.text[:300]!r}")
        return

    try:
        buy, sell, updated = parse_gold_table(
            response.text, symbol=symbol, source_label=label
        )
        print(f"PARSED OK: buy={buy:,.0f} sell={sell:,.0f} updated={updated!r}")
    except Exception as exc:
        print(f"PARSER ERROR: {type(exc).__name__}: {exc}")


async def main() -> None:
    sjc_provider = SJCGoldProvider()
    pnj_provider = PNJGoldProvider()
    await probe("SJC", sjc_provider.url, "SJC_GOLD")
    await probe("PNJ", pnj_provider.url, "SJC_GOLD")


if __name__ == "__main__":
    asyncio.run(main())
