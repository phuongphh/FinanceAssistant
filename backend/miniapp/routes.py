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

import hashlib
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.config import get_settings
from backend.database import get_db
from backend.miniapp.auth import require_miniapp_auth
from backend.services import (
    dashboard_service,
    intent_metrics,
    wealth_dashboard_service,
)

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

# --- Static-asset cache busting ----------------------------------------
#
# Telegram's WebView caches /miniapp/static/css/*.css and /miniapp/static/js/*.js
# very aggressively — re-opening the Mini App after a deploy still serves the
# previous CSS/JS until cache eviction (often hours). Without cache busting,
# a freshly-deployed UI change is invisible to users who already opened the
# WebApp once. We compute a content hash over every referenced static asset
# at process start and append it as ``?v=<hash>`` to every ``/miniapp/static/``
# URL inside the HTML. The hash changes the moment any CSS/JS byte changes,
# so the WebView treats it as a new resource and bypasses its cache. The HTML
# itself is served with ``Cache-Control: no-cache`` so the WebView always
# re-fetches the document (cheap — a few KB) and picks up the new version
# string after every deploy.

_STATIC_REF_FILES = (
    "css/style.css",
    "css/wealth.css",
    "js/dashboard.js",
    "js/wealth_dashboard.js",
)
_STATIC_URL_PATTERN = re.compile(r'(/miniapp/static/[^"\'?#\s]+)')
_VERSION_MARKER_PATTERN = re.compile(r"<!--\s*APP_VERSION_MARKER\s*-->")
_BOOTSTRAP_MARKER_PATTERN = re.compile(r"<!--\s*BUILD_BOOTSTRAP\s*-->")


def _build_bootstrap_script(version: str) -> str:
    """Inline reload guard that runs before any other asset loads.

    Telegram WebView (especially iOS WebKit) often ignores ``Cache-Control:
    no-cache`` on HTML and serves a previously-cached document without
    revalidating. When that happens, the cached HTML still references the
    old (un-versioned or stale-versioned) JS, so the cache-busting query
    string never reaches the WebView at all and a UI fix can stay invisible
    for hours/days.

    This bootstrap closes that loop *for every subsequent deploy*: the
    moment the WebView ever does fetch a fresh HTML (whether through normal
    revalidation, a Telegram cache wipe, or a network change), the script
    sees that the build hash on disk doesn't match the one stored in
    ``localStorage`` from the previous session and triggers a
    ``location.replace`` with a unique ``?_b=<hash>`` query string. That
    URL is genuinely new from the WebView's POV, so it bypasses every
    cache layer (HTML and assets) on the next request and the user lands
    on the freshly-rendered dashboard.

    Idempotent: after a successful refresh, ``localStorage`` matches the
    current hash so the script no-ops on every subsequent open. First-time
    visitors (no stored hash) only seed the value — no reload — so cold
    opens are not slowed down. ``try/catch`` guards against
    ``localStorage`` throwing in private mode / sandboxed iframes.
    """
    return (
        "<script>"
        "(function(){"
        f"var CURRENT={version!r};"
        "try{"
        "var KEY='fa.app.build';"
        "var stored=localStorage.getItem(KEY);"
        "if(stored&&stored!==CURRENT){"
        "localStorage.setItem(KEY,CURRENT);"
        "var url=new URL(location.href);"
        "url.searchParams.set('_b',CURRENT);"
        "location.replace(url.toString());"
        "return;"
        "}"
        "if(!stored)localStorage.setItem(KEY,CURRENT);"
        "}catch(e){}"
        "})();"
        "</script>"
    )


def _compute_static_version() -> str:
    hasher = hashlib.sha256()
    for rel_path in _STATIC_REF_FILES:
        asset = _STATIC_DIR / rel_path
        if asset.exists():
            hasher.update(asset.read_bytes())
    return hasher.hexdigest()[:10]


