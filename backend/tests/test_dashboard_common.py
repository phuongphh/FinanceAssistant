"""Behavioural tests for the shared dashboard helper bundle.

`dashboard_common.js` is loaded by every miniapp dashboard template
before the dashboard-specific bundle and exposes a single
``window.DashboardCommon`` namespace. A bug here would silently break
every dashboard at once, so we exercise the public surface in a Node
sandbox (no fastapi / DOM dependency).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "backend/miniapp/static/js/dashboard_common.js"
NODE = shutil.which("node")


def _evaluate(snippet: str) -> dict:
    """Load dashboard_common.js into a Node vm sandbox and evaluate
    ``snippet`` against ``window.DashboardCommon``. Returns the parsed
    JSON object the snippet prints to stdout.
    """
    harness = f"""
const vm = require('vm');
const fs = require('fs');

const ctx = {{
    console,
    Intl,
    Math,
    Number,
    String,
    Boolean,
    Object,
    Array,
    Date,
    Map,
    Set,
    Promise,
    Error,
    JSON,
    RegExp,
    AbortController,
    setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms | 0, 50)),
    clearTimeout,
    parseInt,
    parseFloat,
    isNaN,
    URLSearchParams,
}};
ctx.window = ctx;
ctx.self = ctx;
ctx.globalThis = ctx;
ctx.document = {{ documentElement: {{ style: {{ setProperty: () => {{}} }} }} }};
ctx.Telegram = {{ WebApp: {{ initData: 'stub', initDataUnsafe: {{ user: {{ language_code: 'vi' }} }} }} }};
ctx.fetch = (url, opts) => Promise.resolve({{
    ok: true,
    status: 200,
    headers: {{ get: () => null }},
    json: () => Promise.resolve({{ data: {{ url: String(url) }} }}),
}});

vm.createContext(ctx);
vm.runInContext(fs.readFileSync({str(COMMON)!r}, 'utf8'), ctx, {{
    filename: 'dashboard_common.js',
    timeout: 5000,
}});

