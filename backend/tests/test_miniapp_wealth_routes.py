"""Tests for the wealth dashboard route handlers (P3A-22).

Covers:
- 401 when ``X-Telegram-Init-Data`` header is missing or invalid.
- Happy path returns the composed payload.
- Cache TTL — second call within window returns cached value.
- /trend rejects unsupported ``days`` values with 422.
- Service errors map to a graceful 500 with friendly Vietnamese copy.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import app
from backend.miniapp import routes as miniapp_routes
from backend.miniapp.auth import require_miniapp_auth

client = TestClient(app)


async def _stub_db():
    """Stand-in for ``get_db`` — wealth routes don't actually touch the
    DB once we mock ``_resolve_user`` and the service calls."""
    yield MagicMock()


def _fake_user(telegram_id: int = 12345):
    """Match the User shape that ``_resolve_user`` returns (id is enough)."""
    return SimpleNamespace(id=uuid.uuid4(), telegram_id=telegram_id)


def _override_auth(user_id: int = 12345):
    """Bypass HMAC verification — return a fake verified payload."""

    async def _ok():
        return {"user_id": user_id, "first_name": "Test"}

    app.dependency_overrides[require_miniapp_auth] = _ok
    app.dependency_overrides[get_db] = _stub_db


def _clear_overrides():
    app.dependency_overrides.pop(require_miniapp_auth, None)
    app.dependency_overrides.pop(get_db, None)
    miniapp_routes._wealth_cache_clear()


SAMPLE_OVERVIEW = {
    "net_worth": 5_000_000.0,
    "asset_count": 1,
    "currency": "VND",
    "level": "starter",
    "level_label": "Khởi đầu",
    "change_day": {"amount": 0.0, "pct": 0.0},
    "change_month": {"amount": 1_000_000.0, "pct": 25.0},
    "breakdown": [
        {
            "asset_type": "cash",
            "label": "Tiền mặt & Tài khoản",
            "icon": "💵",
            "color": "#10B981",
            "value": 5_000_000.0,
            "pct": 100.0,
        }
    ],
    "trend": [{"date": "2026-04-01", "value": 5_000_000.0}],
    "trend_days": 90,
    "assets": [
        {
            "id": "abc",
            "name": "VCB",
            "asset_type": "cash",
            "subtype": None,
            "icon": "💵",
            "type_label": "Tiền mặt & Tài khoản",
            "current_value": 5_000_000.0,
            "initial_value": 5_000_000.0,
            "change": 0.0,
            "change_pct": 0.0,
            "acquired_at": "2026-01-01",
        }
    ],
    "next_milestone": {
        "target": 30_000_000.0,
        "target_level": "young_prof",
        "target_label": "Trẻ Năng Động",
        "pct_progress": 16.67,
        "remaining": 25_000_000.0,
    },
}


class TestWealthOverviewAuth:
    def setup_method(self):
        # Stub the DB dependency so failures don't bubble from auth →
        # database init when no DATABASE_URL is configured in CI.
        app.dependency_overrides[get_db] = _stub_db

    def teardown_method(self):
        _clear_overrides()

    def test_missing_init_data_returns_401(self):
        # No header → FastAPI raises 422 (Header(...) is required).
        resp = client.get("/miniapp/api/wealth/overview")
        assert resp.status_code in {401, 422}

    def test_invalid_init_data_returns_401(self):
        resp = client.get(
            "/miniapp/api/wealth/overview",
            headers={"X-Telegram-Init-Data": "invalid-data"},
        )
        assert resp.status_code == 401


class TestWealthOverviewHappyPath:
    def teardown_method(self):
        _clear_overrides()

    def test_returns_payload_and_caches(self):
        _override_auth()
        build_mock = AsyncMock(return_value=SAMPLE_OVERVIEW)
        # Stable user across both calls so the cache key matches.
        user = _fake_user()

        async def _fake_resolve(auth, db):
            return user

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), patch.object(
            miniapp_routes.wealth_dashboard_service,
            "build_overview",
            build_mock,
        ):
            resp = client.get(
                "/miniapp/api/wealth/overview?source=briefing",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["error"] is None
            assert body["data"]["net_worth"] == 5_000_000.0
            assert body["data"]["level"] == "starter"
            assert body["data"]["next_milestone"]["target"] == 30_000_000.0

            # Second call hits the cache — service NOT called twice.
            resp2 = client.get(
                "/miniapp/api/wealth/overview?source=briefing",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp2.status_code == 200
            assert build_mock.await_count == 1

    def test_service_failure_returns_500(self):
        _override_auth()

        async def _fake_resolve(auth, db):
            return _fake_user()

        async def _boom(*args, **kwargs):
            raise RuntimeError("db blew up")

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), patch.object(
            miniapp_routes.wealth_dashboard_service,
            "build_overview",
            _boom,
        ):
            resp = client.get(
                "/miniapp/api/wealth/overview",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 500
            # Friendly copy in the detail — not a Python traceback.
            assert "tài sản" in resp.json()["detail"].lower()


class TestWealthTrendEndpoint:
    def teardown_method(self):
        _clear_overrides()

    def test_rejects_unsupported_days(self):
        _override_auth()

        async def _fake_resolve(auth, db):
            return _fake_user()

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve):
            resp = client.get(
                "/miniapp/api/wealth/trend?days=7",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 422
            assert "30" in resp.json()["detail"]

    def test_happy_path_returns_trend(self):
        _override_auth()
        trend_mock = AsyncMock(
            return_value=[
                {"date": "2026-04-01", "value": 5_000_000.0},
                {"date": "2026-04-02", "value": 5_500_000.0},
            ]
        )

        async def _fake_resolve(auth, db):
            return _fake_user()

        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), patch.object(
            miniapp_routes.wealth_dashboard_service,
            "get_trend",
            trend_mock,
        ):
            resp = client.get(
                "/miniapp/api/wealth/trend?days=90",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert len(data) == 2
            assert data[0]["value"] == 5_000_000.0


class TestStartAssetWizardRoute:
    def teardown_method(self):
        _clear_overrides()

    def test_invokes_wizard_with_user_telegram_id_as_chat_id(self):
        _override_auth()
        user = _fake_user(telegram_id=98765)

        async def _fake_resolve(auth, db):
            return user

        wizard_mock = AsyncMock()
        # Patch the symbol where it's imported — the route does a lazy
        # import inside the handler, so we patch the source module.
        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), patch(
            "backend.bot.handlers.asset_entry.start_asset_wizard",
            wizard_mock,
        ):
            resp = client.post(
                "/miniapp/api/wealth/start-asset-wizard",
                headers={"X-Telegram-Init-Data": "stub"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"data": {"ok": True}, "error": None}

            wizard_mock.assert_awaited_once()
            args = wizard_mock.await_args.args
            # (db, chat_id, user) — chat_id must equal user.telegram_id
            # so the bot posts the type-picker into the user's private chat.
            assert args[1] == 98765
            assert args[2] is user

    def test_requires_auth(self):
        # No auth override — the real require_miniapp_auth dependency
        # rejects the missing/invalid initData.
        app.dependency_overrides[get_db] = _stub_db
        try:
            resp = client.post(
                "/miniapp/api/wealth/start-asset-wizard",
                headers={"X-Telegram-Init-Data": "invalid"},
            )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestStartAssetEditRoute:
    def teardown_method(self):
        _clear_overrides()

    def test_invokes_single_asset_edit_from_member_ids(self):
        _override_auth()
        user = _fake_user(telegram_id=98765)
        asset_id = str(uuid.uuid4())

        async def _fake_resolve(auth, db):
            return user

        edit_mock = AsyncMock()
        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), patch(
            "backend.bot.handlers.asset_entry.start_asset_edit_wizard",
            edit_mock,
        ):
            resp = client.post(
                "/miniapp/api/wealth/start-asset-edit",
                headers={"X-Telegram-Init-Data": "stub"},
                json={"asset_ids": [asset_id]},
            )

        assert resp.status_code == 200
        edit_mock.assert_awaited_once()
        args = edit_mock.await_args.args
        assert args[1] == 98765
        assert args[2] is user
        assert args[3] == asset_id

    def test_invokes_group_picker_for_multiple_member_ids(self):
        _override_auth()
        user = _fake_user(telegram_id=98765)
        asset_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        async def _fake_resolve(auth, db):
            return user

        picker_mock = AsyncMock()
        with patch.object(miniapp_routes, "_resolve_user", _fake_resolve), patch(
            "backend.bot.handlers.asset_entry.show_asset_edit_picker",
            picker_mock,
        ):
            resp = client.post(
                "/miniapp/api/wealth/start-asset-edit",
                headers={"X-Telegram-Init-Data": "stub"},
                json={"asset_ids": asset_ids},
            )

        assert resp.status_code == 200
        picker_mock.assert_awaited_once()
        args = picker_mock.await_args.args
        assert args[1] == 98765
        assert args[2] is user
        assert args[3] == asset_ids

    def test_requires_asset_id(self):
        _override_auth()
        resp = client.post(
            "/miniapp/api/wealth/start-asset-edit",
            headers={"X-Telegram-Init-Data": "stub"},
            json={},
        )
        assert resp.status_code == 422


class TestWealthDashboardPage:
    def test_serves_html(self):
        resp = client.get("/miniapp/wealth")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        body = resp.text
        assert "Tổng tài sản" in body
        # Must reference the wealth-specific JS + CSS bundles.
        assert "wealth_dashboard.js" in body
        assert "wealth.css" in body

    def test_static_refs_carry_cache_busting_version(self):
        """Telegram WebView caches /miniapp/static aggressively; without a
        ``?v=`` query string a freshly-deployed UI change is invisible to
        users until cache eviction. The hash must change whenever any
        referenced asset changes — see _compute_static_version."""
        resp = client.get("/miniapp/wealth")
        body = resp.text
        version = miniapp_routes._STATIC_VERSION
        assert version  # non-empty hash
        assert f"wealth_dashboard.js?v={version}" in body
        assert f"wealth.css?v={version}" in body
        assert f"style.css?v={version}" in body

    def test_html_response_disables_browser_cache(self):
        """HTML doc must revalidate every open so a new deploy's ``?v=``
        version reaches the user immediately."""
        resp = client.get("/miniapp/wealth")
        cache_control = resp.headers.get("cache-control", "")
        assert "no-cache" in cache_control
        assert "no-store" in cache_control or "must-revalidate" in cache_control

    def test_legacy_dashboard_also_versioned(self):
        resp = client.get("/miniapp/dashboard")
        assert resp.status_code == 200
        body = resp.text
        version = miniapp_routes._STATIC_VERSION
        assert f"dashboard.js?v={version}" in body
        assert f"style.css?v={version}" in body

    def test_dashboard_injects_reload_bootstrap_with_current_version(self):
        """Inline reload guard must appear in the served HTML and embed the
        current build hash. Telegram WebView (especially iOS WebKit) can
        ignore Cache-Control on HTML; the live probe forces a `?b=<hash>`
        reload when the server hash drifts, so a stale WebView state
        self-heals on the next visibility change without requiring the
        user to manually clear Telegram's cache. The synchronous
        localStorage drift reload was removed to fix issue #610 — see
        the bootstrap docstring."""
        resp = client.get("/miniapp/wealth")
        body = resp.text
        version = miniapp_routes._STATIC_VERSION
        # Bootstrap must run before any other script — the placeholder is
        # placed before the telegram-web-app.js include in the template.
        assert body.index(f"'{version}'") < body.index("telegram-web-app.js")
        assert "fa.app.build" in body
        # Diagnostic seed remains (so support can read back the stored
        # hash) but we never read it back to navigate — see issue #610.
        assert "localStorage.setItem" in body
        assert "localStorage.getItem" not in body
        # Handshake guard: don't navigate while initData is empty.
        assert "!w.initData" in body
        # Hash-fragment preservation: keep `#tgWebAppData=...` across the
        # live-probe reload so the reloaded page still authenticates.
        assert "u.hash=location.hash" in body
        assert "location.replace" in body

    def test_legacy_dashboard_also_has_reload_bootstrap(self):
        resp = client.get("/miniapp/dashboard")
        body = resp.text
        assert f"'{miniapp_routes._STATIC_VERSION}'" in body
        assert "fa.app.build" in body

    def test_dashboard_renders_visible_build_marker(self):
        """User-facing footer prints git SHA + asset hash so a glance at the
        Mini App reveals which build the VPS is running. Indispensable when
        debugging "I pushed but UI didn't change" — without this the only
        way to verify the deploy is to ssh into the VPS."""
        resp = client.get("/miniapp/wealth")
        body = resp.text
        assert miniapp_routes._STATIC_VERSION in body
        # Footer copy must contain the literal "build" prefix so users can
        # search/screenshot it unambiguously.
        assert "build " in body
        assert f"assets {miniapp_routes._STATIC_VERSION}" in body


class TestMiniAppStaticCacheBehavior:
    def test_static_js_ignores_conditional_request_headers(self):
        """Regression guard for issue #765.

        Telegram WebView may ignore query-string cache busters and still send
        conditional requests for /miniapp/static/*. We must return 200 with a
        body (not 304) so stale JS never survives a deploy.
        """
        first = client.get("/miniapp/static/js/expense_dashboard.js")
        assert first.status_code == 200
        assert first.text

        etag = first.headers.get("etag")
        last_modified = first.headers.get("last-modified")
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        second = client.get("/miniapp/static/js/expense_dashboard.js", headers=headers)
        assert second.status_code == 200
        assert second.text


class TestVersionEndpoint:
    def test_returns_git_sha_and_static_version(self):
        resp = client.get("/miniapp/api/version")
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] is None
        assert body["data"]["static_version"] == miniapp_routes._STATIC_VERSION
        assert body["data"]["git_sha"] == miniapp_routes._GIT_SHA

    def test_response_is_uncacheable(self):
        """The dashboard bootstrap polls this endpoint on every visibility
        change to detect a deploy. A cached response would defeat that —
        Telegram Desktop users would stay locked on the previous build
        until the browser cache expired."""
        resp = client.get("/miniapp/api/version")
        cache_control = resp.headers.get("cache-control", "")
        assert "no-cache" in cache_control
        assert "no-store" in cache_control

    def test_no_auth_required(self):
        # Diagnostic endpoint is intentionally public — values are non-sensitive
        # and ssh-less verification of a deploy is the whole point.
        resp = client.get("/miniapp/api/version")
        assert resp.status_code == 200


class TestDesktopLiveProbe:
    """Telegram Desktop (macOS) keeps the WebApp WebView alive across panel
    close/reopen, so a deploy stays invisible until the user fully quits
    Telegram. The bootstrap embeds a JS probe that polls
    /miniapp/api/version whenever the page becomes visible — when the
    server hash drifts from the one baked into the cached HTML, the probe
    triggers a hard reload to the fresh URL.
    """

    def _fetch_dashboard(self):
        return client.get(
            f"/miniapp/wealth?b={miniapp_routes._STATIC_VERSION}",
            follow_redirects=False,
        )

    def test_bootstrap_exposes_build_to_window(self):
        assert "window.__FA_BUILD__=" in self._fetch_dashboard().text

    def test_bootstrap_fetches_version_endpoint_uncached(self):
        body = self._fetch_dashboard().text
        # Must hit the version endpoint with cache: 'no-store' so we always
        # reach the network even if a proxy ignores the response headers.
        assert "/miniapp/api/version" in body
        assert "no-store" in body

    def test_bootstrap_listens_to_visibility_signals(self):
        """All three signals matter: visibilitychange catches normal tab
        focus, pageshow catches bfcache restore (Safari/iOS), and Telegram
        WebApp's viewportChanged catches Desktop's panel reopen — the
        one signal that fires on macOS where the others stay silent.
        """
        body = self._fetch_dashboard().text
        assert "visibilitychange" in body
        assert "pageshow" in body
        assert "viewportChanged" in body

    def test_bootstrap_reload_uses_canonical_b_param(self):
        """On mismatch the probe sets ``?b=`` so the reloaded URL matches
        the canonical cache-bust convention used by ``wealth_dashboard_url``
        and the chat-menu-button helper — keeping a single ``?b=<hash>``
        URL key per build across every entry point."""
        body = self._fetch_dashboard().text
        assert "searchParams.set('b'," in body

    def test_bootstrap_guards_against_repeat_reload(self):
        """If the probe ticks twice before navigation completes, the
        second invocation must no-op so users don't see a flicker storm."""
        body = self._fetch_dashboard().text
        assert "_faReloading" in body


class TestBuildHashRedirect:
    """Dashboard pages must always serve 200 OK with the freshly-rendered
    HTML — never a 3xx — because Telegram Mini App WebViews do not follow
    HTTP redirects automatically (issue #608: 302 → blank panel).

    Cache busting is owned by the JS bootstrap inside the HTML (localStorage
    drift check + ``/miniapp/api/version`` live probe), so a stale or
    missing ``?b=`` on the request URL still lands the user on a fresh
    dashboard. ``wealth_dashboard_url`` continues to emit ``?b=<hash>`` on
    every freshly-rendered button so each deploy gets a never-before-seen
    URL that Telegram treats as uncached.
    """

    def test_missing_b_serves_html_directly(self):
        """No ``?b=`` arrives → server still responds 200 with the current
        HTML (which bakes the current build hash into the bootstrap)."""
        resp = client.get("/miniapp/wealth", follow_redirects=False)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        # Fresh HTML must contain the current build hash so the bootstrap's
        # probe + localStorage check both see the canonical value.
        assert f"'{miniapp_routes._STATIC_VERSION}'" in resp.text

    def test_stale_b_serves_html_directly(self):
        """An old inline button still in chat history (``?b=oldhash``) must
        load — Telegram cannot follow a redirect to the fresh hash, so we
        serve the page directly and let the JS bootstrap reconcile."""
        resp = client.get(
            "/miniapp/wealth?b=oldhash&source=briefing", follow_redirects=False
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert f"'{miniapp_routes._STATIC_VERSION}'" in resp.text

    def test_current_b_serves_html_directly(self):
        resp = client.get(
            f"/miniapp/wealth?b={miniapp_routes._STATIC_VERSION}",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_twin_page_serves_html_without_redirect(self):
        resp = client.get("/miniapp/twin", follow_redirects=False)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_cashflow_page_serves_html_without_redirect(self):
        resp = client.get("/miniapp/cashflow", follow_redirects=False)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_expense_page_serves_html_without_redirect(self):
        resp = client.get("/miniapp/expense", follow_redirects=False)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_html_template_change_bumps_static_version(self, tmp_path, monkeypatch):
        """Without HTML in the hash, an HTML-only edit (sort buttons, copy,
        layout) wouldn't move ``_STATIC_VERSION`` and every cache-bust URL
        would stay the same as the previous deploy. Verify HTML files are
        actually included in ``_compute_static_version``."""
        baseline = miniapp_routes._compute_static_version()

        # Mutate the HTML file on disk and confirm the hash moves.
        wealth_tpl = miniapp_routes._TEMPLATES_DIR / "wealth_dashboard.html"
        original = wealth_tpl.read_text(encoding="utf-8")
        try:
            wealth_tpl.write_text(original + "\n<!-- bust -->\n", encoding="utf-8")
            bumped = miniapp_routes._compute_static_version()
            assert bumped != baseline, (
                "HTML edits must change the build hash — otherwise the "
                "?b= cache-bust on the menu button URL stays constant "
                "across HTML-only deploys"
            )
        finally:
            wealth_tpl.write_text(original, encoding="utf-8")


class TestMiniappUrlHelpers:
    """Every Mini App URL helper must emit ``?b=<build_hash>`` so Telegram's
    WebView treats each deploy as a fresh URL — bug repro: PR #452 changed
    HTML but ``/dashboard`` command kept serving cached HTML because the
    URL ``?source=dashboard_command`` was identical across deploys.
    """

    def _with_base_url(self, monkeypatch, base: str | None):
        from backend.config import get_settings

        settings = get_settings()
        original = settings.miniapp_base_url
        settings.miniapp_base_url = base
        monkeypatch.setattr(
            "backend.miniapp.urls.get_settings", lambda: settings
        )
        return original

    def test_wealth_url_includes_build_hash(self, monkeypatch):
        from backend.miniapp.urls import wealth_dashboard_url

        original = self._with_base_url(monkeypatch, "https://example.com")
        try:
            url = wealth_dashboard_url(source="briefing")
        finally:
            from backend.config import get_settings

            get_settings().miniapp_base_url = original

        assert url is not None
        assert url.startswith("https://example.com/miniapp/wealth?")
        assert f"b={miniapp_routes._STATIC_VERSION}" in url
        assert "source=briefing" in url

    def test_twin_url_includes_build_hash(self, monkeypatch):
        from backend.miniapp.urls import twin_dashboard_url

        original = self._with_base_url(monkeypatch, "https://example.com")
        try:
            url = twin_dashboard_url(source="telegram_twin")
        finally:
            from backend.config import get_settings

            get_settings().miniapp_base_url = original

        assert url is not None
        assert f"b={miniapp_routes._STATIC_VERSION}" in url
        assert "source=telegram_twin" in url

    def test_returns_none_when_base_url_unset(self, monkeypatch):
        from backend.miniapp.urls import wealth_dashboard_url

        original = self._with_base_url(monkeypatch, "")
        try:
            assert wealth_dashboard_url(source="x") is None
        finally:
            from backend.config import get_settings

            get_settings().miniapp_base_url = original