def _detect_git_sha() -> str:
    """Best-effort short SHA of the running build.

    Reads ``.git/HEAD`` directly so we don't require a ``git`` binary inside
    the runtime container. Returns ``"unknown"`` when the repo metadata is
    unavailable (e.g. minimal Docker images that strip ``.git``). The result
    is exposed via ``/miniapp/api/version`` and rendered into the dashboard
    footer so a quick glance tells you which commit the VPS is actually
    running — invaluable when debugging "I pushed but nothing changed".
    """
    repo_root = Path(__file__).resolve().parents[2]
    head_file = repo_root / ".git" / "HEAD"
    try:
        if not head_file.exists():
            return "unknown"
        head = head_file.read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref_path = repo_root / ".git" / head.split(maxsplit=1)[1].strip()
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()[:7]
        return head[:7]
    except OSError:
        return "unknown"


_STATIC_VERSION = _compute_static_version()
_GIT_SHA = _detect_git_sha()


def _render_html_with_version(html_path: Path) -> str:
    raw = html_path.read_text(encoding="utf-8")
    bumped = _STATIC_URL_PATTERN.sub(rf"\1?v={_STATIC_VERSION}", raw)
    # Inject the reload bootstrap as early as possible — this script must
    # run before any other resource loads so a stale-cache reload can
    # ``location.replace`` without first executing the old JS.
    bootstrap = _build_bootstrap_script(_STATIC_VERSION)
    if _BOOTSTRAP_MARKER_PATTERN.search(bumped):
        bumped = _BOOTSTRAP_MARKER_PATTERN.sub(
            lambda _m: bootstrap, bumped, count=1
        )
    else:
        # Fallback for templates without the marker — still wedge it inside
        # <head> so the guard runs before anything else parses.
        bumped = re.sub(
            r"(<head[^>]*>)",
            lambda m: m.group(1) + bootstrap,
            bumped,
            count=1,
        )
    # Inject a visible footer marker so users can read the running build
    # straight from the dashboard — much faster than tailing server logs
    # when verifying a deploy reached the VPS.
    footer_html = (
        '<div style="text-align:center;margin:18px 0 8px;font-size:11px;'
        'opacity:0.45;letter-spacing:0.02em;font-family:system-ui,sans-serif;">'
        f"build {_GIT_SHA} · assets {_STATIC_VERSION}"
        "</div>"
    )
    if _VERSION_MARKER_PATTERN.search(bumped):
        bumped = _VERSION_MARKER_PATTERN.sub(
            lambda _m: footer_html, bumped, count=1
        )
    else:
        # Templates that haven't added the marker yet still get the footer
        # right before </body> so the diagnostic is universal.
        bumped = bumped.replace("</body>", footer_html + "\n</body>", 1)
    return bumped


_HTML_CACHE: dict[str, str] = {}


