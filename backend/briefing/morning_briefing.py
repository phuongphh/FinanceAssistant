"""Phase 3.9 enriched morning briefing with real market data."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.bot.formatters.movers import format_movers_line
from backend.market_data.analytics.news_relevance import get_relevant_news
from backend.market_data.analytics.portfolio_metrics import (
    compute_diversification_score,
    get_best_worst_from_assets,
)
from backend.market_data.client import get_crypto_quote, get_gold_quote
from backend.models.bank_rate import BankRateSnapshot
from backend.models.market_snapshot import MarketSnapshot
from backend.models.user import User
from backend.wealth.ladder import WealthLevel, detect_level
from backend.wealth.models.asset import Asset
from backend.wealth.services import net_worth_calculator

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "content" / "briefing.yaml"
_TWIN_COPY_PATH = Path(__file__).resolve().parents[2] / "content" / "twin_copy.yaml"


@dataclass(frozen=True)
class EnrichedBriefingResult:
    text: str
    level: WealthLevel
    is_empty_state: bool = False
    is_stale: bool = False
    render_ms: int = 0
    sections: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.text)


@lru_cache(maxsize=1)
def _load_template() -> dict[str, Any]:
    with open(_TEMPLATE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _load_twin_copy() -> dict[str, Any]:
    with open(_TWIN_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["briefing"]


def _morning_emoji() -> str:
    """Static fallback emoji for the morning greeting.

    Phase 3.9.5 attaches Telegram ``custom_emoji`` entities at the transport
    boundary instead of embedding HTML tags here, keeping this renderer plain
    text and safe for non-Telegram consumers/tests.
    """
    return "🌤️"


def _greeting_name(user: User) -> str:
    if hasattr(user, "get_greeting_name"):
        return user.get_greeting_name()
    return (getattr(user, "display_name", None) or "bạn").strip() or "bạn"


def _greeting_line(user: User) -> str:
    return f"{_morning_emoji()} Chào buổi sáng, {_greeting_name(user)}!"


def _fmt_decimal(value: Decimal | int | float | None, suffix: str = "") -> str:
    if value is None:
        return "chưa có"
    dec = Decimal(str(value))
    if dec == dec.to_integral():
        return f"{dec:,.0f}{suffix}"
    return f"{dec:,.2f}{suffix}"


def _signed_pct(value: float | Decimal | None) -> str:
    if value is None:
        return "0.0"
    return f"{float(value):+.1f}"


def _quote_line(price: Decimal | None, change_pct: Any = None, currency: str = "") -> str:
    if price is None:
        return "chưa có dữ liệu"
    suffix = f" {currency}" if currency else ""
    change = "" if change_pct is None else f" ({_signed_pct(change_pct)}%)"
    return f"{_fmt_decimal(price, suffix)}{change}"


async def _latest_market_snapshot(db: AsyncSession, code: str) -> MarketSnapshot | None:
    result = await db.execute(
        select(MarketSnapshot)
        .where(MarketSnapshot.asset_code == code)
        .order_by(desc(MarketSnapshot.snapshot_date))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_vcb_rate(db: AsyncSession) -> Decimal | None:
    result = await db.execute(
        select(BankRateSnapshot.rate_pct)
        .where(BankRateSnapshot.bank_code == "VCB")
        .order_by(desc(BankRateSnapshot.snapshot_date))
        .limit(1)
    )
    return result.scalar_one_or_none()



_ASSET_TYPE_LABELS = {
    "cash": "Tiền mặt",
    "stock": "Cổ phiếu/Quỹ",
    "real_estate": "Bất động sản",
    "crypto": "Tiền số",
    "gold": "Vàng",
    "other": "Khác",
}


def _asset_type_label(asset_type: str) -> str:
    return _ASSET_TYPE_LABELS.get(str(asset_type), str(asset_type).replace("_", " ").title())

async def _portfolio_assets(db: AsyncSession, user_id) -> list[Asset]:
    result = await db.execute(select(Asset).where(Asset.user_id == user_id, Asset.is_active.is_(True)))
    return list(result.scalars().all())


def _allocation_lines(breakdown: net_worth_calculator.NetWorthBreakdown) -> str:
    if breakdown.total <= 0:
        return "• Chưa có tài sản"
    lines: list[str] = []
    for asset_type, value in sorted(breakdown.by_type.items(), key=lambda item: item[1], reverse=True):
        pct = value / breakdown.total * Decimal(100)
        lines.append(f"• {_asset_type_label(asset_type)}: {format_money_short(value)} ({pct:.0f}%)")
    return "\n".join(lines)


def _news_lines(news: list[Any]) -> str:
    if not news:
        return "• Chưa có tin nổi bật cho danh mục của bạn."
    return "\n".join(f"• {item.title}" for item in news[:3])



async def _twin_briefing_line(db: AsyncSession, user_id) -> str:
    """Return one encouraging Twin delta line, or empty when no projection exists."""
    try:
        from backend.twin.services.twin_query_service import get_twin_snapshot

        snapshot = await get_twin_snapshot(db, user_id)
    except Exception:
        return ""
    if snapshot.projection is None or snapshot.delta_vs_p50 is None:
        return ""
    reference = snapshot.actual_nw - snapshot.delta_vs_p50
    if reference <= 0:
        return ""
    delta_pct = snapshot.delta_vs_p50 / reference * Decimal(100)
    copy = _load_twin_copy()
    pct_text = f"{abs(delta_pct):.0f}"
    if delta_pct > Decimal("5"):
        return copy["ahead"].format(delta_pct=pct_text)
    if delta_pct < Decimal("-5"):
        return copy["behind"].format(delta_pct=pct_text)
    return copy["on_track"].format(delta_pct=pct_text)


async def _cashflow_briefing_section(db: AsyncSession, user_id) -> str:
    """Return 1-2 line cashflow summary for the morning briefing.

    Only shown when the user has ≥ 2 confirmed recurring patterns
    (per spec S19 — avoid false confidence with thin data).
    Returns empty string when conditions are not met.
    """
    try:
        from backend.cashflow.forecast import get_latest_forecast
        from backend.cashflow.detector import load_confirmed_patterns
        from pathlib import Path
        import yaml

        confirmed = await load_confirmed_patterns(db, user_id)
        if len(confirmed) < 2:
            return ""

        forecast = await get_latest_forecast(db, user_id)
        if forecast is None or not forecast.monthly_data:
            return ""

        content_path = Path(__file__).resolve().parents[2] / "content" / "cashflow.yaml"
        with open(content_path, encoding="utf-8") as f:
            copy = yaml.safe_load(f) or {}
        briefing_copy = copy.get("briefing_cashflow", {})

        # Use the first forecast month (next month data)
        next_month = forecast.monthly_data[0]
        from decimal import Decimal
        income = Decimal(str(next_month.get("income", 0)))
        expense = Decimal(str(next_month.get("expense", 0)))
        net = Decimal(str(next_month.get("net", 0)))

        net_sign = "+" if net >= 0 else "−"
        section_line = briefing_copy.get("section", "").format(
            net_sign=net_sign,
            net=format_money_short(abs(net)),
            income=format_money_short(income),
            expense=format_money_short(expense),
        )

        lines = [section_line]

        if forecast.low_balance_risk and forecast.low_balance_month:
            low_month = forecast.low_balance_month
            month_label = f"Tháng {low_month.month}/{low_month.year}"
            # Find balance for that month
            balance = Decimal(0)
            for m in forecast.monthly_data:
                if m.get("month") == low_month.isoformat():
                    balance = Decimal(str(m.get("balance_eom", 0)))
                    break
            warn_line = briefing_copy.get("low_balance_warning", "").format(
                month=month_label,
                balance=format_money_short(balance),
            )
            if warn_line:
                lines.append(warn_line)

        return "\n".join(lines)
    except Exception:
        logger.debug("cashflow briefing section failed — skipping", exc_info=True)
        return ""


async def _twin_accuracy_line(db: AsyncSession, user_id) -> str:
    """Return accuracy comparison line when ≥2 projections exist."""
    try:
        from backend.twin.accuracy import get_accuracy_summary

        summary = await get_accuracy_summary(db, user_id)
    except Exception:
        return ""
    if summary is None:
        return ""
    copy = _load_twin_copy()
    template_key = f"accuracy_{summary.tone}"
    template = copy.get(template_key, copy.get("accuracy_neutral", ""))
    if not template:
        return ""
    error_sign = "+" if summary.error_pct >= 0 else ""
    return template.format(
        predicted=format_money_short(summary.predicted_p50),
        actual=format_money_short(summary.actual),
        error_pct=f"{error_sign}{summary.error_pct:.1f}",
    )


def _insights(assets: list[Asset], vcb_rate: Decimal | None) -> list[str]:
    insights: list[str] = []
    for asset in assets:
        if asset.asset_type != "stock":
            continue
        extra = asset.extra or {}
        avg = extra.get("avg_price") or extra.get("user_input_price")
        current = extra.get("current_price")
        if avg and current:
            change = (Decimal(str(current)) - Decimal(str(avg))) / Decimal(str(avg)) * Decimal(100)
            if change > 5:
                symbol = extra.get("ticker") or extra.get("symbol") or asset.name
                insights.append(f"{symbol} đang tăng hơn 5% — có thể chốt lời 1 phần?")
                break
    if vcb_rate is not None:
        for asset in assets:
            if asset.asset_type != "cash":
                continue
            extra = asset.extra or {}
            rate = extra.get("rate_pct")
            bank = extra.get("bank_code") or extra.get("bank")
            if rate is not None and Decimal(str(rate)) + Decimal("0.5") < vcb_rate:
                insights.append(f"Lãi suất {bank or 'ngân hàng hiện tại'} thấp hơn VCB >0.5% — cân nhắc chuyển ngân hàng.")
                break
    return insights[:2] or ["Danh mục ổn, hôm nay mình chỉ cần theo dõi nhẹ thôi."]


async def render_enriched_morning_briefing(db: AsyncSession, user: User) -> EnrichedBriefingResult:
    """Render greeting plus five real-data sections; external fetches run concurrently."""
    import time

    started = time.perf_counter()
    template = _load_template()

    async def crypto_quote(symbol: str):
        try:
            return await get_crypto_quote(symbol)
        except Exception:
            return None

    async def gold_quote():
        try:
            return await get_gold_quote("SJC_GOLD")
        except Exception:
            return None

    # Keep AsyncSession reads sequential (SQLAlchemy sessions are not safe for
    # concurrent DB use), while external provider/RSS calls run in parallel.
    breakdown = await net_worth_calculator.calculate(db, user.id)
    change = await net_worth_calculator.calculate_change(db, user.id, net_worth_calculator.PERIOD_DAY)
    movers = await net_worth_calculator.get_daily_movers(db, user.id)
    vnindex = await _latest_market_snapshot(db, "VNINDEX")
    assets = await _portfolio_assets(db, user.id)
    vcb_rate = await _latest_vcb_rate(db)
    btc, gold, news = await asyncio.gather(
        crypto_quote("BTC"),
        gold_quote(),
        get_relevant_news(user.id, limit=3),
    )
    twin_line = await _twin_briefing_line(db, user.id)
    twin_accuracy_line = await _twin_accuracy_line(db, user.id)
    cashflow_section = await _cashflow_briefing_section(db, user.id)
    performers = await get_best_worst_from_assets(assets)
    diversification = compute_diversification_score([{"asset_type": asset.asset_type, "value": Decimal(asset.current_value or 0)} for asset in assets])

    is_stale = bool((btc and btc.is_stale) or (gold and gold.is_stale))
    level = detect_level(breakdown.total)
    is_empty_state = breakdown.asset_count == 0 or breakdown.total <= 0
    insight_lines = _insights(assets, vcb_rate)
    top, bottom = performers
    insight_templates = template["insights_lines"]
    if top is not None and bottom is not None and top.get("return_pct") is not None:
        if top["asset_id"] == bottom["asset_id"]:
            # Only one investment holding has a comparable return — calling
            # the same asset both "best" and "worst" reads as a bug to users,
            # so collapse to a single-asset line.
            insight_lines.append(
                insight_templates["performance_single"].format(
                    symbol=top["symbol"],
                    pct=_signed_pct(top["return_pct"]),
                )
            )
        else:
            insight_lines.append(
                insight_templates["performance_pair"].format(
                    best_symbol=top["symbol"],
                    best_pct=_signed_pct(top["return_pct"]),
                    worst_symbol=bottom["symbol"],
                    worst_pct=_signed_pct(bottom["return_pct"]),
                )
            )
    insight_lines.append(
        insight_templates["diversification"].format(
            score=diversification["score"],
            label=diversification["label"],
        )
    )

    sections = {
        "greeting": template["sections"]["greeting"].format(
            greeting=_greeting_line(user),
        ),
        "net_worth": template["sections"]["net_worth"].format(
            net_worth=format_money_short(breakdown.total),
            change_label="So với hôm qua",
            change_abs=format_money_short(change.change_absolute),
            change_pct=_signed_pct(change.change_percentage),
        ),
        "market": template["sections"]["market"].format(
            vnindex=_quote_line(Decimal(str(vnindex.price)) if vnindex and vnindex.price is not None else None, vnindex.change_1d_pct if vnindex else None),
            gold=_quote_line(gold.price if gold else None, None, "VND/lượng"),
            btc=_quote_line(btc.price if btc else None, None, btc.currency if btc else ""),
        ),
        "portfolio": template["sections"]["portfolio"].format(
            allocation_lines=_allocation_lines(breakdown),
            today_change=f"{format_money_short(change.change_absolute)} ({_signed_pct(change.change_percentage)}%)",
            movers_line=format_movers_line(movers) or "—",
        ),
        "news": template["sections"]["news"].format(news_lines=_news_lines(news)),
        "insights": template["sections"]["insights"].format(insight_lines="\n".join(f"• {line}" for line in insight_lines[:4])),
    }
    if twin_line:
        sections["twin"] = twin_line
    if twin_accuracy_line:
        sections["twin_accuracy"] = twin_accuracy_line
    if cashflow_section:
        sections["cashflow"] = cashflow_section
    text = "\n\n".join(section.strip() for section in sections.values() if section)
    if is_stale:
        text = f"{text}\n\n{template['footer']['stale']}"
    return EnrichedBriefingResult(
        text=text,
        level=level,
        is_empty_state=is_empty_state,
        is_stale=is_stale,
        render_ms=int((time.perf_counter() - started) * 1000),
        sections=sections,
    )

