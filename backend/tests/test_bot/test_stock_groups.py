"""Unit tests for stock_groups helpers — fallback price + dispatcher ordering."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.bot.formatters.stock_groups import fallback_portfolio_price


def _asset(*, extra: dict | None, current_value=0) -> SimpleNamespace:
    return SimpleNamespace(extra=extra, current_value=current_value)


class TestFallbackPortfolioPrice:
    def test_prefers_avg_price(self):
        asset = _asset(extra={"avg_price": 45000, "quantity": 100}, current_value=4_800_000)
        assert fallback_portfolio_price(asset) == Decimal("45000")

    def test_avg_price_string(self):
        asset = _asset(extra={"avg_price": "12500.50"})
        assert fallback_portfolio_price(asset) == Decimal("12500.50")

    def test_falls_back_to_current_value_over_quantity(self):
        asset = _asset(extra={"quantity": 100}, current_value=Decimal("5000000"))
        assert fallback_portfolio_price(asset) == Decimal("50000")

    def test_zero_quantity_returns_none(self):
        asset = _asset(extra={"quantity": 0}, current_value=Decimal("1000"))
        assert fallback_portfolio_price(asset) is None

    def test_missing_extra_returns_none(self):
        asset = _asset(extra=None, current_value=Decimal("1000"))
        assert fallback_portfolio_price(asset) is None

    def test_empty_extra_returns_none(self):
        asset = _asset(extra={}, current_value=Decimal("1000"))
        assert fallback_portfolio_price(asset) is None

    def test_invalid_avg_price_falls_through_to_quantity(self):
        asset = _asset(
            extra={"avg_price": "not-a-number", "quantity": 10},
            current_value=Decimal("100000"),
        )
        assert fallback_portfolio_price(asset) == Decimal("10000")

    def test_invalid_quantity_returns_none(self):
        asset = _asset(extra={"quantity": "abc"}, current_value=Decimal("1000"))
        assert fallback_portfolio_price(asset) is None

    def test_negative_avg_price_falls_through(self):
        asset = _asset(extra={"avg_price": -100, "quantity": 10}, current_value=Decimal("1000"))
        # negative avg_price is rejected (>0 guard), falls back to current_value/qty
        assert fallback_portfolio_price(asset) == Decimal("100")

    def test_zero_current_value_with_quantity_returns_none(self):
        asset = _asset(extra={"quantity": 10}, current_value=0)
        assert fallback_portfolio_price(asset) is None


class TestStockDispatcherOrdering:
    """Provider order is operator-flippable via stock_provider_primary."""

    def _build(self, monkeypatch, primary_setting: str | None):
        from backend.market_data.providers import stock_dispatcher
        from backend.market_data.providers.stock_ssi import SSIStockProvider
        from backend.market_data.providers.stock_vndirect import VNDIRECTStockProvider

        fake_settings = SimpleNamespace(stock_provider_primary=primary_setting)
        monkeypatch.setattr(stock_dispatcher, "get_settings", lambda: fake_settings)

        dispatcher = stock_dispatcher.build_stock_dispatcher(redis_client=None, timeout=1.0)
        return dispatcher, SSIStockProvider, VNDIRECTStockProvider

    def test_default_is_vndirect_first(self, monkeypatch):
        dispatcher, SSI, VND = self._build(monkeypatch, None)
        assert isinstance(dispatcher.vn_dispatcher.primary, VND)
        assert isinstance(dispatcher.vn_dispatcher.secondary, SSI)

    def test_explicit_vndirect_first(self, monkeypatch):
        dispatcher, SSI, VND = self._build(monkeypatch, "vndirect")
        assert isinstance(dispatcher.vn_dispatcher.primary, VND)
        assert isinstance(dispatcher.vn_dispatcher.secondary, SSI)

    def test_ssi_setting_flips_order(self, monkeypatch):
        dispatcher, SSI, VND = self._build(monkeypatch, "ssi")
        assert isinstance(dispatcher.vn_dispatcher.primary, SSI)
        assert isinstance(dispatcher.vn_dispatcher.secondary, VND)

    def test_setting_is_case_insensitive(self, monkeypatch):
        dispatcher, SSI, VND = self._build(monkeypatch, "SSI")
        assert isinstance(dispatcher.vn_dispatcher.primary, SSI)

    def test_unknown_value_defaults_to_vndirect(self, monkeypatch):
        dispatcher, SSI, VND = self._build(monkeypatch, "bogus")
        assert isinstance(dispatcher.vn_dispatcher.primary, VND)