def _serve_html(filename: str) -> HTMLResponse:
    path = _TEMPLATES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} missing")
    rendered = _HTML_CACHE.get(filename)
    if rendered is None:
        rendered = _render_html_with_version(path)
        _HTML_CACHE[filename] = rendered
    return HTMLResponse(
        content=rendered,
        headers={
            # Force the WebView to revalidate the HTML on every open so a new
            # deploy's `?v=` query strings reach the user immediately. The
            # static assets behind those URLs remain cacheable for the long
            # haul because the version string acts as the cache key.
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )


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


def invalidate_wealth_cache_for_user(user_id) -> None:
    """Drop wealth-dashboard cache entries for one user after an edit."""
    stale_keys = [key for key in _wealth_cache if key and key[0] == user_id]
    for key in stale_keys:
        _wealth_cache.pop(key, None)


@router.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    """Serve the dashboard HTML. Auth happens in the API layer (per-request)."""
    # `miniapp_opened` here fires before the JS verifies user via initData, so
    # we don't have a user_id yet — the per-user dimension arrives via the
    # `miniapp_loaded` beacon once the dashboard finishes loading.
    analytics.track(analytics.EventType.MINIAPP_OPENED)
    return _serve_html("dashboard.html")


@router.get("/api/version")
async def get_app_version():
    """Public diagnostic — returns the running build's git SHA and asset hash.

    Use this to verify a deploy actually reached the VPS:

        curl https://<host>/miniapp/api/version

    Same values are rendered into the dashboard footer for in-app inspection.
    No auth on purpose — values are non-sensitive (publicly committed code).
    """
    return {
        "data": {
            "git_sha": _GIT_SHA,
            "static_version": _STATIC_VERSION,
        },
        "error": None,
    }


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
    analytics.track(
        analytics.EventType.MINIAPP_OPENED,
        properties={"page": "wealth"},
    )
    return _serve_html("wealth_dashboard.html")


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


@router.post("/api/wealth/start-asset-edit")
async def start_asset_edit_route(
    payload: dict,
    auth: dict = Depends(require_miniapp_auth),
    db: AsyncSession = Depends(get_db),
):
    """Trigger the asset edit wizard from a clicked dashboard row.

    Ownership is checked inside ``start_asset_edit_wizard`` via
    ``asset_service.get_asset_by_id``; the Mini App only passes the row id.
    """
    body = payload or {}
    asset_id = str(body.get("asset_id") or "")
    asset_ids = body.get("asset_ids")
    if not asset_id and not asset_ids:
        raise HTTPException(status_code=422, detail="asset_id is required")

    user = await _resolve_user(auth, db)

    from backend.bot.handlers.asset_entry import (
        show_asset_edit_picker,
        start_asset_edit_wizard,
    )

    if isinstance(asset_ids, list) and asset_ids:
        clean_ids = [str(item) for item in asset_ids]
        if len(clean_ids) > 1:
            await show_asset_edit_picker(db, user.telegram_id, user, clean_ids)
        else:
            await start_asset_edit_wizard(db, user.telegram_id, user, clean_ids[0])
    else:
        await start_asset_edit_wizard(db, user.telegram_id, user, asset_id)
    invalidate_wealth_cache_for_user(user.id)
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


# --- Phase 3.5 — Intent metrics (admin) --------------------------------


def _require_admin_api_key(
    x_admin_key: str = Header(
        ..., alias="X-Admin-Key", description="Internal admin API key"
    ),
) -> None:
    """Gatekeeper for the admin metrics endpoint.

    We don't reuse ``require_miniapp_auth`` because this endpoint isn't
    surfaced from the Mini App — it's an ops endpoint hit from a
    dashboard or curl. The shared internal_api_key from .env is the
    secret; in production swap for a per-user JWT once the admin UI
    grows beyond one human.
    """
    settings = get_settings()
    expected = (settings.internal_api_key or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503, detail="Admin API key not configured"
        )
    if x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.get("/api/intent-metrics")
async def get_intent_metrics(
    window_days: int = Query(
        1, ge=1, le=30, description="Daily summary window in days"
    ),
    histogram_days: int = Query(7, ge=1, le=90),
    cost_trend_days: int = Query(7, ge=1, le=90),
    top_unclear_limit: int = Query(20, ge=1, le=100),
    _: None = Depends(_require_admin_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Aggregations powering the intent ops dashboard.

    Bundles the four queries into one response so a single fetch hydrates
    the whole admin page. Cached implicitly by the events table indexes —
    no in-process cache because this endpoint is hit infrequently.
    """
    from datetime import datetime, timedelta, timezone

    summary_since = datetime.now(timezone.utc) - timedelta(days=window_days)
    histogram_since = datetime.now(timezone.utc) - timedelta(days=histogram_days)

    summary = await intent_metrics.daily_summary(db, since=summary_since)
    histogram = await intent_metrics.confidence_histogram(
        db, since=histogram_since
    )
    top_unclear = await intent_metrics.top_unclear_intents(
        db, since=histogram_since, limit=top_unclear_limit
    )
    trend = await intent_metrics.cost_trend(db, days=cost_trend_days)
    alerts = intent_metrics.evaluate_alerts(summary)

    return {
        "data": {
            "summary": summary,
            "confidence_histogram": histogram,
            "top_unclear_intents": top_unclear,
            "cost_trend": trend,
            "alerts": alerts,
        },
        "error": None,
    }
