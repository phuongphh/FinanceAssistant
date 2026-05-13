"""``forecast_cashflow`` tool — Phase 3.8 Epic 4 (Story P3.8-S12).

Wraps ``backend.services.cashflow_forecaster`` so the LLM can answer:

- "Tháng tới tôi sẽ tiết kiệm bao nhiêu?" → ``months_ahead=1``
- "Dự đoán cashflow 3 tháng tới" → ``months_ahead=3``
- "Khi nào tôi sẽ âm tài khoản?" → ``include_runway=True``
- "Tôi có thể sống bao lâu nếu mất việc?" → ``include_runway=True``

Output is structured (forecast list + optional runway). The LLM is
expected to format with the emoji conventions noted in
``description``: 📈 income, 📉 expense, 💎 savings. Confidence is
displayed so users don't read a 6-month-out figure as a hard number.
"""
from __future__ import annotations

from typing import Type

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import (
    ForecastCashflowInput,
    ForecastCashflowOutput,
    MonthlyForecastItem,
    RunwayInfo,
)
from backend.models.user import User
from backend.services import cashflow_forecaster


class ForecastCashflowTool(Tool):
    @property
    def name(self) -> str:
        return "forecast_cashflow"

    @property
    def description(self) -> str:
        # Long-form description with example queries — the agent's
        # function-calling accuracy improves directly with example
        # count (we learned this in Phase 3.7).
        return (
            "Forecast the user's cashflow (income, expense, savings) "
            "for upcoming months. Use this for ANY future-tense query "
            "about money — 'next month', 'next quarter', 'sẽ tiết "
            "kiệm', 'dự đoán'. Set ``include_runway=true`` for "
            "survival-time queries.\n"
            "\n"
            "Methodology: income from the user's IncomeStream rows "
            "(scheduled by month), expense = recurring patterns + "
            "ambient baseline (avg of non-recurring last 3 months). "
            "Confidence decays with distance: month 1 ≈ 85%, month 3 "
            "≈ 55%. Show this when answering — long-horizon numbers "
            "are not hard facts.\n"
            "\n"
            "Examples (Vietnamese query → tool call):\n"
            "- 'tháng tới tôi sẽ tiết kiệm bao nhiêu?' → "
            "{months_ahead: 1}\n"
            "- 'dự đoán cashflow 3 tháng tới' → {months_ahead: 3}\n"
            "- 'cashflow 6 tháng tới' → {months_ahead: 6}\n"
            "- 'tháng 7 dự kiến tôi tiết kiệm bao nhiêu?' → "
            "{months_ahead: <gap to july>}\n"
            "- 'bao giờ tôi âm tài khoản?' → "
            "{months_ahead: 1, include_runway: true}\n"
            "- 'mất việc tôi sống được bao lâu?' → "
            "{months_ahead: 1, include_runway: true}\n"
            "\n"
            "When formatting the response, use 📈 income / 📉 expense "
            "/ 💎 savings emojis and surface confidence + any notes "
            "(low data warnings, projected deficit). If runway "
            "warning is present, lead with it."
        )

    @property
    def input_schema(self) -> Type[BaseModel]:
        return ForecastCashflowInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return ForecastCashflowOutput

    async def execute(
        self,
        input_data: ForecastCashflowInput,
        user: User,
        db: AsyncSession,
    ) -> ForecastCashflowOutput:
        forecasts = await cashflow_forecaster.forecast(
            db, user.id, months_ahead=input_data.months_ahead,
        )
        items = [
            MonthlyForecastItem(
                month=f.month,
                expected_income=f.expected_income,
                expected_expense=f.expected_expense,
                expected_savings=f.expected_savings,
                confidence=f.confidence,
                breakdown=dict(f.breakdown),
                notes=list(f.notes),
            )
            for f in forecasts
        ]

        runway: RunwayInfo | None = None
        if input_data.include_runway:
            r = await cashflow_forecaster.compute_runway(db, user.id)
            runway = RunwayInfo(
                months=r.months,
                liquid_assets=r.liquid_assets,
                monthly_burn=r.monthly_burn,
                warning=r.warning,
                band=r.band,
            )

        return ForecastCashflowOutput(forecasts=items, runway=runway)
