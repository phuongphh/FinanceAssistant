"""Daily cost aggregation for the operator KPI digest (Phase 4.1, A.4).

Outputs a structured ``CostReport`` consumed by the KPI digest worker
(Story A.6) — NEVER sends a separate operator message of its own.

Aggregation is single-pass over ``llm_cost_log`` for the day:
  - total VND per provider
  - top 5 users by spend
  - users who crossed the 80% threshold today
  - 7-day moving average for the burst alert
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.cost_budget import LLMCostLog, UserCostBudget

logger = logging.getLogger(__name__)


@dataclass
class TopUser:
    user_id_short: str  # First 8 chars of UUID — operator-facing, not PII
    cost_vnd: Decimal


@dataclass
class CostReport:
    report_date: date
    total_vnd_by_provider: dict[str, Decimal] = field(default_factory=dict)
    total_vnd: Decimal = Decimal("0")
    top_users: list[TopUser] = field(default_factory=list)
    crossed_80_pct_today: int = 0
    seven_day_avg_vnd: Decimal = Decimal("0")
    is_burst: bool = False  # total > 200% of 7-day avg

    def to_telegram_section(self) -> str:
        """Render as a compact section for the KPI digest (< 500 chars).

        VND amounts round to 1k. The bursting flag prefixes the section
        with 🚨 so the operator's eye lands on it.
        """
        prefix = "🚨 " if self.is_burst else ""
        lines = [f"{prefix}<b>💰 Cost ({self.report_date.isoformat()})</b>"]

        # Provider breakdown
        if self.total_vnd_by_provider:
            for prov, vnd in sorted(
                self.total_vnd_by_provider.items(), key=lambda kv: -kv[1]
            ):
                lines.append(f"• {prov}: {_fmt_k(vnd)}")
        lines.append(f"• <b>Tổng:</b> {_fmt_k(self.total_vnd)}")

        # Top spenders
        if self.top_users:
            top_str = ", ".join(
                f"{u.user_id_short}({_fmt_k(u.cost_vnd)})" for u in self.top_users[:5]
            )
            lines.append(f"• Top 5: {top_str}")

        if self.crossed_80_pct_today:
            lines.append(f"• ⚠️ {self.crossed_80_pct_today} user chạm 80% cap hôm nay")
        return "\n".join(lines)


def _fmt_k(vnd: Decimal) -> str:
    """Round to nearest 1k VND for compact display."""
    val = int(Decimal(vnd).quantize(Decimal("1")) // 1000)
    if val == 0 and vnd > 0:
        return "<1k"
    return f"{val}k"


async def daily_summary(db: AsyncSession, *, day: date | None = None) -> CostReport:
    """Aggregate one day of LLM costs into a :class:`CostReport`.

    ``day`` defaults to yesterday (Asia/Ho_Chi_Minh local date when
    the cron runs at 08:00 local). The query uses UTC bounds derived
    from ``day`` so the result is reproducible.
    """
    if day is None:
        day = (datetime.now(timezone.utc) - timedelta(days=1)).date()

    start_dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)

    report = CostReport(report_date=day)

    # Provider totals.
    rows = (
        await db.execute(
            select(LLMCostLog.provider, func.coalesce(func.sum(LLMCostLog.cost_vnd), 0))
            .where(LLMCostLog.created_at >= start_dt, LLMCostLog.created_at < end_dt)
            .group_by(LLMCostLog.provider)
        )
    ).all()
    for provider, total in rows:
        amt = Decimal(total)
        report.total_vnd_by_provider[provider] = amt
        report.total_vnd += amt

    # Top 5 users by cost.
    top_rows = (
        await db.execute(
            select(
                LLMCostLog.user_id,
                func.coalesce(func.sum(LLMCostLog.cost_vnd), 0).label("total"),
            )
            .where(LLMCostLog.created_at >= start_dt, LLMCostLog.created_at < end_dt)
            .group_by(LLMCostLog.user_id)
            .order_by(func.sum(LLMCostLog.cost_vnd).desc())
            .limit(5)
        )
    ).all()
    report.top_users = [
        TopUser(user_id_short=str(uid)[:8], cost_vnd=Decimal(total))
        for uid, total in top_rows
    ]

    # 7-day moving average for the burst comparison.
    avg_window_start = start_dt - timedelta(days=7)
    avg_total = (
        await db.execute(
            select(func.coalesce(func.sum(LLMCostLog.cost_vnd), 0)).where(
                LLMCostLog.created_at >= avg_window_start,
                LLMCostLog.created_at < start_dt,
            )
        )
    ).scalar()
    avg_per_day = Decimal(avg_total) / Decimal(7)
    report.seven_day_avg_vnd = avg_per_day
    report.is_burst = bool(
        avg_per_day > 0 and report.total_vnd > avg_per_day * Decimal("2")
    )

    # Users who crossed 80% today (last_warning_sent_at lands inside
    # the report window).
    crossed_count = (
        await db.execute(
            select(func.count())
            .select_from(UserCostBudget)
            .where(
                UserCostBudget.last_warning_sent_at >= start_dt,
                UserCostBudget.last_warning_sent_at < end_dt,
            )
        )
    ).scalar()
    report.crossed_80_pct_today = int(crossed_count or 0)

    return report
