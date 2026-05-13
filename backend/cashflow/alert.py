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
from backend.services.notifier_resolver import ChannelTarget, resolve_targets

logger = logging.getLogger(__name__)

_CONTENT_PATH = Path(__file__).resolve().parents[2] / "content" / "cashflow.yaml"
_ZALO_CONTENT_PATH = Path(__file__).resolve().parents[2] / "content" / "zalo.yaml"

ALERT_REDIS_TTL_SECONDS = 7 * 24 * 3600   # 7 days


# ── Public API ───────────────────────────────────────────────────────────────


async def check_and_send_alert(
    db: AsyncSession,
    user: User,
    confirmed_patterns: list[RecurringPattern],
) -> bool:
    """Check latest forecast and send alert across all opted-in channels.

    Returns True if at least one channel accepted the alert this call.
    Caller must have already committed the updated forecast.

    Multi-channel semantics (Phase 4B Epic 4 / Story #441):
    - Telegram is always attempted.
    - Zalo is appended when the user has linked + the OA is configured.
    - Each channel has its own Redis dedup key so a Telegram-only resend
      next week doesn't suppress a freshly-linked Zalo channel that
      never got the alert.
    - Fail-open: a Zalo failure logs but never blocks the Telegram send,
      and vice versa. The function returns True if ANY channel succeeded.
    """
    forecast = await get_latest_forecast(db, user.id)
    if forecast is None or not forecast.low_balance_risk:
        return False

    low_month = forecast.low_balance_month
    if low_month is None:
        return False

    targets = resolve_targets(user)
    if not targets:
        logger.warning("cashflow alert: no notifier targets for user=%s", user.id)
        return False

    redis = _get_redis()
    any_sent = False
    for target in targets:
        sent = await _send_one_channel(
            target=target,
            user=user,
            forecast=forecast,
            confirmed_patterns=confirmed_patterns,
            low_month=low_month,
            redis=redis,
        )
        any_sent = any_sent or sent

    return any_sent


async def _send_one_channel(
    *,
    target: ChannelTarget,
    user: User,
    forecast: CashflowForecast,
    confirmed_patterns: list[RecurringPattern],
    low_month: date,
    redis: Any,
) -> bool:
    """Send the alert on a single channel with per-channel dedup.

    Returns True iff the send succeeded. Never raises — any exception
    is logged so the multi-channel fan-out continues.
    """
    # Backwards-compatible dedup key: Telegram keeps the original
    # ``cashflow_alert:{user}:{month}`` shape from before Epic 4 so
    # the rollout doesn't replay alerts already sent before deploy.
    # New channels (Zalo, …) include the channel suffix.
    if target.channel == "telegram":
        alert_key = f"cashflow_alert:{user.id}:{low_month.isoformat()}"
    else:
        alert_key = (
            f"cashflow_alert:{user.id}:{target.channel}:{low_month.isoformat()}"
        )
    try:
        already_sent = await redis.exists(alert_key)
    except Exception:
        # Redis unreachable → fail-open and attempt the send. We'd
        # rather send twice than not at all when dedup is degraded.
        logger.warning(
            "cashflow alert: redis dedup check failed channel=%s user=%s",
            target.channel,
            user.id,
            exc_info=True,
        )
        already_sent = False

    if already_sent:
        logger.debug(
            "cashflow alert: dedup hit channel=%s user=%s month=%s",
            target.channel,
            user.id,
            low_month,
        )
        return False

    message = _format_alert_for_channel(
        forecast, confirmed_patterns, channel=target.channel
    )
    chat_id_arg = _coerce_chat_id(target.target_id)
    try:
        if target.channel == "telegram":
            result = await target.notifier.send_message(
                chat_id=chat_id_arg, text=message, parse_mode="HTML"
            )
        else:
            # Zalo (and any future channel) ignores parse_mode by
            # design; passing it would still be safe but we keep the
            # call minimal.
            result = await target.notifier.send_message(
                chat_id=chat_id_arg, text=message
            )
    except Exception:
        # Defence-in-depth: Notifier contract says "never raise", but
        # if a buggy adapter does, we MUST keep the fan-out going.
        logger.warning(
            "cashflow alert: notifier raised channel=%s user=%s",
            target.channel,
            user.id,
            exc_info=True,
        )
        return False

    if result is None:
        logger.warning(
            "cashflow alert: send failed channel=%s user=%s — will retry on next run",
            target.channel,
            user.id,
        )
        return False

    try:
        await redis.setex(alert_key, ALERT_REDIS_TTL_SECONDS, "sent")
    except Exception:
        # Mirror the dedup-check fail-open: a send already happened,
        # we just couldn't write the dedup key.
        logger.warning(
            "cashflow alert: redis setex failed channel=%s user=%s",
            target.channel,
            user.id,
            exc_info=True,
        )

    logger.info(
        "cashflow alert: sent channel=%s user=%s month=%s",
        target.channel,
        user.id,
        low_month,
    )
    return True


def _coerce_chat_id(target_id: str) -> int:
    """Telegram notifier expects an int chat_id; Zalo notifier ignores
    the argument. Best-effort cast so both paths share the call site.
    """
    try:
        return int(target_id)
    except (TypeError, ValueError):
        return 0


# ── Message formatting ───────────────────────────────────────────────────────


def _format_alert(
    forecast: CashflowForecast,
    confirmed_patterns: list[RecurringPattern],
) -> str:
    """Default formatter — kept for backwards compatibility. Always
    returns the Telegram HTML format."""
    return _format_alert_for_channel(forecast, confirmed_patterns, channel="telegram")


def _format_alert_for_channel(
    forecast: CashflowForecast,
    confirmed_patterns: list[RecurringPattern],
    *,
    channel: str,
) -> str:
    """Render the cashflow alert for a specific channel.

    - ``telegram`` → HTML formatting + full body + footer (links to
      Mini App). Length is not constrained.
    - ``zalo`` → plain text, no Markdown, terser body (Story #441
      requires ≤300 chars). The notifier still truncates as defence-
      in-depth, but we keep the message naturally short here so the
      ellipsis path is the exception.
    """
    low_month = forecast.low_balance_month
    month_label = _month_label(low_month) if low_month else "tháng tới"
    balance = _get_month_balance(forecast, low_month)
    balance_str = _fmt_money(balance)
    threshold = forecast.low_balance_threshold
    threshold_str = _fmt_money(threshold)
    suggested = _suggested_action(balance, threshold)

    if channel == "zalo":
        zalo_copy = _load_zalo_copy().get("cashflow_alert", {})
        template_key = "body" if threshold else "body_no_threshold"
        template = zalo_copy.get(template_key) or zalo_copy.get("body", "")
        return template.format(
            month=month_label,
            balance=balance_str,
            threshold=threshold_str,
            suggested_action=suggested,
        ).strip()

    # Default = telegram
    copy = _load_copy()
    alert_copy = copy.get("cashflow_alert", {})
    top_expense = _find_top_expense_pattern(confirmed_patterns)
    title = alert_copy.get("title", "⚠️ Cashflow {month}").format(month=month_label)
    body = alert_copy.get("body", "").format(
        month=month_label,
        balance=balance_str,
        threshold=threshold_str,
        top_expense_pattern=top_expense,
        suggested_action=suggested,
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


@lru_cache(maxsize=1)
def _load_zalo_copy() -> dict[str, Any]:
    try:
        with open(_ZALO_CONTENT_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("zalo.yaml not found — using fallback strings")
        return {}


def _get_redis() -> Any:
    from backend.market_data.client import get_redis_client
    return get_redis_client()
