"""Diagnostic — fetch SJC/PNJ/BTMC gold pages and report status + parser outcome.

Run on the bot host (or any machine with network access to the gold sites)
to check whether the scraper-facing URLs return parseable HTML/JSON. Prints
the HTTP status, response length, table count (HTML) or JSON top-level
keys, and the ParserError details if parsing fails.

Usage:

    PYTHONPATH=. python scripts/diag_gold_providers.py
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import httpx

from backend.market_data.providers.gold_btmc import BTMCGoldProvider
from backend.market_data.providers.gold_common import (
    BROWSER_HEADERS,
    parse_gold_table,
)
from backend.market_data.providers.gold_pnj import PNJGoldProvider
from backend.market_data.providers.gold_sjc import SJCGoldProvider


async def probe_html(label: str, url: str, symbol: str) -> None:
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


async def probe_btmc(label: str, provider: BTMCGoldProvider) -> None:
    print(f"\n=== {label} ===")
    print(f"URL: {provider.url}")
    for symbol in ("SJC_GOLD", "RING_24K"):
        try:
            quote = await provider.fetch_quote(symbol)
            print(
                f"PARSED OK [{symbol}]: "
                f"buy={quote.metadata['buy_price']:,.0f} "
                f"sell={quote.price:,.0f} "
                f"updated={quote.metadata.get('btmc_updated_at')!r}"
            )
        except Exception as exc:
            print(f"ERROR [{symbol}]: {type(exc).__name__}: {exc}")


ProbeFn = Callable[[], Awaitable[None]]


async def main() -> None:
    sjc_provider = SJCGoldProvider()
    pnj_provider = PNJGoldProvider()
    btmc_provider = BTMCGoldProvider()

    await probe_html("SJC", sjc_provider.url, "SJC_GOLD")
    await probe_html("PNJ", pnj_provider.url, "SJC_GOLD")
    await probe_btmc("BTMC", btmc_provider)


if __name__ == "__main__":
    asyncio.run(main())
