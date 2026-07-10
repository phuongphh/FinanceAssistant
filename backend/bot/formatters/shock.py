"""Render the shock simulation + liquidation answer in Bé Tiền's voice (E1, #1.4).

Pure formatting: takes a :class:`ShockResult` from ``shock_simulation_service``
and a :class:`LiquidationPlan` from ``liquidation_advisor`` and turns them into
user-facing Vietnamese. Every string lives in ``content/decision_copy.yaml``
(never hardcoded); asset-class labels are reused from ``content/twin_copy.yaml``
so we don't fork a second Vietnamese name for the same class.

Two deliberate product rules baked in here:
    * **Weather metaphor, no numbers.** We map a ``ShockSeverity`` to a weather
      line and never read out p10/p50/p90 — a user feels "cơn mưa to" far better
      than "-18%". The percentile deltas stay inside the engine.
    * **legal-guardrail.** The redraw list only ever names classes the user
      already owns (via ``LiquidationPlan.options``). There is no code path that
      prints a fund, ticker, or external product.

Layer note: this is a formatter — no I/O, no DB, no env. The
``SHOCK_SIMULATION_ENABLED`` flag is decided at the handler edge before we are
called.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from backend.bot.formatters.money import format_money_short
from backend.services.decision.liquidation_advisor import LiquidationPlan
from backend.services.decision.shock_simulation_service import (
    ShockResult,
    ShockSeverity,
)

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "decision_copy.yaml"
_TWIN_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_copy.yaml"


@lru_cache(maxsize=1)
def _shock_copy() -> dict:
    with _COPY_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data.get("shock") or {})


@lru_cache(maxsize=1)
def _asset_labels() -> dict:
    with _TWIN_COPY_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data.get("asset_labels") or {})


def _asset_label(asset_class: str) -> str:
    """Vietnamese label for a twin asset class, falling back to the raw key."""
    return str(_asset_labels().get(asset_class, asset_class))


def _format_years(horizon_years: int) -> str:
    return f"{int(horizon_years)} năm"


def render_clarify_amount() -> str:
    """One warm clarifying question when the shock amount is missing."""
    return _shock_copy().get(
        "clarify_amount", "Mình đang tính phải chi khoảng bao nhiêu vậy?"
    )


def render_empty_portfolio() -> str:
    """Copy for when there's no portfolio to simulate a shock against."""
    return _shock_copy().get(
        "empty_portfolio",
        "Mình chưa nắm được tài sản của mình nên chưa mô phỏng được cú này.",
    )


def render_confirm_large(shock_amount: Decimal) -> str:
    """Copy for the >50%-net-worth confirm gate."""
    return (
        _shock_copy()
        .get("confirm_large", "Khoản {amount} này khá lớn — mình vẫn muốn xem thử chứ?")
        .format(amount=format_money_short(shock_amount))
    )


def render_shock(result: ShockResult, plan: LiquidationPlan) -> str:
    """Render the full shock answer: weather severity + recovery + redraw plan."""
    copy = _shock_copy()
    parts: list[str] = []

    intro = copy.get("intro", "")
    if intro:
        parts.append(intro.format(amount=format_money_short(result.shock_amount)))

    weather = copy.get("weather") or {}
    parts.append(
        weather.get(
            result.severity.value, weather.get(ShockSeverity.MODERATE.value, "")
        )
    )

    years = _format_years(result.horizon_years)
    recovery_key = "recovers" if result.recovers else "no_recovers"
    recovery = copy.get(recovery_key, "")
    if recovery:
        parts.append(recovery.format(years=years))

    parts.append(_render_redraw(copy, plan))

    return "\n\n".join(p for p in parts if p)


def _render_redraw(copy: dict, plan: LiquidationPlan) -> str:
    """The "rút từ đâu ít hại nhất" block — only names classes the user owns."""
    if not plan.has_assets:
        return ""

    lines: list[str] = []
    intro = copy.get("redraw_intro", "")
    if intro:
        lines.append(intro)

    # legal-guardrail: every bullet is one of the user's own classes.
    for opt in plan.options:
        lines.append(
            f"• {_asset_label(opt.asset_class)}: rút ~{format_money_short(opt.take)}"
        )

    if not plan.fully_covered:
        insufficient = copy.get("insufficient", "")
        if insufficient:
            lines.append(
                insufficient.format(shortfall=format_money_short(plan.shortfall))
            )

    return "\n".join(lines)


__all__ = [
    "render_clarify_amount",
    "render_confirm_large",
    "render_empty_portfolio",
    "render_shock",
]
