"""Phase 3.9 enriched morning briefing with real market data."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
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

_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "content" / "briefing.yaml"


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


async def _portfolio_assets(db: AsyncSession, user_id) -> list[Asset]:
    result = await db.execute(select(Asset).where(Asset.user_id == user_id, Asset.is_active.is_(True)))
    return list(result.scalars().all())


def _allocation_lines(breakdown: net_worth_calculator.NetWorthBreakdown) -> str:
    if breakdown.total <= 0:
        return "• Chưa có tài sản"
    lines: list[str] = []
    for asset_type, value in sorted(breakdown.by_type.items(), key=lambda item: item[1], reverse=True):
        pct = value / breakdown.total * Decimal(100)
        lines.append(f"• {asset_type}: {format_money_short(value)} ({pct:.0f}%)")
    return "\n".join(lines)


def _news_lines(news: list[Any]) -> str:
    if not news:
        return "• Chưa có tin nổi bật cho danh mục của bạn."
    return "\n".join(f"• {item.title}" for item in news[:3])


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
    """Render five real-data sections; independent data fetches run concurrently."""
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
    vnindex = await _latest_market_snapshot(db, "VNINDEX")
    assets = await _portfolio_assets(db, user.id)
    vcb_rate = await _latest_vcb_rate(db)
    btc, gold, news = await asyncio.gather(
        crypto_quote("BTC"),
        gold_quote(),
        get_relevant_news(user.id, limit=3),
    )
    performers = await get_best_worst_from_assets(assets)
    diversification = compute_diversification_score([{"asset_type": asset.asset_type, "value": Decimal(asset.current_value or 0)} for asset in assets])

    is_stale = bool((btc and btc.is_stale) or (gold and gold.is_stale))
    level = detect_level(breakdown.total)
    is_empty_state = breakdown.asset_count == 0 or breakdown.total <= 0
    insight_lines = _insights(assets, vcb_rate)
    top, bottom = performers
    if top is not None:
        insight_lines.append(f"Tốt nhất: {top['symbol']} {_signed_pct(top['return_pct'])}%; yếu nhất: {bottom['symbol']} {_signed_pct(bottom['return_pct'])}%.")
    insight_lines.append(f"Đa dạng hóa: {diversification['score']}/100 ({diversification['label']}).")

    sections = {
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
        ),
        "news": template["sections"]["news"].format(news_lines=_news_lines(news)),
        "insights": template["sections"]["insights"].format(insight_lines="\n".join(f"• {line}" for line in insight_lines[:4])),
    }
    text = "\n\n".join(sections.values())
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

