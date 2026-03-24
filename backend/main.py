import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.routers import expenses, goals

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/health")
async def health_check():
    return JSONResponse(
        content={"data": {"status": "healthy"}, "error": None}
    )
