from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.market_data.normalizer import PriceQuote


def test_price_quote_json_round_trip_preserves_decimal_and_metadata():
    quote = PriceQuote(
        symbol="vnm",
        price=Decimal("86400.50"),
        currency="vnd",
        asset_type="stock",
        fetched_at=datetime(2026, 5, 8, 9, 30, tzinfo=timezone.utc),
        source="ssi",
        metadata={"volume": 12345, "change_pct": "1.25"},
    )

    restored = PriceQuote.from_json(quote.to_json())

    assert restored == quote
    assert isinstance(restored.price, Decimal)
    assert restored.symbol == "VNM"
    assert restored.currency == "VND"


def test_price_quote_marks_naive_datetime_as_utc_and_can_mark_stale():
    quote = PriceQuote(
        symbol="btc",
        price=Decimal("2500000000"),
        currency="vnd",
        asset_type="crypto",
        fetched_at=datetime(2026, 5, 8, 9, 30),
        source="coingecko",
    )

    stale = quote.mark_stale()

    assert quote.fetched_at.tzinfo is timezone.utc
    assert stale.is_stale is True
    assert quote.is_stale is False
