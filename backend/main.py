import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.miniapp import routes as miniapp_routes
from backend.routers import expenses, goals, income, ingestion, market, portfolio, reports, telegram
from backend.scheduler import register_jobs
from backend.workers.telegram_worker import recover_orphaned_updates, run_recovery_loop

logger = logging.getLogger(__name__)
settings = get_settings()

# Seconds we wait for in-flight background tasks (Telegram update
# processing) to finish during a graceful shutdown. Longer than a typical
# LLM call, short enough to not stall a deploy. Any task still running
# after this is abandoned; the row stays in ``processing`` and the next
# startup picks it up as an orphan.
SHUTDOWN_TASK_GRACE_SECONDS = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Embed the scheduler in the app process so there is no separate
    # process to keep alive. Run uvicorn with a single worker (--workers 1)
    # to avoid duplicate cron fires; Phase 1 will move to Celery workers.
    scheduler = AsyncIOScheduler()
    register_jobs(scheduler)
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    logger.info("Finance Assistant API starting up")

    # Pick up any telegram_updates that were mid-flight when the previous
    # process died. See docs/strategy/scaling-refactor-A.md §A1.
    try:
        recovered = await recover_orphaned_updates()
        if recovered:
            logger.info("Re-enqueued %d orphaned Telegram updates", recovered)
    except Exception:
        # Startup must never fail because of recovery — the queue is
        # advisory and a human can replay from the telegram_updates table.
        logger.exception("Orphan recovery failed at startup; continuing")

    # Run recovery on a timer too, not just at boot — a fast restart loop
    # would otherwise leave rows stuck until the next deploy (the 5-min
    # cutoff keeps excluding them). Atomic claim inside the loop means
    # multiple uvicorn workers are safe to run it concurrently.
    recovery_task = asyncio.create_task(run_recovery_loop())

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        recovery_task.cancel()
        try:
            await recovery_task
        except asyncio.CancelledError:
            pass

    # Graceful shutdown: give in-flight background tasks a bounded window
    # to finish so we don't leave updates half-processed when uvicorn
    # receives SIGTERM during a deploy.
    pending = [
        t for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and not t.done()
    ]
    if pending:
        logger.info(
            "Waiting up to %ds for %d background task(s) to finish",
            SHUTDOWN_TASK_GRACE_SECONDS, len(pending),
        )
        done, still_pending = await asyncio.wait(
            pending, timeout=SHUTDOWN_TASK_GRACE_SECONDS
        )
        if still_pending:
            logger.warning(
                "%d background task(s) did not finish within grace period — "
                "their telegram_updates rows will be recovered on next startup",
                len(still_pending),
            )

    logger.info("Finance Assistant API shutting down")


app = FastAPI(
    title="Finance Assistant API",
    description="Personal finance AI assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(expenses.router, prefix="/api/v1")
app.include_router(goals.router, prefix="/api/v1")
app.include_router(goals.income_router, prefix="/api/v1")
app.include_router(ingestion.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(income.router, prefix="/api/v1")
app.include_router(telegram.router, prefix="/api/v1")
app.include_router(miniapp_routes.router)  # No /api/v1 prefix — Mini App URL is public


@app.get("/health")
async def health_check():
    return JSONResponse(
        content={"data": {"status": "healthy"}, "error": None}
    )