(async () => {{
    try {{
        const DC = ctx.DashboardCommon;
        const result = await (async () => {{ {snippet} }})();
        process.stdout.write(JSON.stringify({{ ok: true, result }}));
    }} catch (err) {{
        process.stdout.write(JSON.stringify({{ ok: false, error: String(err && err.message || err) }}));
        process.exit(1);
    }}
}})();
""".strip()
    proc = subprocess.run(
        [NODE, "-e", harness],
        capture_output=True,
        text=True,
        timeout=10,
    )
    stdout = (proc.stdout or "").strip()
    assert stdout, f"node printed nothing (exit={proc.returncode}); stderr={proc.stderr}"
    payload = json.loads(stdout)
    assert payload.get("ok"), f"snippet failed: {payload.get('error')}"
    return payload["result"]


pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js not on PATH; skipping shared-helpers tests.")


def test_dashboard_common_exposes_expected_helpers() -> None:
    """Lock the public surface — every consumer destructures from this list."""
    keys = _evaluate("return Object.keys(DC).sort();")
    assert keys == sorted([
        "applyTheme",
        "formatMoneyShort",
        "formatMoneyFull",
        "escapeHtml",
        "fetchAPI",
        "resolveInitData",
        "authHeaders",
        "formatDate",
        "resolveDateFormat",
    ])


def test_format_money_short_canonical_precision() -> None:
    """Canonical 2-decimal precision for billions, 1-decimal for millions,
    rounded thousands, rounded raw đồng. Mirrors the rule the expense and
    wealth dashboards depended on before extraction.
    """
    cases = _evaluate("""
        return {
            '0': DC.formatMoneyShort(0),
            '500': DC.formatMoneyShort(500),
            '1500': DC.formatMoneyShort(1500),
            '12345': DC.formatMoneyShort(12345),
            '1500000': DC.formatMoneyShort(1500000),
            '1234567890': DC.formatMoneyShort(1234567890),
            '2000000000': DC.formatMoneyShort(2000000000),
            'neg45000': DC.formatMoneyShort(-45000),
        };
    """)
    assert cases["0"] == "0đ"
    assert cases["500"] == "500đ"
    assert cases["1500"] == "2k"  # round
    assert cases["12345"] == "12k"
    assert cases["1500000"] == "1.5tr"
    assert cases["1234567890"] == "1.23 tỷ"
    assert cases["2000000000"] == "2 tỷ"  # trailing zeros stripped
    assert cases["neg45000"] == "-45k"


def test_format_money_full_uses_vi_locale_grouping() -> None:
    cases = _evaluate("""
        return {
            '1000': DC.formatMoneyFull(1000),
            '1234567': DC.formatMoneyFull(1234567),
            'rounded': DC.formatMoneyFull(1500.7),
        };
    """)
    assert cases["1000"] == "1,000đ"
    assert cases["1234567"] == "1,234,567đ"
    assert cases["rounded"] == "1,501đ"


def test_escape_html_blocks_xss_vectors() -> None:
    """Defensive: any string we interpolate into innerHTML must be
    escaped. The helper is used across every dashboard for user-supplied
    merchant names, notes, category labels.
    """
    cases = _evaluate("""
        return {
            ampersand: DC.escapeHtml('Tom & Jerry'),
            tag: DC.escapeHtml('<script>alert(1)</script>'),
            quote: DC.escapeHtml('say \"hi\"'),
            falsy_null: DC.escapeHtml(null),
            falsy_undef: DC.escapeHtml(undefined),
        };
    """)
    assert cases["ampersand"] == "Tom &amp; Jerry"
    assert cases["tag"] == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert cases["quote"] == "say &quot;hi&quot;"
    assert cases["falsy_null"] == ""
    assert cases["falsy_undef"] == ""


def test_format_date_local_timezone_interpretation() -> None:
    """Contract: ISO date YYYY-MM-DD must render in *local* timezone.
    Appending T00:00:00 prevents the date from sliding to the previous
    day when rendered in a UTC-shifted environment.
    """
    cases = _evaluate("""
        return {
            normal: DC.formatDate('2025-12-31'),
            empty: DC.formatDate(''),
            null_: DC.formatDate(null),
        };
    """)
    assert cases["normal"] == "31/12/2025"
    assert cases["empty"] == "--/--/----"
    assert cases["null_"] == "--/--/----"


def test_fetch_api_includes_telegram_init_data_header() -> None:
    """Security/auth: every miniapp API call must carry the
    X-Telegram-Init-Data header so the backend can verify the caller.
    """
    captured = _evaluate("""
        let captured = null;
        ctx.fetch = (url, opts) => {
            captured = { url: String(url), headers: opts && opts.headers };
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve({ data: { ok: 1 } }),
            });
        };
        const data = await DC.fetchAPI('/wealth/overview');
        return { captured, data };
    """)
    assert captured["captured"]["url"] == "/miniapp/api/wealth/overview"
    assert captured["captured"]["headers"]["X-Telegram-Init-Data"] == "stub"
    assert captured["captured"]["headers"]["Content-Type"] == "application/json"
    assert captured["data"] == {"ok": 1}


def test_fetch_api_waits_for_late_init_data_before_fallback() -> None:
    """Telegram WebApp can hydrate initData a tick late on cold loads.
    fetchAPI should wait briefly so first request is authenticated.
    """
    captured = _evaluate("""
        let calls = 0;
        ctx.Telegram.WebApp.initData = '';
        ctx.fetch = (url, opts) => {
            calls += 1;
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve({ data: { ok: calls, hdr: opts && opts.headers && opts.headers['X-Telegram-Init-Data'] } }),
            });
        };
        setTimeout(() => { ctx.Telegram.WebApp.initData = 'late-stub'; }, 20);
        const data = await DC.fetchAPI('/expense-dashboard/overview');
        return data;
    """)
    assert captured["ok"] == 1
    assert captured["hdr"] == "late-stub"


def test_fetch_api_uses_query_initdata_without_double_decode_breakage() -> None:
    """URLSearchParams already decodes values; decode again can crash on `%`."""
    captured = _evaluate("""
        let seenHeader = '';
        ctx.Telegram.WebApp.initData = '';
        ctx.location = { search: '?tgWebAppData=query%25signed%3Dabc' };
        ctx.fetch = (url, opts) => {
            seenHeader = opts && opts.headers && opts.headers['X-Telegram-Init-Data'];
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve({ data: { ok: 1 } }),
            });
        };
        const data = await DC.fetchAPI('/expense-dashboard/overview');
        return { data, seenHeader };
    """)
    assert captured["data"] == {"ok": 1}
    assert captured["seenHeader"] == "query%signed=abc"


def test_resolve_init_data_reads_hash_fragment() -> None:
    """Root-cause regression guard (issue #865): Telegram puts launch
    params in the URL *hash* (#tgWebAppData=…), not the query string. When
    tg.initData hasn't hydrated, resolveInitData must recover auth from the
    hash so the page-load GET still authenticates instead of 401-ing.
    """
    captured = _evaluate("""
        ctx.Telegram.WebApp.initData = '';
        ctx.location = { hash: '#tgWebAppData=hash%25signed%3Dxyz&tgWebAppVersion=7.0', search: '' };
        const resolved = await DC.resolveInitData(0);
        return { resolved };
    """)
    assert captured["resolved"] == "hash%signed=xyz"


def test_auth_headers_attach_resolved_init_data() -> None:
    """Mutation guard: POST/PATCH headers must carry the same resolved
    initData the page-load GET sent. Without this, a page that recovered
    auth from the hash would load but silently 401 on every mutation.
    """
    captured = _evaluate("""
        ctx.Telegram.WebApp.initData = '';
        ctx.location = { hash: '#tgWebAppData=from-hash', search: '' };
        const headers = await DC.authHeaders();
        return headers;
    """)
    assert captured["X-Telegram-Init-Data"] == "from-hash"
    assert captured["Content-Type"] == "application/json"


def test_fetch_api_surfaces_payload_error() -> None:
    """When the API responds 200 with a structured error envelope the
    helper must throw so callers' catch blocks fire.
    """
    threw = _evaluate("""
        ctx.fetch = () => Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ error: { message: 'no funds' } }),
        });
        try {
            await DC.fetchAPI('/anything');
            return { threw: false };
        } catch (err) {
            return { threw: true, message: String(err.message) };
        }
    """)
    assert threw == {"threw": True, "message": "no funds"}


def test_fetch_api_throws_no_init_data_when_session_absent() -> None:
    """Root-cause guard (menu-button 401): when no initData can be resolved
    anywhere (tg.initData empty, no URL hash, no query), fetchAPI must throw a
    distinct NO_INIT_DATA error WITHOUT firing the doomed request — so the UI
    can tell "opened outside Telegram / launch delivered nothing" apart from a
    server-*rejected* session (wrong bot token), instead of conflating both as
    an opaque 'API 401'.
    """
    result = _evaluate("""
        let calls = 0;
        ctx.Telegram.WebApp.initData = '';
        ctx.location = { hash: '', search: '' };
        ctx.fetch = () => { calls += 1; return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ data: {} }) }); };
        try {
            await DC.fetchAPI('/wealth/overview');
            return { threw: false, calls };
        } catch (err) {
            return { threw: true, message: String(err.message), calls };
        }
    """)
    assert result == {"threw": True, "message": "NO_INIT_DATA", "calls": 0}


def test_fetch_api_throws_on_http_failure() -> None:
    """Non-2xx must surface as an Error with 'API <status>' so per-
    dashboard buildErrorMessage can map 401/422/404 to localized copy.
    """
    threw = _evaluate("""
        ctx.fetch = () => Promise.resolve({
            ok: false,
            status: 401,
            json: () => Promise.resolve({}),
        });
        try {
            await DC.fetchAPI('/x');
            return { threw: false };
        } catch (err) {
            return { threw: true, message: String(err.message) };
        }
    """)
    assert threw == {"threw": True, "message": "API 401"}
