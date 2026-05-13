"""Tests for ``backend.agent.tools.forecast_cashflow``.

We assert:
- Tool registered in default registry.
- Description contains ≥5 example queries (LLM accuracy lever).
- Input schema validates ``months_ahead`` 1-12 bound.
- ``include_runway=False`` skips the runway service call.
- ``include_runway=True`` populates ``runway`` with band/warning.
- Critical spec query "Tháng 7 dự kiến tiết kiệm bao nhiêu?" returns
  a forecast with confidence.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from backend.agent.tools import build_default_registry
from backend.agent.tools.forecast_cashflow import ForecastCashflowTool
from backend.agent.tools.schemas import (
    ForecastCashflowInput,
    ForecastCashflowOutput,
)
from backend.models.user import User
from backend.schemas.cashflow import MonthlyForecast, RunwayResult


def _user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 1
    return u


def _forecast(month: date, savings: Decimal, confidence: float = 0.85) -> MonthlyForecast:
    return MonthlyForecast(
        month=month,
        expected_income=Decimal("30000000"),
        expected_expense=Decimal("30000000") - savings,
        expected_savings=savings,
        confidence=confidence,
        breakdown={
            "scheduled_income": Decimal("30000000"),
            "recurring_expense": Decimal("15000000"),
            "ambient_expense": Decimal("15000000") - savings,
        },
        notes=[],
    )


class TestRegistration:
    def test_in_default_registry(self):
        registry = build_default_registry()
        assert "forecast_cashflow" in registry.names()
        assert isinstance(registry.get("forecast_cashflow"), ForecastCashflowTool)

    def test_description_has_5_plus_examples(self):
        """Tool descriptions live or die on example count (Phase 3.7
        / 3.8 convention). Spec § P3.8-S12 requires ≥3 examples; we
        ship more for runway + horizon variants."""
        desc = ForecastCashflowTool().description
        # Each example line starts with "- '"
        assert desc.count("- '") >= 5


class TestInputSchema:
    def test_default_months_ahead_3(self):
        inp = ForecastCashflowInput()
        assert inp.months_ahead == 3
        assert inp.include_runway is False

    def test_months_ahead_lower_bound(self):
        with pytest.raises(ValueError):
            ForecastCashflowInput(months_ahead=0)

    def test_months_ahead_upper_bound(self):
        with pytest.raises(ValueError):
            ForecastCashflowInput(months_ahead=13)


@pytest.mark.asyncio
class TestExecute:
    async def test_basic_no_runway(self):
        user = _user()
        forecasts = [
            _forecast(date(2026, 5, 1), Decimal("5000000")),
            _forecast(date(2026, 6, 1), Decimal("4000000"), 0.70),
            _forecast(date(2026, 7, 1), Decimal("3000000"), 0.55),
        ]
        with patch(
            "backend.agent.tools.forecast_cashflow.cashflow_forecaster.forecast",
            new=AsyncMock(return_value=forecasts),
        ), patch(
            "backend.agent.tools.forecast_cashflow.cashflow_forecaster.compute_runway",
            new=AsyncMock(),
        ) as runway_mock:
            tool = ForecastCashflowTool()
            result = await tool.execute(
                ForecastCashflowInput(months_ahead=3),
                user, db=None,
            )
        assert isinstance(result, ForecastCashflowOutput)
        assert len(result.forecasts) == 3
        assert result.forecasts[0].month == date(2026, 5, 1)
        assert result.runway is None
        # include_runway=False → never call compute_runway.
        runway_mock.assert_not_awaited()

    async def test_include_runway_true_populates_field(self):
        user = _user()
        runway = RunwayResult(
            months=2.0,
            liquid_assets=Decimal("20000000"),
            monthly_burn=Decimal("10000000"),
            warning="🚨 Runway dưới 3 tháng — nên build emergency fund.",
            band="critical",
        )
        with patch(
            "backend.agent.tools.forecast_cashflow.cashflow_forecaster.forecast",
            new=AsyncMock(return_value=[]),
        ), patch(
            "backend.agent.tools.forecast_cashflow.cashflow_forecaster.compute_runway",
            new=AsyncMock(return_value=runway),
        ) as runway_mock:
            tool = ForecastCashflowTool()
            result = await tool.execute(
                ForecastCashflowInput(months_ahead=1, include_runway=True),
                user, db=None,
            )
        runway_mock.assert_awaited_once()
        assert result.runway is not None
        assert result.runway.band == "critical"
        assert result.runway.months == pytest.approx(2.0)
        assert "🚨" in result.runway.warning

    async def test_critical_spec_query_july_savings(self):
        """Spec § P3.8-S12 critical test query: 'Tháng 7 dự kiến tôi
        tiết kiệm bao nhiêu?' → specific number with confidence."""
        user = _user()
        # Forecasting from May 1 with months_ahead=2 → June + July.
        forecasts = [
            _forecast(date(2026, 6, 1), Decimal("5000000"), 0.85),
            _forecast(date(2026, 7, 1), Decimal("4500000"), 0.70),
        ]
        with patch(
            "backend.agent.tools.forecast_cashflow.cashflow_forecaster.forecast",
            new=AsyncMock(return_value=forecasts),
        ):
            tool = ForecastCashflowTool()
            result = await tool.execute(
                ForecastCashflowInput(months_ahead=2),
                user, db=None,
            )
        july = next(
            (f for f in result.forecasts if f.month == date(2026, 7, 1)),
            None,
        )
        assert july is not None
        assert july.expected_savings == Decimal("4500000")
        assert july.confidence == pytest.approx(0.70)


class TestOutputSchema:
    def test_breakdown_passes_through(self):
        f = _forecast(date(2026, 5, 1), Decimal("5000000"))
        assert "scheduled_income" in f.breakdown
        assert "recurring_expense" in f.breakdown
        assert "ambient_expense" in f.breakdown
