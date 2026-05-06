"""Pydantic schemas for cashflow forecasting (Phase 3.8 Epic 4).

Two payloads:

- ``MonthlyForecast`` — one entry per future month in a forecast.
- ``RunwayResult`` — "if income stops today, how long can the user
  survive on liquid assets?".

Money fields stay as ``Decimal`` so callers (agent formatter, future
chart endpoints) can sum without precision drift.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MonthlyForecast(BaseModel):
    """One month in a cashflow forecast.

    ``confidence`` decays with distance — month-1=0.85, month-2=0.70,
    month-3=0.55, floor 0.30 (per spec § 2.1). The formatter shows
    this so users don't read a 6-month-out figure as a hard number.

    ``breakdown`` carries an explainability trace:
        {
          "scheduled_income": <Decimal>,   # streams firing this month
          "recurring_expense": <Decimal>,  # patterns due this month
          "ambient_expense": <Decimal>,    # baseline non-recurring avg
        }
    The agent tool returns it; the LLM uses it to answer "tại sao
    tháng 6 cao thế?" follow-ups without a second tool call.

    ``notes`` accumulates user-visible warnings (low data, no income
    streams, projected deficit). Empty list when there's nothing to
    flag — keeps the formatter terse for the typical case.
    """

    model_config = ConfigDict(use_enum_values=True)

    month: date = Field(..., description="First day of the forecast month")
    expected_income: Decimal
    expected_expense: Decimal
    expected_savings: Decimal
    confidence: float = Field(..., ge=0.0, le=1.0)
    breakdown: dict[str, Decimal] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class RunwayResult(BaseModel):
    """Output of ``RunwayAnalyzer.compute_runway``.

    ``months`` is the float number of months the user could keep
    paying essential expenses with their liquid assets. ``None``
    means "infinite" — user has assets but no essential expenses
    tracked; we don't return a misleading 0.

    ``warning`` is human-readable Vietnamese text per spec
    thresholds: <3mo runs the 🚨 line, 3-6mo runs ⚠️, >6mo is
    quiet.
    """

    model_config = ConfigDict(use_enum_values=True)

    months: Optional[float]
    liquid_assets: Decimal
    monthly_burn: Decimal
    warning: Optional[str] = None
    # Advisory band: "critical" | "tight" | "comfortable" | "unknown"
    # — a stable token the agent / Mini App can branch on without
    # parsing the localised ``warning`` string.
    band: str = "unknown"


__all__ = ["MonthlyForecast", "RunwayResult"]
