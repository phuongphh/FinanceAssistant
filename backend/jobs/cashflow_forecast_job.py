"""Phase 4B S16 + S17 — Daily cashflow forecast + alert job.

Schedule: daily 01:00 Asia/Ho_Chi_Minh.

Per-user pipeline:
1. Load confirmed patterns. Skip if < 2 (unreliable forecast).
2. Compute and persist 3-month ``CashflowForecast``.
3. Commit forecast.
4. Check and send alert if low_balance_risk (S17 Redis-deduped).

Running at 01:00 (quiet window, after daily_snapshot_job at 23:59)
ensures the morning briefing at 07:00 always reads a fresh forecast
without triggering an on-demand recompute.

Layer contract:
- Job owns the session and commit boundary.
- forecast.compute_and_persist_forecast flushes only.
- alert.check_and_send_alert uses get_notifier() port, never commits.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from backend.database import get_session_factory
from backend.models.user import User

logger = logging.getLogger(__name__)

INTER_USER_SLEEP = 1.0
MIN_HISTORY_DAYS = 90


async def run_cashflow_forecast_job() -> None:
    """Entry point for APScheduler registration."""
    from backend.cashflow.forecast import compute_and_persist_forecast
    from backend.cashflow.alert import check_and_send_alert
    from backend.cashflow.detector import load_confirmed_patterns

    session_factory = get_session_factory()
    async with session_factory() as db:
        users = await _eligible_users(db)

    logger.info("cashflow forecast: %d eligible users", len(users))
    sent_alerts = 0
    errors = 0

    for user in users:
        async with session_factory() as db:
            try:
                confirmed = await load_confirmed_patterns(db, user.id)
                if len(confirmed) < 2:
                    continue

                await compute_and_persist_forecast(db, user)
                await db.commit()

                alerted = await check_and_send_alert(db, user, confirmed)
                if alerted:
                    sent_alerts += 1

            except ValueError:
                pass   # < 2 confirmed patterns — expected, not an error
            except Exception:
                errors += 1
                logger.exception(
                    "cashflow forecast failed for user %s", user.id
                )

        await asyncio.sleep(INTER_USER_SLEEP)

    logger.info(
        "cashflow forecast: done — alerts_sent=%d errors=%d",
        sent_alerts, errors,
    )


async def _eligible_users(db) -> list[User]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_HISTORY_DAYS)
    stmt = select(User).where(
        and_(
            User.created_at <= cutoff,
            User.deleted_at.is_(None),
            User.telegram_id.isnot(None),
            User.is_active.is_(True),
        )
    )
    return list((await db.execute(stmt)).scalars().all())
