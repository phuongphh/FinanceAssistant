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
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.database import get_db
from backend.miniapp.auth import require_miniapp_auth
from backend.services import dashboard_service

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

router = APIRouter(prefix="/miniapp", tags=["miniapp"])


@router.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    """Serve the dashboard HTML. Auth happens in the API layer (per-request)."""
    html_path = _TEMPLATES_DIR / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard page missing")
    # `miniapp_opened` here fires before the JS verifies user via initData, so
    # we don't have a user_id yet — the per-user dimension arrives via the
    # `miniapp_loaded` beacon once the dashboard finishes loading.
    analytics.track(analytics.EventType.MINIAPP_OPENED)
    return FileResponse(html_path, media_type="text/html; charset=utf-8")


@router.post("/api/events/loaded")
async def record_loaded(
    payload: dict,
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Beacon from dashboard.js after first render. Records perf + user."""
    user = await _resolve_user(auth, db)
    load_time_ms = payload.get("load_time_ms") if isinstance(payload, dict) else None
    try:
        load_time_ms = float(load_time_ms) if load_time_ms is not None else None
    except (TypeError, ValueError):
        load_time_ms = None

    analytics.track(
        analytics.EventType.MINIAPP_LOADED,
        user_id=user.id,
        properties={"load_time_ms": load_time_ms} if load_time_ms is not None else {},
    )
    return {"data": {"ok": True}, "error": None}


async def _resolve_user(
    auth: dict, db: AsyncSession
):
    telegram_id = auth.get("user_id")
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Missing Telegram user id")
    # Safety net: user should already exist from /start, but create if missing.
    user, _ = await dashboard_service.get_or_create_user(
        db,
        telegram_id,
        first_name=auth.get("first_name"),
        last_name=auth.get("last_name"),
        username=auth.get("username"),
    )
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
