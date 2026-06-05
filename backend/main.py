import asyncio
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.admin_spa import SPAStaticFiles

from backend.config import get_settings
from backend.api.admin import (
    analytics as admin_analytics,
    audit as admin_audit,
    auth as admin_auth,
    licenses as admin_licenses,
    twin_metrics as admin_twin_metrics,
    users as admin_users,
)
from backend.database import get_session_factory
from backend.miniapp import routes as miniapp_routes
from backend.routers import (
    admin_agent_metrics,
    cashflow as cashflow_router,
    expenses,
    goals,
    income,
    ingestion,
    life_events as life_events_router,
    market,
    portfolio,
    reports,
    telegram,
    twin,
    zalo as zalo_router,
)
from backend.bot.setup_commands import setup_bot_commands
from backend.bot.setup_menu_button import setup_chat_menu_button
from backend.adapters.zalo_oa import close_client as close_zalo_client
from backend.services.telegram_service import close_client as close_telegram_client
from backend.workers.telegram_worker import recover_orphaned_updates, run_recovery_loop

logger = logging.getLogger(__name__)
settings = get_settings()

# Seconds we wait for in-flight background tasks (Telegram update
# processing) to finish during a graceful shutdown. Longer than a typical
# LLM call, short enough to not stall a deploy. Any task still running
# after this is abandoned; the row stays in ``processing`` and the next
# startup picks it up as an orphan.
SHUTDOWN_TASK_GRACE_SECONDS = 30

# Max seconds to wait for PostgreSQL before proceeding anyway. Handles the
# race where launchd starts the backend before Docker containers finish
# coming up after a reboot.
_DB_WAIT_INTERVAL = 3  # seconds between retries
_DB_WAIT_ATTEMPTS = 20  # 20 × 3s = 60s max


