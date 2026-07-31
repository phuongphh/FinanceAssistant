"""Render the plan-to-goal feasibility answer in Bé Tiền's voice (Phase 4.5, E2).

Pure formatting: takes a :class:`PlanFeasibility` from
``plan_feasibility_service`` plus the original ``target`` / ``horizon_years``
the user asked about, and turns them into user-facing Vietnamese. Every string
lives in ``content/decision_copy.yaml`` (never hardcoded) — this module only
picks the right tone block for the band and threads the money numbers in.

Three tones, matching the copy:
    khả thi   (EASY / FEASIBLE)        → encouraging, "trong tầm tay".
    cần cố    (STRETCH / AMBITIOUS)    → honest nudge; AMBITIOUS also gets the
                                          "mức với tới được" pivot.
    bất khả thi (NEEDS_REVISION)       → gentle "hơi quá sức" + the honest
                                          reachable-target pivot so we never
                                          end on a flat "no".

Layer note: this is a formatter — no I/O, no DB, no env. The
``PLAN_FEASIBILITY_QA_ENABLED`` flag is decided at the handler edge before we
are called.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from backend.bot.formatters.money import format_money_short
from backend.bot.formatters.tone import render_tone_variant
from backend.schemas.goal import FeasibilityBand
from backend.services.decision.plan_feasibility_service import PlanFeasibility

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "decision_copy.yaml"

# Bands that read as "cần cố" rather than "khả thi" or "bất khả thi".
_STRETCH_BANDS = frozenset({FeasibilityBand.STRETCH, FeasibilityBand.AMBITIOUS})


@lru_cache(maxsize=1)
def _feasibility_copy() -> dict:
    with _COPY_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return dict(data.get("feasibility") or {})


def _format_years(horizon_years: Decimal) -> str:
    """ "5 năm" / "5.5 năm" — drop the trailing ``.0`` for whole years."""
    years = Decimal(horizon_years)
    if years == years.to_integral_value():
        return f"{int(years)} năm"
    return f"{years.normalize()} năm"


def render_feasibility(
    result: PlanFeasibility,
    *,
    target: Decimal,
    horizon_years: Decimal,
    tone: str | None = None,
    salutation: str = "bạn",
) -> str:
    """Render the feasibility verdict as a short, warm multi-line reply.

    ``tone`` threads the tone dial (E4 #4.3). ``None`` (dial dark) keeps the
    legacy ``decision_copy.yaml`` wording untouched; a live ``"gentle"`` /
    ``"strict"`` swaps only the emotionally-loaded NEEDS_REVISION verdict for
    its tone variant — the reachable-target pivot still follows in either tone,
    so we never end on a flat "no".
    """
    copy = _feasibility_copy()
    years = _format_years(horizon_years)
    actual = format_money_short(result.actual_monthly_savings)

    if result.already_reached:
        return copy.get("already_reached", "Mục tiêu này coi như trong túi 🎉")

    intro = copy.get("intro", "").format(target=format_money_short(target), years=years)

    if result.band == FeasibilityBand.UNKNOWN:
        return _join(intro, copy.get("unknown", ""))

    if result.band in (FeasibilityBand.EASY, FeasibilityBand.FEASIBLE):
        return _join(intro, copy.get("feasible", "").format(actual=actual))

    if result.band in _STRETCH_BANDS:
        required = format_money_short(result.required_monthly_savings or Decimal(0))
        body = copy.get("stretch", "").format(required=required, actual=actual)
        # AMBITIOUS is close but still a reach — offer the honest alternative
        # so the user has a concrete fallback mốc, not just "cố lên".
        pivot = ""
        if result.band == FeasibilityBand.AMBITIOUS:
            pivot = _pivot(copy, result, years)
        return _join(intro, body, pivot)

    # NEEDS_REVISION — never end on a flat "no"; pivot to the reachable target.
    body = render_tone_variant(
        "decision.feasibility_needs_revision",
        tone,
        salutation=salutation,
        actual=actual,
    ) or copy.get("needs_revision", "").format(actual=actual)
    return _join(intro, body, _pivot(copy, result, years))


def render_clarify(missing: str, *, target: Decimal | None = None) -> str:
    """One warm clarifying question when an essential param is missing.

    ``missing`` is ``"target"`` or ``"horizon"``. The horizon prompt echoes the
    already-known target so the user sees we were listening.
    """
    copy = _feasibility_copy()
    if missing == "horizon":
        known = format_money_short(target) if target is not None else ""
        return copy.get("clarify_horizon", "Mình muốn đạt trong bao lâu vậy?").format(
            target=known
        )
    return copy.get("clarify_target", "Mình đang nhắm tới con số bao nhiêu vậy?")


def _pivot(copy: dict, result: PlanFeasibility, years: str) -> str:
    """The "mức với tới được" line — empty when there's no honest number to
    offer (e.g. no saving rate, so ``reachable_target`` collapses to the start).
    """
    if result.reachable_target is None or result.actual_monthly_savings <= 0:
        return ""
    return copy.get("reachable_pivot", "").format(
        reachable=format_money_short(result.reachable_target), years=years
    )


def _join(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


__all__ = ["render_clarify", "render_feasibility"]
