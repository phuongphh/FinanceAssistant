import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.miniapp import routes as miniapp_routes
from backend.routers import expenses, goals, income, ingestion, market, portfolio, reports, telegram

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Scheduled jobs run in a separate process — see backend/scheduler.py.
    # Keeping them out of the web server prevents duplicate cron fires when
    # more than one uvicorn worker is running.
    logger.info("Finance Assistant API starting up")
    yield
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