async def _wait_for_db() -> None:
    """Retry DB connection at startup until PostgreSQL is reachable."""
    for attempt in range(1, _DB_WAIT_ATTEMPTS + 1):
        try:
            session_factory = get_session_factory()
            async with session_factory() as db:
                await db.execute(text("SELECT 1"))
            if attempt > 1:
                logger.info("Database ready after %d attempt(s)", attempt)
            return
        except Exception as exc:
            if attempt < _DB_WAIT_ATTEMPTS:
                logger.warning(
                    "DB not ready (attempt %d/%d): %s — retrying in %ds",
                    attempt,
                    _DB_WAIT_ATTEMPTS,
                    exc,
                    _DB_WAIT_INTERVAL,
                )
                await asyncio.sleep(_DB_WAIT_INTERVAL)
            else:
                logger.error(
                    "DB unreachable after %d attempts — proceeding anyway; "
                    "pool_pre_ping will recover connections as DB comes up",
                    _DB_WAIT_ATTEMPTS,
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Scheduled jobs run in a separate process — see backend/scheduler.py.
    # Keeping them out of the web server prevents duplicate cron fires when
    # more than one uvicorn worker is running.
    logger.info("Finance Assistant API starting up")

    # Phase 4.1 Story A.5 — Sentry init runs BEFORE anything that could
    # raise so the very first exception of a deploy is captured. Init
    # is idempotent and no-ops if SENTRY_DSN is unset (dev/test envs).
    try:
        from backend.adapters.observability import sentry_adapter

        sentry_adapter.init()
    except Exception:
        # Sentry init failure must never block boot — log and proceed.
        logger.exception("Sentry init failed; continuing without telemetry")

    # Block until PostgreSQL is reachable. This prevents the race where
    # launchd boots the backend before Docker containers finish starting.
    await _wait_for_db()

    # Sync the bot's command list with Telegram so the "/" menu always
    # reflects the current BOT_COMMANDS definition without a manual call
    # to the /set-commands endpoint after each deploy. Phase 3.6 cuts
    # the list down to 4 core commands — see bot/setup_commands.py.
    try:
        await setup_bot_commands()
        logger.info("Telegram bot commands registered")
    except Exception:
        logger.exception("Failed to register bot commands at startup; continuing")

    # Re-register the Mini App chat menu button on every boot. The URL
    # carries the current build hash so each deploy gives Telegram's
    # WebView a URL it has never cached before — root-cause fix for the
    # "users see old dashboard until they clear cache" problem. See
    # bot/setup_menu_button.py for the full rationale.
    #
    # We use ``current_build_hash()`` (a content-derived SHA over every
    # CSS/JS/HTML file the dashboards reference) rather than the git SHA.
    # Container images that strip ``.git`` make ``_GIT_SHA`` return
    # ``"unknown"`` — a literal that doesn't change between deploys —
    # which used to leave the menu URL stuck on ``?b=unknown`` and
    # silently neutralise the entire cache-bust mechanism.
    try:
        from backend.miniapp.routes import current_build_hash

        await setup_chat_menu_button(current_build_hash())
    except Exception:
        logger.exception(
            "Failed to register chat menu button at startup; continuing — "
            "users keep whatever menu button BotFather has on file"
        )

    # Phase 4.3 Story 3.1 — register the Twin recompute worker on the
    # in-memory event bus. Importing the module runs ``register()`` and
    # subscribes ``handle_twin_event`` so that ``expense.added``,
    # ``asset.created`` etc. published from services actually wake up a
    # debounced recompute. Without this import, every publish is a no-op
    # because the subscriber set is empty.
    try:
        from backend.workers import twin_recompute_worker  # noqa: F401

        logger.info("Twin recompute worker subscribed to event bus")
    except Exception:
        logger.exception(
            "Failed to register Twin recompute worker — on-demand Twin "
            "recompute (Story 3.1) will be inactive this boot"
        )

    # Pick up any telegram_updates that were mid-flight when the previous
    # process died. See docs/archive/scaling-refactor-A.md §A1.
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
        recovery_task.cancel()
        try:
            await recovery_task
        except asyncio.CancelledError:
            pass

    # Graceful shutdown: give in-flight background tasks a bounded window
    # to finish so we don't leave updates half-processed when uvicorn
    # receives SIGTERM during a deploy.
    pending = [
        t
        for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and not t.done()
    ]
    if pending:
        logger.info(
            "Waiting up to %ds for %d background task(s) to finish",
            SHUTDOWN_TASK_GRACE_SECONDS,
            len(pending),
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

    await close_telegram_client()
    await close_zalo_client()

    logger.info("Finance Assistant API shutting down")


app = FastAPI(
    title="Finance Assistant API",
    description="Personal finance AI assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.admin_allowed_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

_admin_rate_windows: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def admin_api_rate_limit(request: Request, call_next):
    """Memory backstop for /api/admin until traffic reaches Caddy.

    Caddy is the production enforcement point; this lightweight process-local
    limiter keeps dev/staging safe and avoids adding a runtime dependency.
    """
    if request.url.path.startswith("/api/admin/"):
        now = time.monotonic()
        window = _admin_rate_windows[_client_ip(request)]
        cutoff = now - 60
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= settings.admin_api_rate_limit_per_minute:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many admin API requests"},
            )
        window.append(now)
    return await call_next(request)


@app.middleware("http")
async def force_fresh_miniapp_static_assets(request: Request, call_next):
    """Bypass conditional revalidation for Telegram Mini App static files.

    Telegram WebView has a known cache-key quirk: query-string cache busters
    (``?v=...``) may be ignored for ``/miniapp/static/*``. If the client sends
    ``If-None-Match``/``If-Modified-Since``, Starlette StaticFiles can return
    304 and the stale JS keeps running (spinner hangs forever).

    We strip conditional headers for Mini App static requests so every request
    gets a full 200 response body with the currently deployed bytes.
    """
    if request.url.path.startswith("/miniapp/static/"):
        scope = request.scope
        raw_headers = scope.get("headers") or []
        scope["headers"] = [
            (k, v)
            for (k, v) in raw_headers
            if k.lower() not in {b"if-none-match", b"if-modified-since"}
        ]
    return await call_next(request)


_MINIAPP_STATIC = Path(__file__).parent / "miniapp" / "static"
if _MINIAPP_STATIC.exists():
    app.mount(
        "/miniapp/static",
        StaticFiles(directory=str(_MINIAPP_STATIC)),
        name="miniapp-static",
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
# Phase 4.1 channel discipline (Task D.1): the Zalo OA webhook is only
# mounted when ZALO_CHANNEL_ENABLED=true. Soft launch is Telegram-only
# so the default-off setting is the safety guarantee — even if Zalo OA
# secrets leak into the env, the webhook stays 404.
if settings.zalo_channel_enabled:
    app.include_router(zalo_router.router, prefix="/api/v1")
    logger.info("Zalo channel ENABLED — webhook mounted at /api/v1/zalo/webhook")
else:
    logger.info(
        "Zalo channel disabled (ZALO_CHANNEL_ENABLED=false) — webhook not mounted"
    )
app.include_router(twin.router, prefix="/api")
app.include_router(life_events_router.router, prefix="/api")
app.include_router(cashflow_router.router, prefix="/api")
app.include_router(admin_agent_metrics.router, prefix="/api/v1")
app.include_router(admin_auth.router, prefix="/api/admin")
app.include_router(admin_analytics.router, prefix="/api/admin")
app.include_router(admin_audit.router, prefix="/api/admin")
app.include_router(admin_users.router, prefix="/api/admin")
app.include_router(admin_licenses.router, prefix="/api/admin")
app.include_router(admin_twin_metrics.router, prefix="/api/admin")
app.include_router(miniapp_routes.router)  # No /api/v1 prefix — Mini App URL is public


@app.get("/health")
async def health_check():
    return JSONResponse(content={"data": {"status": "healthy"}, "error": None})


_ADMIN_STATIC = Path(__file__).parent / "static" / "admin"
if _ADMIN_STATIC.exists():
    # Canonical admin URL is /admin/ (matches Cloudflare ingress + deploy
    # script success message). Starlette's Mount("/admin", ...) only
    # matches /admin/* — bare /admin still 404s without an explicit
    # redirect, so add one before mounting.
    @app.get("/admin", include_in_schema=False)
    async def _admin_trailing_slash():
        return RedirectResponse(url="/admin/", status_code=308)

    # /admin mount must come BEFORE / so the more-specific prefix wins
    # for /admin/login, /admin/assets/*, etc.
    app.mount(
        "/admin",
        SPAStaticFiles(directory=str(_ADMIN_STATIC), html=True),
        name="admin-spa-prefix",
    )
    # Root mount kept for backward-compat: pre-fix users had / bookmarked.
    app.mount(
        "/", SPAStaticFiles(directory=str(_ADMIN_STATIC), html=True), name="admin-spa"
    )
