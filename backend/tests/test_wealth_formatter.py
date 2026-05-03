"""Unit tests for the wealth confirmation formatter.

Focus on the gain/loss line in ``format_asset_added`` — the rest of the
output is plain Python f-strings and isn't worth pinning.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from backend.bot.formatters.wealth_formatter import format_asset_added
from backend.wealth.models.asset import Asset


def _stock(initial: int, current: int) -> Asset:
    a = Asset()
    a.id = uuid.uuid4()
    a.user_id = uuid.uuid4()
    a.asset_type = "stock"
    a.subtype = "vn_stock"
    a.name = "VNM"
    a.initial_value = Decimal(initial)
    a.current_value = Decimal(current)
    a.acquired_at = date.today()
    a.is_active = True
    a.extra = {}
    return a


def test_loss_shows_red_arrow_with_negative_short_amount():
    # TC-1.7.C13: avg=50k, current=30k, qty=100 → -2tr loss
    asset = _stock(initial=5_000_000, current=3_000_000)
    out = format_asset_added(asset, net_worth=Decimal(3_000_000))
    assert "📉 -2tr" in out
    assert "3,000,000đ" in out  # current value, not initial


def test_gain_shows_green_arrow_with_explicit_plus():
    # TC-1.7.C14: avg=10k, current=100k, qty=100 → +9tr gain
    asset = _stock(initial=1_000_000, current=10_000_000)
    out = format_asset_added(asset, net_worth=Decimal(10_000_000))
    assert "📈 +9tr" in out
    assert "10,000,000đ" in out


def test_break_even_omits_gain_loss_line():
    # Cash / "use same price" stock: initial == current → no diff line.
    # (Stock subtype icon is also 📈, so we check for the gain "+/-" pattern,
    # not just the emoji.)
    asset = _stock(initial=5_000_000, current=5_000_000)
    out = format_asset_added(asset, net_worth=Decimal(5_000_000))
    assert "📉" not in out
    assert "📈 +" not in out
    assert "📈 -" not in out


def test_net_worth_uses_current_not_initial():
    # The summary total reflects the *current* value passed by the caller —
    # this guards against a regression where we sum initial_value instead.
    asset = _stock(initial=1_000_000, current=10_000_000)
    out = format_asset_added(asset, net_worth=Decimal(10_000_000))
    assert "10,000,000đ" in out
    assert "1,000,000đ" not in out
