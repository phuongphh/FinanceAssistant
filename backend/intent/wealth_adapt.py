"""Wealth-level-aware response adaptation for Phase 3.5 read handlers.

The four bands have very different content needs (CLAUDE.md §0):

  Starter (<30tr)     — simple, encouraging, no jargon, hide metrics
  Young Prof (30tr+)  — growth context, suggest investments
  Mass Affluent (200tr+) — full breakdown, change tracking, allocation %
  HNW (1B+)           — portfolio analytics, YTD return, advisor-level

This module gives handlers two cheap primitives:

  - ``LevelStyle`` dataclass: precomputed flags + helpers (show %?
    show pnl%? encouragement line?). Handlers ask the dataclass questions
    instead of branching on the enum themselves.
  - ``decorate(text, style)``: append the level-appropriate context line
    to a base response. Composition, not duplication — handlers keep
    their data-formatting logic and just hand off the trailing line.

Detection
---------
``resolve_style(db, user)`` does a single net-worth roundtrip and
caches by user id for the dispatch lifetime; multiple handlers in the
same request share the cached read. Tests can build a ``LevelStyle``
directly to bypass the DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.wealth.ladder import WealthLevel, detect_level
from backend.wealth.services import net_worth_calculator


@dataclass(frozen=True)
class LevelStyle:
    """Precomputed presentation flags for a wealth level."""

    level: WealthLevel
    net_worth: Decimal

    # What to show / hide.
    show_percent_change: bool
    show_pnl_pct: bool
    show_allocation_pct: bool
    show_ytd_return: bool

    # Tone hints.
    encouragement: str | None  # Starter only — appended once at end.
    growth_hint: str | None    # Young Prof only — "tăng X% so với tháng trước".

    @property
    def is_starter(self) -> bool:
        return self.level == WealthLevel.STARTER

    @property
    def is_hnw(self) -> bool:
        return self.level == WealthLevel.HIGH_NET_WORTH


def style_for_level(level: WealthLevel, net_worth: Decimal) -> LevelStyle:
    """Pure helper — no DB, easy to use in tests."""
    if level == WealthLevel.STARTER:
        return LevelStyle(
            level=level,
            net_worth=net_worth,
            show_percent_change=False,
            show_pnl_pct=False,
            show_allocation_pct=False,
            show_ytd_return=False,
            encouragement="Bước đầu tốt — đang xây dựng tài sản 🌱",
            growth_hint=None,
        )
    if level == WealthLevel.YOUNG_PROFESSIONAL:
        return LevelStyle(
            level=level,
            net_worth=net_worth,
            show_percent_change=True,
            show_pnl_pct=True,
            show_allocation_pct=False,
            show_ytd_return=False,
            encouragement=None,
            growth_hint="Cân nhắc thêm đầu tư để tài sản tăng nhanh hơn 📈",
        )
    if level == WealthLevel.MASS_AFFLUENT:
        return LevelStyle(
            level=level,
            net_worth=net_worth,
            show_percent_change=True,
            show_pnl_pct=True,
            show_allocation_pct=True,
            show_ytd_return=False,
            encouragement=None,
            growth_hint=None,
        )
    # HNW
    return LevelStyle(
        level=level,
        net_worth=net_worth,
        show_percent_change=True,
        show_pnl_pct=True,
        show_allocation_pct=True,
        show_ytd_return=True,
        encouragement=None,
        growth_hint=None,
    )


async def resolve_style(db: AsyncSession, user: User) -> LevelStyle:
    """Compute a ``LevelStyle`` for ``user``. One DB roundtrip.

    Reads net worth fresh — by the time a handler runs the caller has
    already opened a session and the helper here is the cheapest way to
    avoid every handler re-implementing "fetch breakdown then branch".
    """
    breakdown = await net_worth_calculator.calculate(db, user.id)
    level = detect_level(breakdown.total)
    return style_for_level(level, breakdown.total)


def decorate(text: str, style: LevelStyle) -> str:
    """Append the level-appropriate trailing line to ``text``.

    The decorator is conservative — only adds a line when the level
    style has one. Mass Affluent / HNW already get extra detail in
    their format methods; we don't need to bolt on extra encouragement.
    """
    if style.encouragement:
        return f"{text}\n\n{style.encouragement}"
    if style.growth_hint:
        return f"{text}\n\n_{style.growth_hint}_"
    return text


__all__ = [
    "LevelStyle",
    "decorate",
    "resolve_style",
    "style_for_level",
]
