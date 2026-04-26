"""Morning briefing formatter — ladder-aware, personalized.

Produces the text body of the morning briefing for one user. Layout
adapts to the user's wealth level (Starter / Young Prof / Mass
Affluent / HNW). Templates live in
``content/briefing_templates.yaml`` so content edits don't require
a deploy.

Layer contract: pure formatter — reads the DB through the existing
calculator, never commits, never sends. The job in
``backend/jobs/morning_briefing_job.py`` owns transport.

Reference: docs/current/phase-3a-detailed.md § 2.2
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.models.expense import Expense
from backend.models.user import User
from backend.wealth.asset_types import get_icon, get_label
from backend.wealth.ladder import WealthLevel, detect_level, next_milestone
from backend.wealth.services import net_worth_calculator
from backend.wealth.services.net_worth_calculator import (
    NetWorthBreakdown,
    NetWorthChange,
)

logger = logging.getLogger(__name__)

_TEMPLATES_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "briefing_templates.yaml"
)

# Saving baseline used for ETA estimates when the user has no income
# or expense history. ~3tr/mo is the median Starter saver in our
# Phase 2 data — replace with real data in Phase 4.
_DEFAULT_MONTHLY_SAVING = Decimal("3_000_000")

# Mobile-screen target. The job will log a warning if a generated
# briefing exceeds this — we don't truncate (would mangle UTF-8 +
# breakdown lines). Hard ceiling is Telegram's 4096-char message limit.
MAX_BRIEFING_CHARS = 800


@dataclass
class BriefingResult:
    """Both the text and the level it was rendered for.

    Job uses ``level`` as an analytics property so we can break open
    rate down by tier without re-querying the user row.
    """
    text: str
    level: WealthLevel
    is_empty_state: bool = False
    char_count: int = 0


@lru_cache(maxsize=1)
def _load_templates() -> dict:
    """Read YAML once per process; tests can call ``cache_clear()``."""
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _change_emoji(change: Decimal) -> str:
    if change > 0:
        return "📈"
    if change < 0:
        return "📉"
    return "➖"


def _signed_money_short(amount: Decimal) -> str:
    """Format ``+1.5tr`` / ``-200k`` — the leading sign is required for
    the change line so users instantly read direction without scanning
    the emoji."""
    short = format_money_short(amount)
    if amount > 0 and not short.startswith("+"):
        return f"+{short}"
    return short


def _signed_pct(value: float) -> str:
    return f"{value:+.1f}"


class BriefingFormatter:
    """Stateless renderer — instantiate once, call ``generate_for_user``
    repeatedly. Holds no per-user state.
    """

    def __init__(self) -> None:
        self._templates = _load_templates()

    async def generate_for_user(
        self, db: AsyncSession, user: User
    ) -> BriefingResult:
        """Build the personalized briefing for ``user``.

        Edge cases handled:
        - 0 assets → empty-state message (no net worth math)
        - net worth = 0 (sold everything) → falls through to empty-state
        - change pct = 0 → "no change" template
        - missing display_name → falls back to "bạn"
        """
        breakdown = await net_worth_calculator.calculate(db, user.id)

        # Empty state: no assets at all OR net worth is zero. Both lead
        # to the same UX (no graph, no breakdown) so we collapse the
        # branches.
        if breakdown.asset_count == 0 or breakdown.total <= 0:
            return self._render_empty_state(user)

        change = await net_worth_calculator.calculate_change(
            db, user.id, period=net_worth_calculator.PERIOD_DAY
        )
        level = detect_level(breakdown.total)

        greeting = self._format_greeting(level, user)
        net_worth_section = self._format_net_worth(level, breakdown, change)

        if level == WealthLevel.STARTER:
            milestone = self._format_milestone_progress(breakdown)
            tip = random.choice(
                self._templates["starter"]["educational_tips"]
            )
            body = "\n\n".join(filter(None, [
                net_worth_section, milestone, tip,
            ]))

        elif level == WealthLevel.YOUNG_PROFESSIONAL:
            action = self._maybe_action_prompt(breakdown)
            body = "\n\n".join(filter(None, [net_worth_section, action]))

        elif level == WealthLevel.MASS_AFFLUENT:
            cashflow = await self._format_cashflow(db, user)
            market = self._templates["mass_affluent"]["market_intelligence"][
                "placeholder"
            ]
            body = "\n\n".join(filter(None, [
                net_worth_section, cashflow, market,
            ]))

        else:  # HNW
            performance = self._templates["hnw"]["detailed_breakdown"][
                "placeholder"
            ]
            body = "\n\n".join([net_worth_section, performance])

        storytelling = self._format_storytelling_prompt(user)

        text = "\n\n".join([greeting, body, storytelling])

        if len(text) > MAX_BRIEFING_CHARS:
            logger.warning(
                "briefing exceeds %d chars (got %d) for user=%s level=%s",
                MAX_BRIEFING_CHARS, len(text), user.id, level.value,
            )

        return BriefingResult(
            text=text, level=level, char_count=len(text),
        )

    # ── Section formatters ────────────────────────────────────────

    def _format_greeting(self, level: WealthLevel, user: User) -> str:
        greetings = self._templates[level.value]["greeting"]
        return random.choice(greetings).format(name=user.get_greeting_name())

    def _format_net_worth(
        self,
        level: WealthLevel,
        breakdown: NetWorthBreakdown,
        change: NetWorthChange,
    ) -> str:
        cfg = self._templates[level.value]["net_worth_display"]
        breakdown_lines = self._format_breakdown(breakdown.by_type)

        # When change is exactly 0 (no historical snapshots, or same
        # value), use the no_change variant — avoids "+0đ (0.0%)"
        # which reads as broken.
        if change.change_absolute == 0:
            return cfg["no_change"].rstrip().format(
                net_worth=format_money_full(breakdown.total),
                net_worth_short=format_money_short(breakdown.total),
                period=change.period_label,
                breakdown_lines=breakdown_lines,
            )

        return cfg["template"].rstrip().format(
            net_worth=format_money_full(breakdown.total),
            net_worth_short=format_money_short(breakdown.total),
            change=_signed_money_short(change.change_absolute),
            change_emoji=_change_emoji(change.change_absolute),
            pct=_signed_pct(change.change_percentage),
            period=change.period_label,
            breakdown_lines=breakdown_lines,
        )

    def _format_breakdown(self, by_type: dict[str, Decimal]) -> str:
        """Multi-line breakdown sorted by value descending.

        Format: ``💵 Tiền mặt: 50tr (45%)``. Percentages round to
        whole numbers — three-decimal precision on a phone screen
        is just noise.
        """
        if not by_type:
            return ""
        total = sum(by_type.values(), Decimal(0))
        if total <= 0:
            return ""

        lines = []
        for asset_type, value in sorted(
            by_type.items(), key=lambda kv: kv[1], reverse=True
        ):
            icon = get_icon(asset_type)
            label = get_label(asset_type)
            pct = float(value / total * 100)
            lines.append(
                f"{icon} {label}: {format_money_short(value)} ({pct:.0f}%)"
            )
        return "\n".join(lines)

    def _format_milestone_progress(
        self, breakdown: NetWorthBreakdown
    ) -> str:
        """Starter-only — show next ladder rung + rough ETA.

        ETA uses a 3tr/mo placeholder until Phase 4 adds real saving
        rate. Capped at 99 months on the display side so the line
        doesn't blow out for users with 0 progress.
        """
        target, _ = next_milestone(breakdown.total)
        remaining = target - breakdown.total

        months_to_go = remaining / _DEFAULT_MONTHLY_SAVING
        months_capped = min(int(months_to_go), 99)
        eta = date.today() + timedelta(days=months_capped * 30)

        template = self._templates["starter"]["progress_context"]["template"]
        return template.rstrip().format(
            next_milestone=format_money_full(target),
            remaining=format_money_short(remaining),
            eta_date=eta.strftime("%m/%Y"),
        )

    def _maybe_action_prompt(
        self, breakdown: NetWorthBreakdown
    ) -> str | None:
        """Young Prof — surface a generic action prompt.

        Phase 3A: pick one at random. Phase 3B will gate them on real
        portfolio signals (cash > 50%, stock concentration > 50%, etc).
        """
        prompts = self._templates["young_prof"]["action_prompts"]
        if not prompts:
            return None
        return random.choice(prompts)

    async def _format_cashflow(
        self, db: AsyncSession, user: User
    ) -> str:
        """Mass Affluent — show monthly income / expense / saving rate.

        Income comes from ``users.monthly_income`` (declared during
        onboarding). Expense is the SUM of this month's expenses.
        Saving rate stays ``--`` if income is missing rather than
        showing 100% (which would be a lie).
        """
        today = date.today()
        month_key = today.strftime("%Y-%m")

        stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.user_id == user.id,
            Expense.month_key == month_key,
            Expense.deleted_at.is_(None),
        )
        expense_total = Decimal(
            (await db.execute(stmt)).scalar() or 0
        )

        income = (
            Decimal(user.monthly_income)
            if user.monthly_income
            else None
        )

        if income and income > 0:
            saving_amount = income - expense_total
            saving_rate_pct = float(saving_amount / income * 100)
            saving_rate_str = f"{saving_rate_pct:.0f}"
            saving_emoji = (
                "🌱" if saving_rate_pct >= 20 else
                "⚖️" if saving_rate_pct >= 0 else "🫣"
            )
            income_str = format_money_short(income)
        else:
            saving_rate_str = "--"
            saving_emoji = ""
            income_str = "—"

        template = self._templates["mass_affluent"]["cashflow"]["template"]
        return template.rstrip().format(
            income_month=income_str,
            expense_month=format_money_short(expense_total),
            saving_rate=saving_rate_str,
            saving_emoji=saving_emoji,
        )

    def _format_storytelling_prompt(self, user: User) -> str:
        threshold = format_money_short(user.expense_threshold_micro)
        prompts = self._templates["storytelling_prompt"]
        return random.choice(prompts).rstrip().format(threshold=threshold)

    def _render_empty_state(self, user: User) -> BriefingResult:
        cfg = self._templates["empty_state"]
        greeting = random.choice(cfg["greeting"]).format(
            name=user.get_greeting_name()
        )
        body = cfg["body"].rstrip()
        text = f"{greeting}\n\n{body}"
        return BriefingResult(
            text=text,
            level=WealthLevel.STARTER,
            is_empty_state=True,
            char_count=len(text),
        )
