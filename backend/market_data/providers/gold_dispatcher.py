"""Gold provider dispatcher: PNJ Edge JSON primary, BTMC XML secondary.

The HTML scrapers we used to favour are dead in production:
- SJC's `textContent.php` always returns 403 (TLS-fingerprint WAF).
- PNJ's `/blog/gia-vang/` is now Next.js — server returns 0 tables.

PNJ exposes a clean public Edge API (`edge-api.pnj.io/.../get-gold-price`)
that breaks SJC bullion (`masp=SJC`) out from 24K nhẫn (`masp=N24K`) — the
most accurate per-product feed available without a deal. BTMC's XML feed
keeps working as the backup; it's reliable but quotes the two products at
parity on most days.
"""
from __future__ import annotations

from backend.market_data.providers.base_dispatcher import Dispatcher
from backend.market_data.providers.gold_btmc import BTMCGoldProvider
from backend.market_data.providers.gold_pnj_json import PNJJSONGoldProvider


def build_gold_dispatcher(redis_client, *, timeout: float = 5.0) -> Dispatcher:
    return Dispatcher(
        PNJJSONGoldProvider(timeout=timeout),
        BTMCGoldProvider(timeout=timeout),
        redis_client,
        timeout=timeout,
    )
