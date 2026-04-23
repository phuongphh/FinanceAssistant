"""Seasonal event notifier — Phase 2, Issue #43.

Runs daily at 08:00 Asia/Ho_Chi_Minh. Loads the YAML calendar, resolves
each event's trigger date for the current year (respecting solar vs
lunar), and if any event's trigger date == today, sends the rendered
message to every active user.

Dedup: each (event_name, year) tuple fires at most once per user ever.
Tracked via the shared ``events`` table — no new schema needed.

Context fetching: some messages reference prior-year data (e.g. last
year's Mid-Autumn spend). The notifier looks these up per-user before
rendering so the message reads personally.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics import EventType
from backend.bot.formatters.money import format_money_full
from backend.database import get_session_factory
from backend.jobs._active_users import get_active_users
from backend.models.event import Event
from backend.models.expense import Expense
from backend.models.user import User
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)

_CALENDAR_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "content"
    / "seasonal_calendar.yaml"
)
_calendar_cache: dict | None = None

INTER_USER_DELAY_SECONDS = 1.0
ACTIVE_WINDOW_DAYS = 30


def _load_calendar() -> dict:
    global _calendar_cache
    if _calendar_cache is None:
        with open(_CALENDAR_PATH, encoding="utf-8") as f:
            _calendar_cache = yaml.safe_load(f) or {}
    return _calendar_cache


def reload_calendar_for_tests() -> None:
    global _calendar_cache
    _calendar_cache = None


# ---------- Date resolution ----------------------------------------

def _resolve_trigger_date(when_spec: dict, today: date) -> date | None:
    """Compute the current-year trigger date for a ``when`` spec.

    Returns the solar ``date`` the event fires on (in the current year,
    or the next occurrence if the lunar event this year has already
    passed by more than 60 days — avoids missing Tết in the next year
    if the scheduler first runs shortly after the date).
    """
    if "solar" in when_spec:
        spec = when_spec["solar"]
        month = int(spec["month"])
        day = int(spec["day"])
        offset = int(spec.get("offset_days", 0))
        try:
            base = date(today.year, month, day)
        except ValueError:
            # e.g. Feb 29 in a non-leap year — skip cleanly.
            return None
        return base + timedelta(days=offset)

    if "lunar" in when_spec:
        try:
            from lunardate import LunarDate
        except ImportError:  # pragma: no cover — listed in requirements
            logger.error("lunardate package not installed; skipping lunar event")
            return None
        spec = when_spec["lunar"]
        month = int(spec["month"])
        day = int(spec["day"])
        offset = int(spec.get("offset_days", 0))
        # Lunar year matches the solar year for most of the calendar.
        # If our computed date has already passed by > 60 days, also
        # compute next-year's so we don't silently skip events that
        # happen very early in the lunar year (e.g. Tết in late Jan).
        try:
            solar = LunarDate(today.year, month, day).toSolarDate()
        except Exception:
            return None
        candidate = solar + timedelta(days=offset)
        # If candidate is in the past by > 60 days, try next lunar year.
        if (today - candidate).days > 60:
            try:
                next_solar = LunarDate(today.year + 1, month, day).toSolarDate()
                candidate = next_solar + timedelta(days=offset)
            except Exception:
                pass
        return candidate

    return None


def _events_firing_today(today: date) -> list[dict]:
    """All calendar events whose resolved trigger date == today."""
    calendar = _load_calendar()
    matches: list[dict] = []
    for ev in calendar.get("events", []) or []:
        trigger = _resolve_trigger_date(ev.get("when") or {}, today)
        if trigger == today:
            matches.append(ev)
    return matches


# ---------- Context fetching ---------------------------------------

async def _last_year_mid_autumn_spend(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> float:
    """Rough estimate: spend across the 2-week window around last year's
    Mid-Autumn, filtered to food-ish categories.

    If the lib isn't available (shouldn't happen), fall back to 0.
    """
    try:
        from lunardate import LunarDate
    except ImportError:  # pragma: no cover
        return 0.0
    try:
        last_year_solar = LunarDate(today.year - 1, 8, 15).toSolarDate()
    except Exception:
        return 0.0
    start = last_year_solar - timedelta(days=7)
    end = last_year_solar + timedelta(days=7)
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= start,
        Expense.expense_date <= end,
        Expense.category.in_(("food", "food_drink", "gift")),
    )
    return float((await db.execute(stmt)).scalar_one() or 0)


async def _last_year_double_11_spend(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> float:
    """Spend on 11/11 and the 3 surrounding days of the previous year."""
    try:
        anchor = date(today.year - 1, 11, 11)
    except ValueError:
        return 0.0
    start = anchor - timedelta(days=1)
    end = anchor + timedelta(days=2)
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    )
    return float((await db.execute(stmt)).scalar_one() or 0)


async def _tet_total_so_far(
    db: AsyncSession, user_id: uuid.UUID, today: date
) -> float:
    """Sum of expenses tagged with 'tết' in merchant/note since the start
    of the current lunar new year window (~2 weeks before today)."""
    start = today - timedelta(days=21)
    stmt = select(Expense.amount, Expense.merchant, Expense.note).where(
        Expense.user_id == user_id,
        Expense.deleted_at.is_(None),
        Expense.expense_date >= start,
        Expense.expense_date <= today,
    )
    rows = (await db.execute(stmt)).all()
    total = 0.0
    for amount, merchant, note in rows:
        text = " ".join(filter(None, [merchant, note])).lower()
        if "tết" in text or "tet" in text or "lì xì" in text or "li xi" in text:
            total += float(amount)
    return total


async def _fetch_context(
    db: AsyncSession, user: User, event_name: str, today: date
) -> dict:
    """Gather placeholder values for the message template.

    Returns a dict that ``str.format`` can merge with ``{name}``.
    Each value is pre-formatted (e.g. VND strings) so the template
    doesn't need logic.
    """
    context: dict = {"name": user.get_greeting_name()}

    if event_name == "mid_autumn":
        spend = await _last_year_mid_autumn_spend(db, user.id, today)
        context["last_year_mid_autumn"] = (
            format_money_full(spend) if spend > 0 else "chưa có dữ liệu"
        )
    elif event_name == "double_11":
        spend = await _last_year_double_11_spend(db, user.id, today)
        context["last_year_double_11"] = (
            format_money_full(spend) if spend > 0 else "chưa có dữ liệu"
        )
    elif event_name == "post_tet_review":
        total = await _tet_total_so_far(db, user.id, today)
        context["tet_total"] = (
            format_money_full(total) if total > 0 else "chưa có dữ liệu rõ ràng"
        )
    return context


# ---------- Firing --------------------------------------------------

def _dedup_key(event_name: str, year: int) -> str:
    return f"{event_name}:{year}"


async def _already_fired(
    db: AsyncSession, user_id: uuid.UUID, event_name: str, year: int
) -> bool:
    stmt = select(func.count()).where(
        Event.user_id == user_id,
        Event.event_type == EventType.SEASONAL_FIRED,
        Event.properties["key"].astext == _dedup_key(event_name, year),
    )
    count = int((await db.execute(stmt)).scalar_one() or 0)
    return count > 0


async def run_seasonal_check(today: date | None = None) -> None:
    today = today or date.today()
    events_today = _events_firing_today(today)
    if not events_today:
        logger.debug("seasonal: no events firing on %s", today)
        return

    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await get_active_users(db, days=ACTIVE_WINDOW_DAYS)

    logger.info(
        "seasonal: %d event(s) firing today — delivering to %d users",
        len(events_today), len(users),
    )

    for event in events_today:
        for user in users:
            try:
                await _deliver(event, user, today)
            except Exception:
                logger.exception(
                    "seasonal: delivery failed event=%s user=%s",
                    event.get("name"), user.id,
                )
            await asyncio.sleep(INTER_USER_DELAY_SECONDS)


async def _deliver(event: dict, user: User, today: date) -> None:
    session_factory = get_session_factory()
    event_name = event.get("name") or ""
    template = event.get("message") or ""
    if not event_name or not template:
        return

    async with session_factory() as db:
        if await _already_fired(db, user.id, event_name, today.year):
            return
        if not user.telegram_id:
            return

        context = await _fetch_context(db, user, event_name, today)

        try:
            text = template.format(**context)
        except KeyError as exc:
            # Missing placeholder → log and send the raw template
            # (better silent-breaking than the user seeing {foo}).
            logger.warning(
                "seasonal: missing placeholder %s in %s", exc, event_name
            )
            text = template

        result = await send_message(
            chat_id=user.telegram_id,
            text=text,
            parse_mode="HTML",
        )
        if result is None:
            logger.warning(
                "seasonal: send failed event=%s user=%s", event_name, user.id
            )
            return

        # Single insert serves both dedup (_already_fired reads this
        # back by the `key` property) and analytics — writing via
        # `analytics.track` too would double-count every delivery.
        db.add(
            Event(
                user_id=user.id,
                event_type=EventType.SEASONAL_FIRED,
                properties={
                    "key": _dedup_key(event_name, today.year),
                    "event": event_name,
                    "year": today.year,
                },
                timestamp=datetime.now(timezone.utc),
            )
        )
        await db.commit()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_seasonal_check())
