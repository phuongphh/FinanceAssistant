"""Tests for the shared movers formatter."""
from __future__ import annotations

import uuid
from decimal import Decimal

from backend.bot.formatters.movers import format_movers_block, format_movers_line
from backend.wealth.services.net_worth_calculator import AssetMover


def _mover(name: str, asset_type: str, pct: float) -> AssetMover:
    return AssetMover(
        asset_id=uuid.uuid4(),
        name=name,
        asset_type=asset_type,
        current_value=Decimal("1000000"),
        previous_value=Decimal("1000000"),
        change_absolute=Decimal("0"),
        change_percentage=pct,
    )


def test_format_movers_line_basic():
    movers = [
        _mover("VIC", "stock", 15.0),
        _mover("MSB", "stock", 2.0),
        _mover("BTC", "crypto", -1.2),
    ]
    out = format_movers_line(movers)
    assert "VIC +15.0%" in out
    assert "MSB +2.0%" in out
    assert "BTC −1.2%" in out  # real minus sign, not hyphen
    assert " · " in out


def test_format_movers_line_truncates_to_limit():
    movers = [_mover(f"S{i}", "stock", float(i + 1)) for i in range(10)]
    out = format_movers_line(movers, limit=3)
    assert out.count(" · ") == 2  # exactly 3 items
    assert "S0" in out and "S2" in out and "S3" not in out


def test_format_movers_line_empty():
    assert format_movers_line([]) == ""


def test_gold_gets_prefix_when_name_does_not_already_include_it():
    # Asset name is just "SJC" — formatter should prefix "Vàng".
    out = format_movers_line([_mover("SJC", "gold", 3.0)])
    assert "Vàng SJC +3.0%" in out
    # Asset name already says "Vàng SJC" — no duplicate prefix.
    out2 = format_movers_line([_mover("Vàng SJC", "gold", 3.0)])
    assert out2 == "Vàng SJC +3.0%"


def test_format_movers_block_with_positive_total():
    movers = [_mover("VIC", "stock", 15.0)]
    block = format_movers_block(total_pct=4.0, movers=movers)
    assert block.startswith("📈 +4.0% so với hôm qua")
    assert "VIC +15.0%" in block


def test_format_movers_block_with_amount_includes_both():
    """When caller passes total_amount + formatter, headline shows both."""
    from decimal import Decimal

    block = format_movers_block(
        total_pct=3.0,
        movers=[_mover("VIC", "stock", 15.0)],
        total_amount=Decimal("217_000_000_000"),
        amount_formatter=lambda v: f"{v / Decimal('1000000000'):.0f} tỷ",
    )
    assert "+217 tỷ" in block
    assert "+3.0%" in block
    assert "so với hôm qua" in block


def test_format_movers_block_with_negative_amount_uses_real_minus():
    from decimal import Decimal

    block = format_movers_block(
        total_pct=-2.5,
        movers=[_mover("BTC", "crypto", -10.0)],
        total_amount=Decimal("-50_000_000"),
        amount_formatter=lambda v: f"{v / Decimal('1000000'):.0f}tr",
    )
    assert "−50tr" in block  # real minus sign
    assert "−2.5%" in block


def test_format_movers_block_with_negative_total():
    block = format_movers_block(total_pct=-2.5, movers=[_mover("BTC", "crypto", -10.0)])
    assert block.startswith("📉 −2.5% so với hôm qua")
    assert "BTC −10.0%" in block


def test_format_movers_block_flat_total():
    block = format_movers_block(total_pct=0.0, movers=[])
    assert "Đi ngang" in block


def test_format_movers_block_skips_headline_when_total_pct_none():
    block = format_movers_block(total_pct=None, movers=[_mover("VIC", "stock", 5.0)])
    assert "so với hôm qua" not in block
    assert "VIC +5.0%" in block
