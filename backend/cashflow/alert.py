"""Phase 4B S17 — Low-balance cashflow alert engine.

Reads the latest ``CashflowForecast`` for each user and sends an alert
when any month in the 3-month horizon has a projected end-of-month
balance below the user's threshold.

De-duplication (Redis):
    key  = cashflow_alert:{user_id}:{low_balance_month_iso}
    TTL  = 7 days

The 7-day TTL means:
- An alert fires at most once per 7 days for the same risky month.
- If the forecast updates and the balance *worsens* after recovery, the
  TTL expiry naturally allows a re-alert.

Alert tone rules (CLAUDE.md + phase-4B-detailed.md):
- Use "có thể", "dự báo", "ước tính" — never "sẽ xảy ra".
- Always include a suggested action.
- ≤ 300 chars for Zalo (Epic 4 readiness).

Layer contract:
- This module is called by ``cashflow_forecast_job`` (after it commits
  the new forecast).
- Uses ``get_notifier()`` port — never imports telegram_service directly.
- Never calls db.commit() — the job owns the transaction boundary.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cashflow.forecast import get_latest_forecast
from backend.models.cashflow_forecast import CashflowForecast
from backend.models.recurring_pattern import PATTERN_TYPE_EXPENSE, RecurringPattern
from backend.models.user import User
from backend.ports.notifier import get_notifier

logger = logging.getLogger(__name__)

_CONTENT_PATH = Path(__file__).resolve().parents[2] / "content" / "cashflow.yaml"

ALERT_REDIS_TTL_SECONDS = 7 * 24 * 3600   # 7 days


# ── Public API ───────────────────────────────────────────────────────────────


async def check_and_send_alert(
    db: AsyncSession,
    user: User,
    confirmed_patterns: list[RecurringPattern],
) -> bool:
    """Check latest forecast and send alert if low-balance risk detected.

    Returns True if an alert was sent this call.
    Caller must have already committed the updated forecast.
    """
    forecast = await get_latest_forecast(db, user.id)
    if forecast is None or not forecast.low_balance_risk:
        return False

    low_month = forecast.low_balance_month
    if low_month is None:
        return False

    redis = _get_redis()
    alert_key = f"cashflow_alert:{user.id}:{low_month.isoformat()}"
    already_sent = await redis.exists(alert_key)
    if already_sent:
        logger.debug(
            "cashflow alert: dedup hit user=%s month=%s", user.id, low_month
        )
        return False

    message = _format_alert(forecast, confirmed_patterns)
    notifier = get_notifier()
    result = await notifier.send_message(
        chat_id=user.telegram_id,
        text=message,
        parse_mode="HTML",
    )
    if result is None:
        logger.warning(
            "cashflow alert: send failed user=%s — will retry on next run", user.id
        )
        return False

    await redis.setex(alert_key, ALERT_REDIS_TTL_SECONDS, "sent")
    logger.info("cashflow alert: sent user=%s month=%s", user.id, low_month)
    return True


# ── Message formatting ───────────────────────────────────────────────────────


def _format_alert(
    forecast: CashflowForecast,
    confirmed_patterns: list[RecurringPattern],
) -> str:
    copy = _load_copy()
    alert_copy = copy.get("cashflow_alert", {})

    low_month = forecast.low_balance_month
    month_label = _month_label(low_month) if low_month else "tháng tới"

    # Find the balance for the low month from monthly_data
    balance = _get_month_balance(forecast, low_month)
    balance_str = _fmt_money(balance)
    threshold_str = _fmt_money(forecast.low_balance_threshold)

    # Top expense pattern for context
    top_expense = _find_top_expense_pattern(confirmed_patterns)

    title = alert_copy.get("title", "⚠️ Cashflow {month}").format(month=month_label)
    body = alert_copy.get("body", "").format(
        month=month_label,
        balance=balance_str,
        threshold=threshold_str,
        top_expense_pattern=top_expense,
        suggested_action=_suggested_action(balance, forecast.low_balance_threshold),
    )
    footer = alert_copy.get("footer", "")

    return f"<b>{title}</b>\n\n{body}\n\n{footer}".strip()


def _get_month_balance(forecast: CashflowForecast, target_month: date | None) -> Decimal:
    if target_month is None:
        return Decimal(0)
    for item in forecast.monthly_data:
        if item.get("month") == target_month.isoformat():
            return Decimal(str(item.get("balance_eom", 0)))
    return Decimal(0)


def _find_top_expense_pattern(patterns: list[RecurringPattern]) -> str:
    expenses = [
        p for p in patterns if p.pattern_type == PATTERN_TYPE_EXPENSE and p.is_active
    ]
    if not expenses:
        return "chi tiêu định kỳ"
    top = max(expenses, key=lambda p: float(p.expected_amount))
    return top.description or top.name or "chi tiêu định kỳ"


def _suggested_action(balance: Decimal, threshold: Decimal | None) -> str:
    if threshold and balance < threshold:
        gap = threshold - balance
        gap_str = _fmt_money(gap)
        return f"Cân nhắc tiết kiệm thêm ~{gap_str} trong tháng này để đảm bảo an toàn."
    return "Theo dõi chi tiêu chặt chẽ hơn trong giai đoạn này."


def _month_label(d: date) -> str:
    return f"Tháng {d.month}/{d.year}"


def _fmt_money(amount: Decimal | None) -> str:
    if amount is None:
        return "—"
    try:
        from backend.bot.formatters.money import format_money_short
        return format_money_short(amount)
    except Exception:
        return f"{amount:,.0f} đ"


@lru_cache(maxsize=1)
def _load_copy() -> dict[str, Any]:
    try:
        with open(_CONTENT_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("cashflow.yaml not found — using fallback strings")
        return {}


def _get_redis() -> Any:
    from backend.market_data.client import get_redis_client
    return get_redis_client()
