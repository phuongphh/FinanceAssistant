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
from backend.market_data.providers.gold_pnj_json import PNJJSONGoldProvider
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
    print("\n=== Existing providers (sanity check, SJC_GOLD then RING_24K) ===")
    for label, provider in (
        ("SJCGoldProvider", SJCGoldProvider()),
        ("PNJGoldProvider", PNJGoldProvider()),
        ("BTMCGoldProvider", BTMCGoldProvider()),
        ("PNJJSONGoldProvider", PNJJSONGoldProvider()),
    ):
        for symbol in ("SJC_GOLD", "RING_24K"):
            try:
                quote = await provider.fetch_quote(symbol)
                print(
                    f"{label} [{symbol}]: OK "
                    f"buy={quote.metadata['buy_price']:,.0f} "
                    f"sell={quote.price:,.0f}"
                )
            except Exception as exc:
                print(f"{label} [{symbol}]: FAIL — {type(exc).__name__}: {exc}")


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

    # 1b) Full key dump for the FIRST classified row of each kind, so we can
    #     see which field carries the weight/unit (per chỉ vs per lượng vs
    #     per gram). 16.45M for "VÀNG MIẾNG SJC" is ~2 chỉ — the real per-
    #     lượng price has to be reconstructed from a unit field we're not
    #     reading yet.
    print("\n-- Full key dump of first classified row per symbol --")
    seen: set[str] = set()
    for idx, row, cls in classified:
        if cls in seen:
            continue
        seen.add(cls)
        print(f"  Row [{idx}] cls={cls}:")
        for key in sorted(row.keys()):
            if key.startswith("@") or "_" not in key:
                value = row[key]
                if value not in (None, ""):
                    print(f"    {key} = {value!r}")

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
    await dump_pnj_next_data()


async def dump_pnj_next_data() -> None:
    """Find PNJ's machine-readable gold-price source.

    PNJ's `/site/gia-vang` page is Next.js, so the visible HTML has zero
    `<table>` elements but the SSR data ships as `<script id="__NEXT_DATA__">
    {...}</script>`. Strategy:
      1. Fetch /site/gia-vang.
      2. Pull out the __NEXT_DATA__ script tag, parse its JSON.
      3. Walk recursively, collect any subtree whose keys/values mention
         "vàng", "gold", "sjc", "nhẫn", "buy", "sell", "price" so we can
         see the canonical schema without dumping the whole tree (often
         hundreds of KB).
      4. Also probe a few candidate REST endpoints so we know if there's
         a simpler API behind the scenes.
    """
    import json as _json
    from bs4 import BeautifulSoup as _BS

    print("\n=== PNJ machine-readable source hunt ===")
    url = "https://www.pnj.com.vn/site/gia-vang"
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers=BROWSER_HEADERS, follow_redirects=True
        ) as client:
            response = await client.get(url)
    except Exception as exc:
        print(f"PNJ fetch failed: {type(exc).__name__}: {exc}")
        return

    print(f"GET {url} -> {response.status_code} (len={len(response.text)})")
    if response.status_code != 200:
        return

    soup = _BS(response.text, "lxml")
    next_script = soup.find("script", attrs={"id": "__NEXT_DATA__"})
    if next_script is None:
        # Try alternative inline-JSON patterns.
        candidates = [
            s for s in soup.find_all("script")
            if s.string and ("__NEXT_DATA__" in s.string or "__INITIAL_STATE__" in s.string)
        ]
        print(f"No <script id='__NEXT_DATA__'> found; alternative inline scripts: {len(candidates)}")
        for s in candidates[:2]:
            content = (s.string or "")[:500]
            print(f"  inline preview: {content!r}")
    else:
        try:
            data = _json.loads(next_script.string or "")
        except Exception as exc:
            print(f"__NEXT_DATA__ JSON parse failed: {type(exc).__name__}: {exc}")
            print(f"raw preview: {(next_script.string or '')[:500]!r}")
        else:
            print(f"__NEXT_DATA__ keys: {list(data.keys())}")
            _dump_relevant_subtrees(data, depth=0, hits_left=8)

    # Probe likely REST endpoints PNJ might expose.
    for api_url in (
        "https://www.pnj.com.vn/api/v1/golds",
        "https://www.pnj.com.vn/site/api/gia-vang",
        "https://giavang.pnj.com.vn/api/getgiavang",
        "https://edge-api.pnj.io/ecom-frontend/v1/get-gold-price",
    ):
        try:
            async with httpx.AsyncClient(
                timeout=5.0, headers=BROWSER_HEADERS, follow_redirects=True
            ) as client:
                r = await client.get(api_url)
        except Exception as exc:
            print(f"\n{api_url} -> NETWORK_ERROR: {type(exc).__name__}: {exc}")
            continue
        ct = r.headers.get("content-type", "?")
        print(f"\n{api_url}\n  -> HTTP {r.status_code} ({ct}, len={len(r.text)})")
        if r.status_code == 200:
            print(f"  preview: {r.text[:300]!r}")


def _dump_relevant_subtrees(node, *, depth: int, path: str = "", hits_left: int) -> int:
    """Recursively print JSON subtrees whose keys/values look gold-relevant.

    Cap output via `hits_left` so we don't dump megabytes when the tree is
    massive. Returns updated `hits_left` so the caller can short-circuit.
    """
    keywords = ("vàng", "gold", "sjc", "nhẫn", "nhan", "buy", "sell", "gia", "price")
    if hits_left <= 0 or depth > 8:
        return hits_left
    if isinstance(node, dict):
        for key, value in node.items():
            key_lower = str(key).lower()
            if any(kw in key_lower for kw in keywords):
                preview = repr(value)[:300]
                print(f"  {path}.{key}: {preview}")
                hits_left -= 1
                if hits_left <= 0:
                    return hits_left
                continue
            hits_left = _dump_relevant_subtrees(
                value, depth=depth + 1, path=f"{path}.{key}", hits_left=hits_left
            )
    elif isinstance(node, list):
        for i, item in enumerate(node[:5]):
            hits_left = _dump_relevant_subtrees(
                item, depth=depth + 1, path=f"{path}[{i}]", hits_left=hits_left
            )
    return hits_left


if __name__ == "__main__":
    asyncio.run(main())
