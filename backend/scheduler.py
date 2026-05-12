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

from backend.jobs.cashflow_detection_job import run_cashflow_detection
from backend.jobs.cashflow_forecast_job import run_cashflow_forecast_job
from backend.jobs.daily_kpi_digest_job import run_daily_kpi_digest_job
from backend.jobs.feedback_sla_job import run_feedback_sla_job
from backend.jobs.check_empathy_triggers import run_hourly_empathy_check
from backend.jobs.check_milestones import run_daily_milestone_check
from backend.jobs.daily_snapshot_job import create_daily_snapshots
from backend.jobs.market_poller import poll_market
from backend.jobs.monthly_report import generate_all_monthly_reports
from backend.jobs.morning_briefing_job import run_morning_briefing_job
from backend.jobs.onboarding_resume_job import run_onboarding_resume_job
from backend.jobs.recurring_detection_job import run_recurring_detection
from backend.jobs.reminder_scheduler_job import run_reminder_scheduler
from backend.jobs.seasonal_notifier import run_seasonal_check
from backend.jobs.weekly_fun_facts import run_weekly_fun_facts
from backend.jobs.weekly_goal_reminder import run_weekly_goal_reminder
from backend.market_data.jobs.bank_rates_updater import update_bank_rates
from backend.market_data.jobs.crypto_updater import update_all_held_crypto
from backend.market_data.jobs.gold_updater import update_all_held_gold
from backend.market_data.jobs.historical_price_seeder import seed_year_start_stock_prices
from backend.market_data.jobs.news_updater import update_news_articles
from backend.market_data.jobs.stock_updater import update_all_held_stocks
from backend.twin.schedulers.weekly_twin_updater import run_weekly_twin_update

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
    # Phase 3.8 Epic 3 — recurring-pattern auto-detection. Runs at
    # 02:00 (low-activity window so the Telegram delivery doesn't
    # compete with morning briefings) once a day.
    scheduler.add_job(
        run_recurring_detection, "cron",
        hour=2, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="recurring_detection",
    )
    # Phase 3.8 Epic 3 + Phase 3.8.5 profile settings — run every
    # 15 minutes so each user's custom reminder_time can be respected.
    # The job itself filters by user_profiles.reminder_enabled/time.
    scheduler.add_job(
        run_reminder_scheduler, "interval",
        minutes=15, timezone="Asia/Ho_Chi_Minh",
        id="recurring_reminders",
    )
    # Phase 3.9 Epic 2 — pre-warm real market data cache.
    scheduler.add_job(
        update_all_held_stocks, "cron",
        minute="*/15", hour="9-15", day_of_week="mon-fri",
        timezone="Asia/Ho_Chi_Minh",
        id="stock_price_updater",
    )
    scheduler.add_job(
        update_all_held_crypto, "interval",
        minutes=5, timezone="Asia/Ho_Chi_Minh",
        id="crypto_price_updater",
    )
    # Phase 3.9 Epic 3 — gold, bank rates, and market news.
    scheduler.add_job(
        update_all_held_gold, "cron",
        hour="9,13,16", minute=0, timezone="Asia/Ho_Chi_Minh",
        id="gold_price_updater",
    )
    scheduler.add_job(
        update_bank_rates, "cron",
        day_of_week="mon", hour=6, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="bank_rates_updater",
    )
    scheduler.add_job(
        update_news_articles, "cron",
        minute=0, timezone="Asia/Ho_Chi_Minh",
        id="news_updater",
    )
    scheduler.add_job(
        seed_year_start_stock_prices, "cron",
        month=1, day=1, hour=7, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="historical_price_seeder",
    )

    # Phase 4A — Financial Twin projections. Heavy Monte Carlo work runs weekly
    # outside request paths; read surfaces consume the latest stored cone.
    scheduler.add_job(
        run_weekly_twin_update, "cron",
        day_of_week="sun", hour=23, minute=0,
        timezone="Asia/Ho_Chi_Minh",
        id="weekly_twin_update",
    )

    # Phase 4.1 Story A.6 — Daily KPI digest. 08:00 ICT every morning;
    # operator gets ONE message gathering cost + engagement + quality +
    # churn + feedback queue (Story A.4 cost report merges in here).
    scheduler.add_job(
        run_daily_kpi_digest_job, "cron",
        hour=8, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="daily_kpi_digest",
    )
    # Phase 4.1 Story A.7 — Feedback SLA alert. Every hour, alert
    # operator about feedback open > 24h (once per feedback).
    scheduler.add_job(
        run_feedback_sla_job, "interval",
        minutes=60, timezone="Asia/Ho_Chi_Minh",
        id="feedback_sla_alert",
    )

    # Phase 4.1 Story A.2 — Onboarding resume nudge. Every 5 minutes:
    # finds users stuck >10 minutes mid-onboarding (per-user nudge cap
    # is enforced in the service, NOT here).
    scheduler.add_job(
        run_onboarding_resume_job, "interval",
        minutes=5, timezone="Asia/Ho_Chi_Minh",
        id="onboarding_resume_nudge",
    )

    # Phase 4B Epic 3 — Cashflow Forecasting v2.
    # Detection runs weekly (Monday 06:00) so users see pattern suggestions
    # at the start of the work week. Forecast runs daily (01:00) so the
    # morning briefing always has a fresh 3-month projection.
    scheduler.add_job(
        run_cashflow_detection, "cron",
        day_of_week="mon", hour=6, minute=0,
        timezone="Asia/Ho_Chi_Minh",
        id="cashflow_pattern_detection",
    )
    scheduler.add_job(
        run_cashflow_forecast_job, "cron",
        hour=1, minute=0,
        timezone="Asia/Ho_Chi_Minh",
        id="cashflow_forecast",
    )


async def _run() -> None:
    # Phase 4.1 Story A.5 — Sentry covers scheduler process too so
    # cron-only failures land in the same dashboard as web errors.
    try:
        from backend.adapters.observability import sentry_adapter

        sentry_adapter.init()
    except Exception:
        logger.exception("Sentry init failed in scheduler; continuing")

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
