"""Group user stock holdings by subtype for the portfolio price board.

Background: ``_action_market_stock_board`` used to call SSI/VNDIRECT for
every ticker in the user's portfolio, including funds (DCDS, E120, TCEF)
and foreign stocks (NVDA, IBM) that those providers cannot serve.
Each unsupported lookup counted as a provider failure and quickly
opened the circuit breaker, which then starved legitimate VN tickers
of live quotes too. Grouping holdings by ``Asset.subtype`` lets the
handler route only the quotable subset through the dispatcher and
display the rest with the user's last known portfolio price.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.wealth.models.asset import Asset


GROUP_VN_STOCK = "vn_stock"
GROUP_FUND_ETF = "fund_etf"
GROUP_FOREIGN = "foreign_stock"

# Display order — VN first (largest cohort), then funds, then foreign.
GROUP_ORDER: tuple[str, ...] = (GROUP_VN_STOCK, GROUP_FUND_ETF, GROUP_FOREIGN)

# Only this group has a working live-quote provider chain today.
QUOTABLE_GROUPS: frozenset[str] = frozenset({GROUP_VN_STOCK})

_SUBTYPE_TO_GROUP: dict[str, str] = {
    "vn_stock": GROUP_VN_STOCK,
    "fund": GROUP_FUND_ETF,
    "etf": GROUP_FUND_ETF,
    "foreign_stock": GROUP_FOREIGN,
}


@dataclass(frozen=True)
class StockGroupEntry:
    """One row in the grouped stock board."""

    group: str
    ticker: str
    asset: Any  # backend.wealth.models.asset.Asset


def classify_asset(asset: "Asset") -> str:
    """Map an Asset to one of the display groups.

    Falls back to ``vn_stock`` for legacy rows with no subtype — the
    current wizard always sets one, so the fallback only matters for
    very old assets that pre-date the subtype field.
    """
    subtype = (asset.subtype or "").strip().lower()
    return _SUBTYPE_TO_GROUP.get(subtype, GROUP_VN_STOCK)


def group_assets(assets: list["Asset"]) -> dict[str, list[StockGroupEntry]]:
    """Bucket assets by display group, preserving input order within each bucket."""
    buckets: dict[str, list[StockGroupEntry]] = {key: [] for key in GROUP_ORDER}
    for asset in assets:
        ticker = str((asset.extra or {}).get("ticker") or asset.name or "").upper().strip()
        if not ticker:
            continue
        group = classify_asset(asset)
        buckets.setdefault(group, []).append(
            StockGroupEntry(group=group, ticker=ticker, asset=asset)
        )
    return buckets


def collect_quotable_tickers(buckets: dict[str, list[StockGroupEntry]]) -> list[str]:
    """Return the de-duplicated list of tickers we should send to providers."""
    seen: list[str] = []
    for group in QUOTABLE_GROUPS:
        for entry in buckets.get(group, []):
            if entry.ticker not in seen:
                seen.append(entry.ticker)
    return seen
