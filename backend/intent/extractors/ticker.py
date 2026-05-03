"""Whitelist-based ticker extractor.

Vietnamese-text-aware: handles "VN-Index", "vnindex", "bitcoin",
"ethereum", and the VN30 / common ETF / major crypto tickers. The
whitelist is the safety net that stops false positives like the word
"BAN" or "MUA" showing up as tickers — only known symbols are returned.

Order of precedence per call:
  1. VN-Index variations ("vn-index", "vnindex", "vn index")
  2. Vietnamese crypto names ("bitcoin", "ethereum") → BTC / ETH
  3. Whitelist match against uppercase 2-5 letter tokens
"""
from __future__ import annotations

import re

# Common VN30 + popular tickers. Curated rather than exhaustive: a hit
# in the whitelist is high-precision; a miss falls through to "unknown
# ticker" which the handler can still gracefully surface.
VN_TICKERS: frozenset[str] = frozenset({
    # VN30 popular
    "VNM", "VIC", "VHM", "VRE", "VCB", "TCB", "MBB", "ACB", "VPB",
    "BID", "CTG", "STB", "HPG", "HSG", "MWG", "MSN", "FPT", "PNJ",
    "REE", "GAS", "PLX", "POW", "SAB", "BVH", "PDR", "NVL", "DGC",
    "VJC", "TPB", "SSI", "HDB", "VIB",
    # ETFs
    "E1VFVN30", "FUEVFVND", "FUESSV30", "FUESSVFL",
    # Indices
    "VNINDEX", "VN30", "HNX", "HNXINDEX", "UPCOM",
})

CRYPTO_TICKERS: frozenset[str] = frozenset({
    "BTC", "ETH", "BNB", "USDT", "USDC", "SOL", "ADA",
    "DOT", "DOGE", "MATIC", "AVAX", "LINK", "XRP", "LTC",
})

ALL_TICKERS = VN_TICKERS | CRYPTO_TICKERS

_VN_INDEX_RE = re.compile(r"vn[\s\-_]?index", re.IGNORECASE)
_UPPERCASE_TOKEN_RE = re.compile(r"\b[A-Z]{2,8}\b")

_CRYPTO_NAME_TO_TICKER: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "binance coin": "BNB",
    "solana": "SOL",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "polygon": "MATIC",
}


def extract(text: str) -> str | None:
    """Return a known ticker from ``text`` or None.

    Long-form names ("bitcoin") win over coincidental uppercase tokens
    so "Bitcoin VS BTC" still resolves cleanly to BTC.
    """
    if not text:
        return None

    if _VN_INDEX_RE.search(text):
        return "VNINDEX"

    lower = text.lower()
    for name, sym in _CRYPTO_NAME_TO_TICKER.items():
        if name in lower:
            return sym

    upper = text.upper()
    for candidate in _UPPERCASE_TOKEN_RE.findall(upper):
        if candidate in ALL_TICKERS:
            return candidate
    return None


__all__ = ["extract", "VN_TICKERS", "CRYPTO_TICKERS", "ALL_TICKERS"]
