"""FastAPI routes for the Telegram Mini App.

- `GET /miniapp/dashboard` — static HTML page (auth checked in JS/API layer)
- `GET /miniapp/api/overview` — aggregated monthly spending data
- `GET /miniapp/api/recent-transactions` — latest N transactions
- `GET /miniapp/static/*` — CSS/JS assets
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.miniapp.auth import require_miniapp_auth
from backend.services import dashboard_service

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

router = APIRouter(prefix="/miniapp", tags=["miniapp"])

# Static assets — CSS + JS
if _STATIC_DIR.exists():
    router.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="miniapp-static",
    )


@router.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    """Serve the dashboard HTML. Auth happens in the API layer (per-request)."""
    html_path = _TEMPLATES_DIR / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard page missing")
    return FileResponse(html_path, media_type="text/html; charset=utf-8")


async def _resolve_user(
    auth: dict, db: AsyncSession
):
    telegram_id = auth.get("user_id")
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Missing Telegram user id")
    user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not registered")
    return user


@router.get("/api/overview")
async def get_overview(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    trend_days: int = Query(30, ge=7, le=90),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Monthly total, transaction count, category breakdown, daily trend."""
    user = await _resolve_user(auth, db)
    month_key = month or dashboard_service.current_month_key()

    total_spent = await dashboard_service.get_month_total(db, user.id, month_key)
    transaction_count = await dashboard_service.get_month_transaction_count(
        db, user.id, month_key
    )
    top_categories = await dashboard_service.get_category_breakdown(
        db, user.id, month_key
    )
    daily_trend = await dashboard_service.get_daily_trend(db, user.id, days=trend_days)

    return {
        "data": {
            "month": month_key,
            "total_spent": total_spent,
            "transaction_count": transaction_count,
            "top_categories": top_categories,
            "daily_trend": daily_trend,
        },
        "error": None,
    }


@router.get("/api/recent-transactions")
async def get_recent(
    limit: int = Query(20, ge=1, le=100),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    user = await _resolve_user(auth, db)
    items = await dashboard_service.get_recent_transactions(db, user.id, limit=limit)
    return {"data": items, "error": None}
