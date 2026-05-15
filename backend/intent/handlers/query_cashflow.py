"""Handler for ``query_cashflow`` — net cashflow (income − expense) for a period.

Wealth-aware: Starter sees a simple "tiết kiệm được X", Mass Affluent
sees breakdown + savings rate. Income side reads from the IncomeStream
table (Phase 3A) and falls back to ``user.monthly_income`` when no
streams are configured.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full, format_money_short
from backend.config.categories import get_category
from backend.intent.extractors.time_range import TimeRange
from backend.intent.handlers.base import IntentHandler
from backend.intent.handlers.query_expenses import (
    _resolve_time_range,
    _TIME_LABELS_VI,
    _fetch_expenses,
)
from backend.wealth.income_types import (
    get_icon as _income_icon,
    get_label as _income_label,
    is_auto_linked as _income_auto_linked,
)
from backend.intent.intents import IntentResult
from backend.intent.wealth_adapt import LevelStyle, decorate, resolve_style
from backend.models.expense import Expense
from backend.models.user import User
from backend.wealth.models.income_stream import IncomeStream

# Legacy prefixes ever written into ``income_streams.name`` by
# ``rental_service``. The post-fix invariant is ``name == asset.name``; this
# strip is belt-and-braces so old rows render correctly even before the
# data migration has run.
_LEGACY_NAME_PREFIXES: tuple[str, ...] = (
    "Thuê BĐS — ",
    "BĐS cho thuê — ",
)


def _strip_legacy_prefix(name: str) -> str:
    for prefix in _LEGACY_NAME_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :].strip()
    return name


@dataclass(frozen=True)
class CashflowPeriod:
    income: Decimal
    spend: Decimal
    net: Decimal
    expenses: list[Expense]


class QueryCashflowHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        time_range = _resolve_time_range(intent)
        streams = await _fetch_income_streams(db, user)
        current = await _build_period(db, user, time_range, streams=streams)

        style = await resolve_style(db, user)
        focus = intent.parameters.get("focus")
        if focus == "current_month_detail":
            text = self._format_monthly_detail(user, time_range, current, streams)
        else:
            previous_range = _previous_period(time_range)
            previous = await _build_period(db, user, previous_range, streams=streams)
            text = self._format_overview(
                user,
                time_range,
                current=current,
                previous=previous,
                streams=streams,
                style=style,
            )
        return decorate(text, style)

    def _format_overview(
        self,
        user: User,
        time_range: TimeRange,
        *,
        current: CashflowPeriod,
        previous: CashflowPeriod,
        streams: list[IncomeStream],
        style: LevelStyle,
    ) -> str:
        name = user.display_name or "bạn"
        label_vi = _TIME_LABELS_VI.get(time_range.label, time_range.label)
        if current.income <= 0 and current.spend <= 0:
            return (
                f"{name} chưa có dữ liệu thu / chi {label_vi} 🌱\n"
                "Mình cần ít nhất một nguồn thu và vài giao dịch để tính dòng tiền."
            )

        saving_rate = _safe_rate(current.net, current.income)
        arrow = "💚" if current.net >= 0 else "🟥"
        sign = "+" if current.net >= 0 else "−"
        net_word = "dư" if current.net >= 0 else "vượt thu"
        lines = [
            f"💰 Dòng tiền {label_vi}: {net_word} {format_money_short(abs(current.net))}",
            "",
            self._income_card(current, previous, streams, time_range),
            "",
            self._expense_card(current, previous),
            "",
            "💎 *Tỷ lệ tiết kiệm*",
            f"{_format_percent(saving_rate) if saving_rate is not None else '—'}",
            "",
            f"{arrow} *Dư / thiếu*: {sign}{format_money_full(abs(current.net))}",
            "",
            _cashflow_tip(current, saving_rate),
        ]
        return "\n".join(lines)

    def _income_card(
        self,
        current: CashflowPeriod,
        previous: CashflowPeriod,
        streams: list[IncomeStream],
        time_range: TimeRange,
    ) -> str:
        income_delta = _delta_text(current.income, previous.income)
        lines = [
            "💼 *Thu nhập tháng*",
            f"Tổng: *{format_money_full(current.income)}* "
            f"({income_delta} vs tháng trước)",
        ]
        return "\n".join(lines)

    def _expense_card(self, current: CashflowPeriod, previous: CashflowPeriod) -> str:
        spend_delta = _delta_text(current.spend, previous.spend)
        lines = [
            "💸 *Chi tiêu tháng*",
            f"Tổng: *{format_money_full(current.spend)}* "
            f"({spend_delta} vs tháng trước)",
        ]
        return "\n".join(lines)

    def _format_monthly_detail(
        self,
        user: User,
        time_range: TimeRange,
        period: CashflowPeriod,
        streams: list[IncomeStream],
    ) -> str:
        label_vi = _TIME_LABELS_VI.get(time_range.label, "tháng này")
        title = f"📅 *Dòng tiền {label_vi}*"
        if time_range.label == "this_month":
            today_vi = date.today().strftime("%d/%m/%Y")
            title = f"📅 *Dòng tiền {label_vi} tính đến hôm nay {today_vi}*"
        sign = "+" if period.net >= 0 else "−"
        lines = [
            title,
            f"Thu: *{format_money_full(period.income)}*",
            f"Chi: *{format_money_full(period.spend)}*",
            f"Dư / thiếu: *{sign}{format_money_full(abs(period.net))}*",
            "",
            "💼 *Top nguồn thu*",
        ]
        income_sources = _top_income_sources(streams, time_range=time_range, limit=3)
        if income_sources:
            lines.extend(
                f"• {label}: {format_money_short(amount)}"
                for label, amount in income_sources
            )
        else:
            lines.append("Chưa có nguồn thu nào được ghi nhận.")

        lines.extend(["", "💸 *Top nhóm chi*"])
        expense_categories = _top_expense_categories(period.expenses, limit=3)
        if expense_categories:
            lines.extend(
                f"• {label}: {format_money_short(amount)}"
                for label, amount in expense_categories
            )
        else:
            lines.append("Chưa có chi tiêu nào trong tháng này.")

        lines.extend(["", "📈 *Nhịp chi tiêu theo ngày*"])
        lines.extend(_daily_flow_lines(period.expenses))

        lines.extend(["", "🔎 *3 giao dịch lớn nhất*"])
        biggest = sorted(
            period.expenses, key=lambda tx: Decimal(tx.amount or 0), reverse=True
        )[:3]
        if biggest:
            for tx in biggest:
                day = getattr(tx, "expense_date", None)
                day_text = day.strftime("%d/%m") if day else "--/--"
                merchant = (getattr(tx, "merchant", None) or "Giao dịch").strip()
                cat = get_category(getattr(tx, "category", None) or "other")
                lines.append(
                    f"• {day_text} — {cat.emoji} {merchant}: {format_money_short(tx.amount)}"
                )
        else:
            lines.append("Chưa có giao dịch để xếp hạng.")

        return "\n".join(lines)


async def _fetch_income_streams(db: AsyncSession, user: User) -> list[IncomeStream]:
    stmt = select(IncomeStream).where(
        IncomeStream.user_id == user.id,
        IncomeStream.is_active.is_(True),
    )
    return list((await db.execute(stmt)).scalars().all())


async def _build_period(
    db: AsyncSession,
    user: User,
    time_range: TimeRange,
    *,
    streams: list[IncomeStream],
) -> CashflowPeriod:
    income = _income_for_period_from_streams(user, time_range, streams)
    expenses = await _fetch_expenses(
        db, user, start=time_range.start, end=time_range.end
    )
    spend = sum(Decimal(tx.amount or 0) for tx in expenses)
    net = income - spend
    return CashflowPeriod(income=income, spend=spend, net=net, expenses=expenses)


def _income_for_period_from_streams(
    user: User, time_range: TimeRange, streams: list[IncomeStream]
) -> Decimal:
    if streams:
        return sum(
            (
                _income_stream_amount_for_period(stream, time_range)
                for stream in streams
            ),
            Decimal(0),
        ).quantize(Decimal("1"))
    if user.monthly_income:
        return Decimal(user.monthly_income).quantize(Decimal("1"))
    return Decimal(0)


def _income_stream_amount_for_period(
    stream: IncomeStream, time_range: TimeRange
) -> Decimal:
    """Return the amount shown for one stream in a cashflow period.

    Fixed monthly streams (salary, rent, other recurring monthly income)
    represent the user's expected monthly amount, so the monthly cashflow
    view must show that exact figure instead of prorating it by elapsed days.
    Variable/non-monthly schedules keep the previous day-based normalisation.
    """
    monthly = Decimal(getattr(stream, "monthly_equivalent", 0) or 0)
    schedule_type = getattr(stream, "schedule_type", None)
    if not isinstance(schedule_type, str) or not schedule_type:
        schedule_type = "monthly"
    if schedule_type == "monthly":
        return monthly
    days = (time_range.end - time_range.start).days + 1
    return (monthly * Decimal(days) / Decimal(30)).quantize(Decimal("1"))


async def _income_for_period(
    db: AsyncSession, user: User, time_range: TimeRange
) -> Decimal:
    """Compute income for a period from active streams.

    Kept for existing callers/tests; the main handler fetches streams once
    and reuses them for current + previous periods to avoid duplicate DB work.
    """
    streams = await _fetch_income_streams(db, user)
    return _income_for_period_from_streams(user, time_range, streams)


def _previous_period(time_range: TimeRange) -> TimeRange:
    days = (time_range.end - time_range.start).days
    previous_end = time_range.start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days)
    return TimeRange(previous_start, previous_end, "previous_period")


def _top_income_sources(
    streams: Iterable[IncomeStream],
    *,
    time_range: TimeRange,
    limit: int,
) -> list[tuple[str, Decimal]]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    labels: dict[str, str] = {}
    for stream in streams:
        amount = _income_stream_amount_for_period(stream, time_range)
        key = getattr(stream, "stream_type", None)
        if not isinstance(key, str) or not key:
            key = "other"
        icon = _income_icon(key)
        type_label = _income_label(key)
        raw_name = getattr(stream, "name", None)
        stored_name = raw_name.strip() if isinstance(raw_name, str) else ""
        # Strip any legacy "<type prefix> — " baked into stored names so old
        # rows display the same as freshly-synced ones until the migration
        # has run. Both the historical "Thuê BĐS" wording and the current
        # "BĐS cho thuê" wording are normalised away.
        pure_name = _strip_legacy_prefix(stored_name)
        if _income_auto_linked(key):
            # Auto-linked streams (currently only rental) always render as
            # "{icon} {type_label} — {asset_name}" so changes to the YAML
            # label propagate without touching DB rows.
            display = (
                f"{icon} {type_label} — {pure_name}"
                if pure_name
                else f"{icon} {type_label}"
            )
        else:
            display = f"{icon} {pure_name or type_label}"
        totals[display] += amount
        labels[display] = display
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [(labels[label], amount) for label, amount in ranked[:limit]]


def _top_expense_categories(
    expenses: Iterable[Expense], *, limit: int
) -> list[tuple[str, Decimal]]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for tx in expenses:
        category = get_category(getattr(tx, "category", None) or "other")
        label = f"{category.emoji} {category.name_vi}"
        totals[label] += Decimal(tx.amount or 0)
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]


def _daily_flow_lines(expenses: list[Expense]) -> list[str]:
    if not expenses:
        return ["Chưa có giao dịch trong tháng này."]
    totals: dict[date, Decimal] = defaultdict(Decimal)
    for tx in expenses:
        day = getattr(tx, "expense_date", None)
        if day is not None:
            totals[day] += Decimal(tx.amount or 0)
    if not totals:
        return ["Chưa đủ ngày giao dịch để vẽ nhịp chi tiêu."]
    best_day = min(totals.items(), key=lambda item: item[1])
    worst_day = max(totals.items(), key=lambda item: item[1])
    return [
        f"Ngày nhẹ nhất: {best_day[0].strftime('%d/%m')} — {format_money_short(best_day[1])}",
        f"Ngày chi cao nhất: {worst_day[0].strftime('%d/%m')} — {format_money_short(worst_day[1])}",
    ]


def _safe_rate(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator / denominator * 100)


def _format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}%"


def _cashflow_tip(period: CashflowPeriod, saving_rate: float | None) -> str:
    if period.income <= 0:
        return "💡 Mẹo: thêm nguồn thu để Bé Tiền tính tỷ lệ tiết kiệm chính xác hơn."
    if period.net < 0:
        return "💡 Mẹo: xem lại 1–2 nhóm chi lớn nhất trước khi thêm khoản mới."
    if saving_rate is not None and saving_rate >= 20:
        return (
            "💡 Mẹo: dòng tiền đang ổn — cân nhắc chuyển phần dư vào mục tiêu ưu tiên."
        )
    return "💡 Mẹo: thử đặt mục tiêu tiết kiệm 20% thu nhập để có vùng đệm an toàn."


def _delta_text(current: Decimal, previous: Decimal) -> str:
    if previous <= 0:
        return "Chưa có dữ liệu tháng trước"
    delta = (current - previous) / previous * Decimal(100)
    if delta == 0:
        return "Không đổi"
    return f"{float(delta):+.1f}%"
