import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.routers import expenses, goals, income, ingestion, market, portfolio, reports, telegram

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Finance Assistant API starting up")

    # Setup scheduled jobs
    from backend.jobs.gmail_poller import poll_gmail
    from backend.jobs.market_poller import poll_market
    from backend.jobs.monthly_report import generate_all_monthly_reports
    from backend.jobs.morning_report_job import send_all_morning_reports

    scheduler.add_job(poll_gmail, "cron", minute="*/30", id="gmail_sync")
    scheduler.add_job(poll_market, "cron", hour=8, minute=0, id="market_snapshot")
    scheduler.add_job(generate_all_monthly_reports, "cron", day=1, hour=9, minute=0, id="monthly_report")
    scheduler.add_job(
        send_all_morning_reports, "cron",
        hour=7, minute=0, timezone="Asia/Ho_Chi_Minh",
        id="morning_report",
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    yield

    scheduler.shutdown()
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


@app.get("/health")
async def health_check():
    return JSONResponse(
        content={"data": {"status": "healthy"}, "error": None}
    )
