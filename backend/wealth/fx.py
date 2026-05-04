"""USD ↔ VND foreign-exchange helper for non-VND-priced assets.

Used by the asset-entry wizard so foreign stocks can be entered in
their native currency (USD) and stored alongside an estimated VND
equivalent. The wizard labels the converted amount as "tạm tính"
because the rate moves daily.

Phase 3A uses a hard-coded mid-rate refreshed manually per quarter.
Phase 3B will replace this with a live FX feed (likely the same path
as ``market_service`` for crypto/gold prices).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

USD_VND_RATE: Decimal = Decimal("25000")


def usd_to_vnd(usd_amount: Decimal | float | int) -> Decimal:
    return Decimal(str(usd_amount)) * USD_VND_RATE


def parse_usd_amount(text: str) -> Decimal | None:
    """Parse a USD amount the way a Vietnamese user types it.

    Accepts: ``"150"``, ``"150.5"``, ``"$150"``, ``"150 USD"``,
    ``"1,500"`` (US thousands separator). Comma is always treated as
    a thousands separator — VN users adopt US convention for USD.

    Returns ``None`` when no positive amount can be extracted, so the
    wizard can re-prompt warmly instead of crashing on garbage input.
    """
    if not text:
        return None
    s = text.strip().lower()
    s = s.replace("$", "").replace("usd", "")
    s = s.replace(",", "").strip()
    if not s:
        return None
    try:
        amount = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return amount if amount > 0 else None
