"""FastAPI routes for the Telegram Mini App.

- `GET /miniapp/dashboard` — legacy expense dashboard (Phase 1)
- `GET /miniapp/wealth` — Phase 3A wealth dashboard (HTML)
- `GET /miniapp/api/overview` — aggregated monthly spending data
- `GET /miniapp/api/recent-transactions` — latest N transactions
- `GET /miniapp/api/wealth/overview` — net worth + breakdown + trend + assets
- `GET /miniapp/api/wealth/trend?days=30|90|365` — net worth time series
- `GET /miniapp/static/*` — CSS/JS assets
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.database import get_db
from backend.miniapp.auth import require_miniapp_auth
from backend.services import dashboard_service, wealth_dashboard_service

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

router = APIRouter(prefix="/miniapp", tags=["miniapp"])

# Per-process in-memory cache for wealth payloads. The dashboard hits the
# overview + trend pair on every open and the same user usually reloads in
# bursts (briefing tap, then a refresh) — 30 seconds is short enough not
# to surprise users who just edited an asset, long enough to absorb the
# burst. Keyed by ``(user_id, kind, days)`` so each user has their own row
# and trend windows don't collide.
_WEALTH_CACHE_TTL_SECONDS = 30.0
_wealth_cache: dict[tuple, tuple[float, dict | list]] = {}


def _cache_get(key: tuple) -> dict | list | None:
    entry = _wealth_cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        _wealth_cache.pop(key, None)
        return None
    return value


def _cache_set(key: tuple, value: dict | list) -> None:
    _wealth_cache[key] = (time.monotonic() + _WEALTH_CACHE_TTL_SECONDS, value)


def _wealth_cache_clear() -> None:
    """Test hook — drops all cached wealth payloads."""
    _wealth_cache.clear()


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
    page = payload.get("page") if isinstance(payload, dict) else None
    try:
        load_time_ms = float(load_time_ms) if load_time_ms is not None else None
    except (TypeError, ValueError):
        load_time_ms = None

    props: dict = {}
    if load_time_ms is not None:
        props["load_time_ms"] = load_time_ms
    if isinstance(page, str) and page:
        # Sanity-clamp the page name — analytics PII filter strips long
        # values, but we also enforce a tiny allowlist-shape here.
        props["page"] = page[:32]

    analytics.track(
        analytics.EventType.MINIAPP_LOADED,
        user_id=user.id,
        properties=props,
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


# --- Phase 3A — Wealth dashboard (Mini App) -----------------------------


@router.get("/wealth", include_in_schema=False)
async def wealth_page():
    """Serve the wealth dashboard HTML.

    Auth happens in the API layer per-request (the page itself is static).
    The ``MINIAPP_OPENED`` event here is anonymous (no user_id) because
    initData hasn't been verified yet — the JS sends an authenticated
    ``WEALTH_DASHBOARD_VIEWED`` event once the API call succeeds.
    """
    html_path = _TEMPLATES_DIR / "wealth_dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Wealth dashboard page missing")
    analytics.track(
        analytics.EventType.MINIAPP_OPENED,
        properties={"page": "wealth"},
    )
    return FileResponse(html_path, media_type="text/html; charset=utf-8")


@router.get("/api/wealth/overview")
async def get_wealth_overview(
    source: str | None = Query(
        None,
        max_length=32,
        pattern=r"^[a-z_]{1,32}$",
        description="Where the open came from: briefing|menu|deep_link",
    ),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Net worth + breakdown + 90-day trend + assets, all in one payload.

    Cached 30s per user (in-process). Errors degrade to 500 with a friendly
    message — Mini App JS shows a retry button rather than crashing.
    """
    user = await _resolve_user(auth, db)
    cache_key = (user.id, "overview")
    cached = _cache_get(cache_key)
    if cached is not None:
        payload = cached
    else:
        try:
            payload = await wealth_dashboard_service.build_overview(
                db, user.id, trend_days=90
            )
        except Exception as exc:  # noqa: BLE001 — surface friendly error
            raise HTTPException(
                status_code=500,
                detail="Không tải được dữ liệu tài sản, thử lại nhé.",
            ) from exc
        _cache_set(cache_key, payload)

    analytics.track(
        analytics.EventType.WEALTH_DASHBOARD_VIEWED,
        user_id=user.id,
        properties={
            "from": source or "unknown",
            "level": payload.get("level"),
            "asset_count": payload.get("asset_count", 0),
        },
    )

    return {"data": payload, "error": None}


@router.post("/api/wealth/start-asset-wizard")
async def start_asset_wizard_route(
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Trigger the asset-add wizard from the Mini App "+ Thêm tài sản" button.

    Posts the type-picker message into the user's private chat with the
    bot, so when the WebApp closes the user lands on a chat that is
    already mid-flow. Private-chat ``chat_id`` equals ``telegram_id``.
    """
    user = await _resolve_user(auth, db)
    # Lazy import — asset_entry pulls in the wizard graph; keep the
    # miniapp module light and avoid any chance of a circular import
    # at process start.
    from backend.bot.handlers.asset_entry import start_asset_wizard

    await start_asset_wizard(db, user.telegram_id, user)
    return {"data": {"ok": True}, "error": None}


@router.get("/api/wealth/trend")
async def get_wealth_trend(
    days: int = Query(
        90,
        description="Trend window in days; one of 30, 90, 365",
    ),
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Historical net worth as ``[{date, value}]`` for the period selector."""
    if days not in wealth_dashboard_service.TREND_DAYS_ALLOWED:
        raise HTTPException(
            status_code=422,
            detail=f"days must be one of {list(wealth_dashboard_service.TREND_DAYS_ALLOWED)}",
        )

    user = await _resolve_user(auth, db)
    cache_key = (user.id, "trend", days)
    cached = _cache_get(cache_key)
    if cached is not None:
        trend = cached
    else:
        try:
            trend = await wealth_dashboard_service.get_trend(
                db, user.id, days=days
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail="Không tải được dữ liệu xu hướng, thử lại nhé.",
            ) from exc
        _cache_set(cache_key, trend)

    analytics.track(
        analytics.EventType.WEALTH_TREND_VIEWED,
        user_id=user.id,
        properties={"days": days},
    )

    return {"data": trend, "error": None}
