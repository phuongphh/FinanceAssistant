#!/usr/bin/env python3
"""Probe VN stock data providers and report which are alive.

Run this from a host with outbound HTTPS to ssi/vndirect/tcbs. It hits a
handful of candidate endpoints with browser-ish headers and prints
status + a short body excerpt + parsed price (when recognisable) so you
can tell at a glance which upstream is still serving quotes and which is
dead. Read-only — no DB, no Redis, no project imports beyond the
provider classes.

Usage:
    python scripts/diag_stock_providers.py                # default VNM
    python scripts/diag_stock_providers.py VNM FPT HPG    # custom tickers
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
COMMON_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi,en;q=0.9",
}


def _ssi_headers() -> dict[str, str]:
    return {
        **COMMON_HEADERS,
        "Origin": "https://iboard.ssi.com.vn",
        "Referer": "https://iboard.ssi.com.vn/",
    }


def _vnd_headers() -> dict[str, str]:
    return {
        **COMMON_HEADERS,
        "Origin": "https://dstock.vndirect.com.vn",
        "Referer": "https://dstock.vndirect.com.vn/",
    }


def _tcbs_headers() -> dict[str, str]:
    return {
        **COMMON_HEADERS,
        "Origin": "https://tcinvest.tcbs.com.vn",
        "Referer": "https://tcinvest.tcbs.com.vn/",
    }


def _candidates(ticker: str) -> list[tuple[str, str, dict[str, str], dict[str, str]]]:
    """Return (label, url, params, headers) tuples to probe."""
    return [
        (
            "SSI iboard dchart defaultAllStocks (current code path)",
            "https://iboard.ssi.com.vn/dchart/api/1.1/defaultAllStocks",
            {"symbol": ticker},
            _ssi_headers(),
        ),
        (
            "SSI iboard-query stock/group (HOSE list)",
            "https://iboard-query.ssi.com.vn/v2/stock/group",
            {"group": "HOSE"},
            _ssi_headers(),
        ),
        (
            "SSI iboard-api company by-code",
            "https://iboard-api.ssi.com.vn/statistics/company/by-code",
            {"code": ticker},
            _ssi_headers(),
        ),
        (
            "VNDIRECT api-finfo stock_prices (current backup)",
            "https://api-finfo.vndirect.com.vn/v4/stock_prices",
            {"q": f"code:{ticker}", "size": "1"},
            _vnd_headers(),
        ),
        (
            "TCBS apipubaws second-tc-price",
            "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/second-tc-price",
            {"ticker": ticker},
            _tcbs_headers(),
        ),
        (
            "TCBS apipubaws bars-long-term (1d)",
            "https://apipubaws.tcbs.com.vn/stock-insight/v2/stock/bars-long-term",
            {"ticker": ticker, "type": "stock", "resolution": "D", "countBack": "1"},
            _tcbs_headers(),
        ),
    ]


def _extract_price_hint(payload: Any) -> str:
    """Best-effort hint about whether the payload actually carries a price."""
    def _walk(obj: Any, depth: int = 0) -> str | None:
        if depth > 4:
            return None
        if isinstance(obj, dict):
            for key in (
                "matchedPrice", "lastPrice", "closePrice", "close",
                "price", "last", "matchPrice", "c",
            ):
                if key in obj and obj[key] not in (None, "", 0):
                    return f"{key}={obj[key]}"
            for value in obj.values():
                hit = _walk(value, depth + 1)
                if hit:
                    return hit
        elif isinstance(obj, list):
            for item in obj[:5]:
                hit = _walk(item, depth + 1)
                if hit:
                    return hit
        return None

    return _walk(payload) or "no price field detected"


async def _probe(client: httpx.AsyncClient, label: str, url: str, params: dict[str, str], headers: dict[str, str]) -> None:
    try:
        response = await client.get(url, params=params, headers=headers, timeout=8.0)
    except httpx.HTTPError as exc:
        print(f"  [ERR ] {label}")
        print(f"         {type(exc).__name__}: {exc}")
        return
    body = response.text
    excerpt = body[:200].replace("\n", " ")
    price_hint = ""
    if response.status_code == 200:
        try:
            price_hint = f"  price={_extract_price_hint(json.loads(body))}"
        except json.JSONDecodeError:
            price_hint = "  body is not JSON"
    print(f"  [{response.status_code:>3}] {label}{price_hint}")
    print(f"         {excerpt}")


async def main(tickers: list[str]) -> int:
    if not tickers:
        tickers = ["VNM"]
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for ticker in tickers:
            print(f"\n=== {ticker} ===")
            for label, url, params, headers in _candidates(ticker):
                await _probe(client, label, url, params, headers)

    print(
        "\nLegend: 200 with a 'price=' hint means the provider is alive and"
        " serving usable data. 403/404/empty bodies mean it needs a different"
        " endpoint, auth, or origin."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
