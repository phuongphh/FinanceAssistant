"""Price movement alerts for held stocks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from backend.config import get_settings
from backend.database import get_session_factory
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.client import get_price_cache
from backend.market_data.normalizer import PriceQuote
from backend.models.price_alert import NotificationSettings, PriceAlertLog
from backend.models.user import User
from backend.ports.notifier import get_notifier
from backend.wealth.models.asset import Asset


@dataclass(frozen=True)
class MovementAlert:
    user_id: object
    telegram_id: int
    symbol: str
    old_price: Decimal
    new_price: Decimal
    change_pct: Decimal
    severity: str
    message: str


def alerts_enabled() -> bool:
    return bool(getattr(get_settings(), "market_data_alerts_enabled", False))


def severity_for_change(change_pct: Decimal) -> str:
    magnitude = abs(change_pct)
    if magnitude > Decimal("10"):
        return "critical"
    if magnitude >= Decimal("7"):
        return "warning"
    return "info"


def format_alert_message(symbol: str, change_pct: Decimal, new_price: Decimal, severity: str) -> str:
    direction = "tăng" if change_pct > 0 else "giảm"
    icon = {"info": "🔔", "warning": "⚠️", "critical": "🚨"}[severity]
    return (
        f"{icon} Bé Tiền báo nhanh: {symbol} vừa {direction} {abs(change_pct):.1f}% trong 15 phút.\n"
        f"Giá mới khoảng {new_price:,.0f}đ. Bạn kiểm tra danh mục khi tiện nhé."
    )


async def _last_known_15m(cache: PriceCache, quote: PriceQuote) -> PriceQuote | None:
    # Cache layer stores one last-known quote. Jobs update it every run, so its
    # value is the practical 15-minute comparison point for the stock cron.
    return await cache.get_last_known(quote.symbol, quote.asset_type)


async def _users_holding(db, symbol: str) -> list[tuple[User, bool]]:
    result = await db.execute(
        select(User, NotificationSettings.price_alerts_enabled, Asset.extra)
        .join(Asset, Asset.user_id == User.id)
        .outerjoin(NotificationSettings, NotificationSettings.user_id == User.id)
        .where(Asset.asset_type == "stock", Asset.is_active.is_(True), Asset.extra.is_not(None))
    )
    rows: list[tuple[User, bool]] = []
    for user, enabled, extra in result.all():
        held = str((extra or {}).get("ticker") or (extra or {}).get("symbol") or "").upper().strip()
        if held == symbol.upper():
            rows.append((user, True if enabled is None else bool(enabled)))
    return rows


async def _can_send(db, user_id, symbol: str, now: datetime) -> bool:
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_count = await db.scalar(
        select(func.count()).select_from(PriceAlertLog).where(
            PriceAlertLog.user_id == user_id,
            PriceAlertLog.sent_at >= start_day,
        )
    )
    if int(day_count or 0) >= 3:
        return False
    cooldown_count = await db.scalar(
        select(func.count()).select_from(PriceAlertLog).where(
            PriceAlertLog.user_id == user_id,
            PriceAlertLog.symbol == symbol,
            PriceAlertLog.sent_at >= now - timedelta(minutes=30),
        )
    )
    return int(cooldown_count or 0) == 0


async def check_movements(quotes: Iterable[PriceQuote], *, cache: PriceCache | None = None) -> list[MovementAlert]:
    """Detect >=5% moves vs last-known and send/log Telegram alerts when enabled."""
    if not alerts_enabled():
        return []
    price_cache = cache or get_price_cache()
    now = datetime.now(timezone.utc)
    alerts: list[MovementAlert] = []
    async with get_session_factory()() as db:
        for quote in quotes:
            previous = await _last_known_15m(price_cache, quote)
            if previous is None or previous.price == 0:
                continue
            change_pct = (quote.price - previous.price) / previous.price * Decimal(100)
            if abs(change_pct) < Decimal("5.0"):
                continue
            severity = severity_for_change(change_pct)
            message = format_alert_message(quote.symbol, change_pct, quote.price, severity)
            holders = await _users_holding(db, quote.symbol)
            for user, enabled in holders:
                if not enabled or not await _can_send(db, user.id, quote.symbol, now):
                    continue
                alert = MovementAlert(user.id, user.telegram_id, quote.symbol, previous.price, quote.price, change_pct, severity, message)
                result = await get_notifier().send_message(user.telegram_id, message)
                if result is None or result.get("ok", True):
                    db.add(PriceAlertLog(user_id=user.id, symbol=quote.symbol, change_pct=change_pct, severity=severity, message=message, sent_at=now))
                    alerts.append(alert)
        await db.commit()
    return alerts
