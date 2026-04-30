"""Standalone scheduler process — runs APScheduler outside the web server.

Run with: python -m backend.scheduler

Split from the FastAPI app so starting multiple uvicorn workers (or
accidentally leaving an old instance running) does not register the
same cron jobs multiple times. Phase 1 will replace this with Celery
workers; until then this single-process runner is the source of truth
for scheduled jobs.
"""
import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.jobs.check_empathy_triggers import run_hourly_empathy_check
from backend.jobs.check_milestones import run_daily_milestone_check
from backend.jobs.daily_snapshot_job import create_daily_snapshots
from backend.jobs.market_poller import poll_market
from backend.jobs.monthly_report import generate_all_monthly_reports
from backend.jobs.morning_briefing_job import run_morning_briefing_job
from backend.jobs.seasonal_notifier import run_seasonal_check
from backend.jobs.weekly_fun_facts import run_weekly_fun_facts
from backend.jobs.weekly_goal_reminder import run_weekly_goal_reminder

logger = logging.getLogger(__name__)


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(poll_market, "cron", hour=8, minute=0, id="market_snapshot")
    scheduler.add_job(
        generate_all_monthly_reports, "cron",
        day=1, hour=9, minute=0, id="monthly_report",
    )
    scheduler.add_job(
        run_daily_milestone_check, "cron",
        hour=8, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="milestone_check",
    )
    # Phase 2 — Empathy Engine (Issue #40).
    # Runs hourly; the job itself bails out during quiet hours (22-07)
    # so we don't need to list each allowed hour here — keeps the
    # config close to the behaviour it enforces.
    scheduler.add_job(
        run_hourly_empathy_check, "cron",
        minute=5, timezone="Asia/Ho_Chi_Minh",
        id="empathy_check",
    )
    # Phase 2 — Seasonal notifier (Issue #43). 08:00 every day.
    scheduler.add_job(
        run_seasonal_check, "cron",
        hour=8, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="seasonal_notifier",
    )
    # Phase 2 — Weekly fun facts (Issue #42). Sunday 19:00.
    scheduler.add_job(
        run_weekly_fun_facts, "cron",
        day_of_week="sun", hour=19, minute=0,
        timezone="Asia/Ho_Chi_Minh",
        id="weekly_fun_facts",
    )
    # Phase 2 — Weekly goal reminder (Issue #44). Monday 08:30.
    scheduler.add_job(
        run_weekly_goal_reminder, "cron",
        day_of_week="mon", hour=8, minute=30,
        timezone="Asia/Ho_Chi_Minh",
        id="weekly_goal_reminder",
    )
    # Phase 3A — Morning briefing (Issue #70). Runs every 15 min so
    # users with custom briefing_time (06:30, 08:15, ...) all get a
    # window. The job itself filters to users whose target time falls
    # in the next 15 minutes and dedups by event log.
    scheduler.add_job(
        run_morning_briefing_job, "interval",
        minutes=15, timezone="Asia/Ho_Chi_Minh",
        id="morning_briefing",
    )
    # Phase 3A — Daily asset snapshot (Issue #71). 23:59 every day so
    # tomorrow's morning briefing has a yesterday-baseline to compare
    # against. ``ON CONFLICT DO NOTHING`` in the job makes it safe
    # against scheduler retries.
    scheduler.add_job(
        create_daily_snapshots, "cron",
        hour=23, minute=59, timezone="Asia/Ho_Chi_Minh",
        id="daily_asset_snapshot",
    )


async def _run() -> None:
    scheduler = AsyncIOScheduler()
    register_jobs(scheduler)
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    scheduler.shutdown()
    logger.info("Scheduler shutdown complete")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
