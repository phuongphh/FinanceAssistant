"""Product analytics — lightweight, non-blocking event tracking.

Fire-and-forget API used by bot handlers, miniapp routes, and schedulers.
Each event is a row in the `events` table (see `backend/models/event.py`).

Design choices
--------------
- Non-blocking: `track(event)` schedules the DB write on the running event
  loop and returns immediately. Callers never `await` the persistence.
- Strict no-PII policy: `sanitize_properties()` drops any key whose name
  hints at message content, phone numbers, addresses, credentials. It also
  truncates stringy values at 200 chars as a defence-in-depth measure.
- Explicit event type constants (see `EventType`) so call sites can't typo
  the wire format.
- Swallows all failures during background write — analytics must never
  break the user flow.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session_factory
from backend.models.event import Event

logger = logging.getLogger(__name__)


class EventType:
    """Canonical names for every tracked event."""
    BOT_STARTED = "bot_started"
    TRANSACTION_CREATED = "transaction_created"
    BUTTON_TAPPED = "button_tapped"
    CATEGORY_CHANGED = "category_changed"
    TRANSACTION_DELETED = "transaction_deleted"
    MINIAPP_OPENED = "miniapp_opened"
    MINIAPP_LOADED = "miniapp_loaded"

    # Phase 2 personality jobs. These also land in the `events` table,
    # where the empathy engine / seasonal notifier query them to
    # enforce cooldowns and once-per-year dedup.
    MILESTONE_CELEBRATED = "milestone_celebrated"
    STREAK_MILESTONE_HIT = "streak_milestone_hit"
    EMPATHY_FIRED = "empathy_fired"
    EMPATHY_SENT = "empathy_sent"
    FUN_FACT_SENT = "fun_fact_sent"
    SEASONAL_FIRED = "seasonal_fired"
    GOAL_REMINDER_SENT = "goal_reminder_sent"

    # Phase 3A — Morning briefing funnel. The job uses _SENT for the
    # daily-dedup query (see `morning_briefing_job.already_sent_today`)
    # so the constant doubles as the single source of truth for both
    # producers and consumers of the dedup signal.
    MORNING_BRIEFING_SENT = "morning_briefing_sent"
    MORNING_BRIEFING_OPENED = "morning_briefing_opened"
    BRIEFING_DASHBOARD_CLICKED = "briefing_dashboard_clicked"
    BRIEFING_STORY_CLICKED = "briefing_story_clicked"
    BRIEFING_ADD_ASSET_CLICKED = "briefing_add_asset_clicked"
    BRIEFING_SETTINGS_CLICKED = "briefing_settings_clicked"

    # Daily snapshot job — counters land here so we can confirm the
    # 23:59 cron actually ran each day (one row = one job execution).
    DAILY_SNAPSHOT_RUN = "daily_snapshot_run"

    # Phase 3A — wealth dashboard funnel. ``WEALTH_DASHBOARD_VIEWED`` is
    # logged on every successful overview API hit; the property ``from``
    # tells us where the open came from (``briefing``, ``menu``, ``deep_link``)
    # so the user-testing scoreboard can attribute opens to morning briefings
    # vs organic discovery.
    WEALTH_DASHBOARD_VIEWED = "wealth_dashboard_viewed"
    WEALTH_TREND_VIEWED = "wealth_trend_viewed"
    WEALTH_LEVEL_UP = "wealth_level_up"


# Property keys that would carry PII if ever accepted — strip unconditionally.
_PII_KEY_PATTERN = re.compile(
    r"(?i)(phone|email|address|token|password|secret|message|content|"
    r"merchant_name|note|raw_text|body|text)"
)
_MAX_STR_VALUE_LEN = 200


def sanitize_properties(props: dict[str, Any] | None) -> dict[str, Any]:
    """Strip PII keys and truncate long stringy values.

    Primitive, conservative — when in doubt, drop.
    """
    if not props:
        return {}
    out: dict[str, Any] = {}
    for key, value in props.items():
        if not isinstance(key, str):
            continue
        if _PII_KEY_PATTERN.search(key):
            continue
        if isinstance(value, str) and len(value) > _MAX_STR_VALUE_LEN:
            value = value[:_MAX_STR_VALUE_LEN]
        # Drop values that aren't JSON-friendly scalars/containers
        if not _is_json_friendly(value):
            continue
        out[key] = value
    return out


def _is_json_friendly(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_friendly(v) for v in value)
    if isinstance(value, dict):
        return all(
            isinstance(k, str) and _is_json_friendly(v)
            for k, v in value.items()
        )
    return False


@dataclass
class Event_:  # noqa: N801 — underscore suffix avoids clash with ORM `Event`
    """Structured analytics event ready to write to the events table."""
    event_type: str
    user_id: uuid.UUID | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Keep track of background tasks so they aren't GC'd mid-flight.
_pending: set[asyncio.Task] = set()


def track(
    event_type: str,
    user_id: uuid.UUID | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget tracking call.

    Safe to call from sync or async contexts. Returns immediately.
    If no event loop is running (e.g. inside a sync CLI), the event is
    written synchronously via a fresh session; failures are swallowed.
    """
    clean_props = sanitize_properties(properties)
    event = Event_(
        event_type=event_type,
        user_id=user_id,
        properties=clean_props,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop — try a synchronous best-effort write.
        try:
            asyncio.run(_persist(event))
        except Exception:
            logger.debug("analytics track() sync-write failed for %s", event_type, exc_info=True)
        return

    task = loop.create_task(_persist(event))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def atrack(
    event_type: str,
    user_id: uuid.UUID | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Async variant — await this if the caller needs ordering guarantees."""
    clean_props = sanitize_properties(properties)
    event = Event_(
        event_type=event_type,
        user_id=user_id,
        properties=clean_props,
    )
    await _persist(event)


async def _persist(event: Event_) -> None:
    """Best-effort persist — any DB error is swallowed and logged."""
    try:
        session_factory = get_session_factory()
    except Exception:
        logger.debug("analytics: no session factory available", exc_info=True)
        return

    try:
        async with session_factory() as session:
            session.add(
                Event(
                    user_id=event.user_id,
                    event_type=event.event_type,
                    properties=event.properties,
                    timestamp=event.timestamp,
                )
            )
            await session.commit()
    except Exception:
        logger.warning(
            "analytics: failed to persist %s", event.event_type, exc_info=True
        )


async def flush_pending(timeout: float = 5.0) -> None:
    """Wait for in-flight writes to finish. Useful at shutdown."""
    if not _pending:
        return
    await asyncio.wait(list(_pending), timeout=timeout)


# -- Reporting helpers (used by stats CLI) ---------------------------------


async def count_by_type(
    db: AsyncSession,
    since: datetime | None = None,
    event_types: Iterable[str] | None = None,
) -> dict[str, int]:
    """Total events grouped by event_type (optionally since a cutoff)."""
    from sqlalchemy import func, select

    stmt = select(Event.event_type, func.count()).group_by(Event.event_type)
    if since is not None:
        stmt = stmt.where(Event.timestamp >= since)
    if event_types is not None:
        stmt = stmt.where(Event.event_type.in_(list(event_types)))
    rows = (await db.execute(stmt)).all()
    return {row[0]: int(row[1]) for row in rows}


async def button_tap_leaderboard(
    db: AsyncSession, since: datetime | None = None, limit: int = 10
) -> list[tuple[str, int]]:
    """Most-tapped buttons in the `button_tapped` stream."""
    from sqlalchemy import func, select

    button_key = Event.properties["button"].astext
    stmt = (
        select(button_key.label("button"), func.count().label("count"))
        .where(Event.event_type == EventType.BUTTON_TAPPED)
        .group_by(button_key)
        .order_by(func.count().desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(Event.timestamp >= since)
    rows = (await db.execute(stmt)).all()
    return [(row.button or "(unknown)", int(row.count)) for row in rows]


async def miniapp_load_time_percentiles(
    db: AsyncSession, since: datetime | None = None
) -> dict[str, float]:
    """p50/p95/p99 of `load_time_ms` on `miniapp_loaded` events."""
    from sqlalchemy import func, select

    load_time = func.cast(Event.properties["load_time_ms"].astext, types_.Float)
    stmt = select(
        func.percentile_cont(0.50).within_group(load_time).label("p50"),
        func.percentile_cont(0.95).within_group(load_time).label("p95"),
        func.percentile_cont(0.99).within_group(load_time).label("p99"),
    ).where(
        Event.event_type == EventType.MINIAPP_LOADED,
        Event.properties["load_time_ms"].isnot(None),
    )
    if since is not None:
        stmt = stmt.where(Event.timestamp >= since)
    row = (await db.execute(stmt)).one_or_none()
    if not row or row.p50 is None:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    return {"p50": float(row.p50), "p95": float(row.p95), "p99": float(row.p99)}


# -- Morning briefing funnel queries (used by stats CLI / dashboards) -----


# Window inside which a button tap counts as "opened the briefing" — past
# this we assume the user opened it for some unrelated reason. 30 min
# matches the median time-to-open observed in the milestone-celebration
# stream so it covers commute-and-coffee paths without diluting the
# signal.
BRIEFING_OPEN_WINDOW_SECONDS = 30 * 60


async def briefing_open_rate(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    level: str | None = None,
) -> dict[str, float | int]:
    """Daily open rate = ``opened / sent`` for morning briefings.

    A briefing counts as "opened" when an ``OPENED`` event is logged
    within ``BRIEFING_OPEN_WINDOW_SECONDS`` of the corresponding ``SENT``
    event for the same user. Falls back gracefully if no briefings have
    been sent in the window — returns ``rate=0.0`` so dashboards
    don't divide by zero.
    """
    from sqlalchemy import func, select

    sent_q = select(func.count()).where(
        Event.event_type == EventType.MORNING_BRIEFING_SENT
    )
    opened_q = select(func.count()).where(
        Event.event_type == EventType.MORNING_BRIEFING_OPENED
    )
    if since is not None:
        sent_q = sent_q.where(Event.timestamp >= since)
        opened_q = opened_q.where(Event.timestamp >= since)
    if level is not None:
        # ``properties->>'level' = :level`` — level is recorded as a
        # property on every SENT event so we can break down without
        # joining users.
        sent_q = sent_q.where(Event.properties["level"].astext == level)
        opened_q = opened_q.where(Event.properties["level"].astext == level)

    sent = int((await db.execute(sent_q)).scalar() or 0)
    opened = int((await db.execute(opened_q)).scalar() or 0)
    rate = (opened / sent) if sent > 0 else 0.0
    return {"sent": sent, "opened": opened, "rate": round(rate, 4)}


async def briefing_open_rate_by_level(
    db: AsyncSession, *, since: datetime | None = None,
) -> dict[str, dict[str, float | int]]:
    """Per-level open-rate breakdown — one entry per wealth level seen
    in the window. Levels with zero sends are omitted to keep the
    dashboard tidy.
    """
    from sqlalchemy import func, select

    level_key = Event.properties["level"].astext
    stmt = (
        select(
            level_key.label("level"),
            Event.event_type,
            func.count().label("count"),
        )
        .where(
            Event.event_type.in_([
                EventType.MORNING_BRIEFING_SENT,
                EventType.MORNING_BRIEFING_OPENED,
            ])
        )
        .group_by(level_key, Event.event_type)
    )
    if since is not None:
        stmt = stmt.where(Event.timestamp >= since)

    rows = (await db.execute(stmt)).all()
    out: dict[str, dict[str, int]] = {}
    for level, event_type, count in rows:
        bucket = out.setdefault(
            level or "unknown", {"sent": 0, "opened": 0}
        )
        if event_type == EventType.MORNING_BRIEFING_SENT:
            bucket["sent"] = int(count)
        else:
            bucket["opened"] = int(count)

    return {
        level: {
            **bucket,
            "rate": round(
                (bucket["opened"] / bucket["sent"])
                if bucket["sent"] > 0 else 0.0,
                4,
            ),
        }
        for level, bucket in out.items()
    }


async def briefing_avg_time_to_open(
    db: AsyncSession, *, since: datetime | None = None,
) -> float | None:
    """Mean seconds between briefing send and first user tap.

    Returns ``None`` if no opens have been recorded — the caller
    decides how to surface "no data yet" (the stats CLI prints
    ``--`` rather than ``0`` to avoid the misleading "instant" read).

    Implementation: per (user_id, send_time) pair, find the first
    open event whose timestamp is in
    ``[send_time, send_time + window]`` and average the deltas. Done
    in Python rather than SQL because Postgres LATERAL joins on a
    JSON-typed events table are noisy to read for a marginal speed
    gain at this scale.
    """
    from sqlalchemy import select

    sent_stmt = (
        select(Event.user_id, Event.timestamp)
        .where(Event.event_type == EventType.MORNING_BRIEFING_SENT)
        .order_by(Event.timestamp)
    )
    opened_stmt = (
        select(Event.user_id, Event.timestamp)
        .where(Event.event_type == EventType.MORNING_BRIEFING_OPENED)
        .order_by(Event.timestamp)
    )
    if since is not None:
        sent_stmt = sent_stmt.where(Event.timestamp >= since)
        opened_stmt = opened_stmt.where(Event.timestamp >= since)

    sent_rows = (await db.execute(sent_stmt)).all()
    opened_rows = (await db.execute(opened_stmt)).all()
    if not sent_rows or not opened_rows:
        return None

    # Group opens by user; each list stays sorted by timestamp.
    opens_by_user: dict[uuid.UUID, list[datetime]] = {}
    for uid, ts in opened_rows:
        if uid is None:
            continue
        opens_by_user.setdefault(uid, []).append(ts)

    deltas: list[float] = []
    for uid, sent_at in sent_rows:
        if uid is None:
            continue
        candidates = opens_by_user.get(uid, [])
        for opened_at in candidates:
            if opened_at < sent_at:
                continue
            delta = (opened_at - sent_at).total_seconds()
            if delta <= BRIEFING_OPEN_WINDOW_SECONDS:
                deltas.append(delta)
            break  # Only the first qualifying open counts.

    if not deltas:
        return None
    return round(sum(deltas) / len(deltas), 1)


# Typed import alias — SQLAlchemy `types` sub-module; placed at module bottom
# so the top stays focused on the public API.
from sqlalchemy import types as types_  # noqa: E402  (intentional trailing import)
