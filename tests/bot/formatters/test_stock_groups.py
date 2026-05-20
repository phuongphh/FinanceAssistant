"""Unit tests for the stock-board grouping helpers.

These functions decide which holdings get sent to SSI/VNDIRECT and which
fall back to the user's portfolio price. Regressions here directly drive
circuit-breaker poisoning (see backend/bot/formatters/stock_groups.py
module docstring), so the edge cases are worth pinning down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.bot.formatters.stock_groups import (
    GROUP_ETF,
    GROUP_FOREIGN,
    GROUP_FUND,
    GROUP_ORDER,
    GROUP_VN_STOCK,
    QUOTABLE_GROUPS,
    classify_asset,
    collect_quotable_tickers,
    group_assets,
)


@dataclass
class _FakeAsset:
    subtype: str | None = None
    name: str | None = None
    extra: dict[str, Any] | None = field(default_factory=dict)


def test_etf_remains_quotable():
    """SSI/VNDIRECT quote ETFs on iBoard — don't strand them in fallback."""
    assert GROUP_ETF in QUOTABLE_GROUPS
    assert GROUP_VN_STOCK in QUOTABLE_GROUPS
    assert GROUP_FUND not in QUOTABLE_GROUPS
    assert GROUP_FOREIGN not in QUOTABLE_GROUPS


@pytest.mark.parametrize(
    "subtype,expected",
    [
        ("vn_stock", GROUP_VN_STOCK),
        ("VN_STOCK", GROUP_VN_STOCK),
        ("  vn_stock  ", GROUP_VN_STOCK),
        ("etf", GROUP_ETF),
        ("fund", GROUP_FUND),
        ("foreign_stock", GROUP_FOREIGN),
        ("", GROUP_VN_STOCK),
        (None, GROUP_VN_STOCK),
        ("unknown_subtype", GROUP_VN_STOCK),
    ],
)
def test_classify_asset(subtype, expected):
    assert classify_asset(_FakeAsset(subtype=subtype)) == expected


def test_group_assets_orders_and_buckets_by_subtype():
    assets = [
        _FakeAsset(subtype="vn_stock", extra={"ticker": "TPB"}),
        _FakeAsset(subtype="etf", extra={"ticker": "E1VFVN30"}),
        _FakeAsset(subtype="fund", extra={"ticker": "DCDS"}),
        _FakeAsset(subtype="foreign_stock", extra={"ticker": "NVDA"}),
        _FakeAsset(subtype="vn_stock", extra={"ticker": "VHM"}),
    ]
    buckets = group_assets(assets)

    assert list(buckets.keys())[:4] == list(GROUP_ORDER)
    assert [e.ticker for e in buckets[GROUP_VN_STOCK]] == ["TPB", "VHM"]
    assert [e.ticker for e in buckets[GROUP_ETF]] == ["E1VFVN30"]
    assert [e.ticker for e in buckets[GROUP_FUND]] == ["DCDS"]
    assert [e.ticker for e in buckets[GROUP_FOREIGN]] == ["NVDA"]


def test_group_assets_uppercases_and_strips_ticker():
    assets = [_FakeAsset(subtype="vn_stock", extra={"ticker": "  tpb  "})]
    buckets = group_assets(assets)
    assert buckets[GROUP_VN_STOCK][0].ticker == "TPB"


def test_group_assets_falls_back_to_name_when_extra_missing():
    assets = [
        _FakeAsset(subtype="vn_stock", name="VHM", extra=None),
        _FakeAsset(subtype="vn_stock", name="hpg", extra={}),
    ]
    buckets = group_assets(assets)
    assert [e.ticker for e in buckets[GROUP_VN_STOCK]] == ["VHM", "HPG"]


def test_group_assets_skips_assets_with_no_ticker():
    assets = [
        _FakeAsset(subtype="vn_stock", name=None, extra=None),
        _FakeAsset(subtype="vn_stock", name="", extra={"ticker": ""}),
        _FakeAsset(subtype="vn_stock", name="TPB"),
    ]
    buckets = group_assets(assets)
    assert [e.ticker for e in buckets[GROUP_VN_STOCK]] == ["TPB"]


def test_collect_quotable_tickers_dedups_across_groups():
    assets = [
        _FakeAsset(subtype="vn_stock", extra={"ticker": "TPB"}),
        _FakeAsset(subtype="vn_stock", extra={"ticker": "tpb"}),
        _FakeAsset(subtype="etf", extra={"ticker": "E1VFVN30"}),
        _FakeAsset(subtype="fund", extra={"ticker": "DCDS"}),
        _FakeAsset(subtype="foreign_stock", extra={"ticker": "NVDA"}),
    ]
    buckets = group_assets(assets)
    quotable = collect_quotable_tickers(buckets)

    assert "TPB" in quotable
    assert "E1VFVN30" in quotable
    assert "DCDS" not in quotable
    assert "NVDA" not in quotable
    assert len(quotable) == len(set(quotable))


def test_collect_quotable_tickers_empty_when_only_non_quotable_groups():
    assets = [
        _FakeAsset(subtype="fund", extra={"ticker": "DCDS"}),
        _FakeAsset(subtype="foreign_stock", extra={"ticker": "NVDA"}),
    ]
    buckets = group_assets(assets)
    assert collect_quotable_tickers(buckets) == []
