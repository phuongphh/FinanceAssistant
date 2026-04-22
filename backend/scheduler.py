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

from backend.jobs.check_milestones import run_daily_milestone_check
from backend.jobs.gmail_poller import poll_gmail
from backend.jobs.market_poller import poll_market
from backend.jobs.monthly_report import generate_all_monthly_reports
from backend.jobs.morning_report_job import send_all_morning_reports

logger = logging.getLogger(__name__)


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(poll_gmail, "cron", minute="*/30", id="gmail_sync")
    scheduler.add_job(poll_market, "cron", hour=8, minute=0, id="market_snapshot")
    scheduler.add_job(
        generate_all_monthly_reports, "cron",
        day=1, hour=9, minute=0, id="monthly_report",
    )
    scheduler.add_job(
        send_all_morning_reports, "cron",
        hour=7, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="morning_report",
    )
    scheduler.add_job(
        run_daily_milestone_check, "cron",
        hour=8, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="milestone_check",
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
