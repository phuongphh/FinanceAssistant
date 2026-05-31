// Shared helpers for Telegram Mini App dashboard bundles.
//
// Loaded once per page via <script src="…dashboard_common.js"></script>
// BEFORE the dashboard-specific bundle. The browser caches it across
// dashboard navigations (expense → wealth → twin), so the second open
// avoids re-parsing 150 lines of duplicated helpers.
//
// Only truly identical, side-effect-free helpers live here. Dashboard-
// local concerns — `showState` (closes over `els`), `buildErrorMessage`
// (each dashboard has different 4xx surface), `reportLoaded` (per-page
// debounce + timing state), `handleInitFailure` (intentional isolation
// per the bootstrap-guard contract) — stay in their respective bundles.
//
// Surface: `window.DashboardCommon` namespace. Dashboards destructure
// at the top of their IIFE so call sites stay unchanged.
(function () {
    'use strict';
    let resolvedInitData = null;

    function getTelegram() {
        return (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) || null;
    }

    // Telegram injects launch params into the URL HASH fragment
    // (#tgWebAppData=…&tgWebAppVersion=…), NOT the query string. When
    // telegram-web-app.js hasn't populated `tg.initData` yet (slow CDN,
    // cache miss), the hash is the authoritative fallback. We also check
    // `search` for the rare desktop/manual-link case where a host appends
    // `?tgWebAppData=` or `?initData=` directly.
    function resolveInitDataFromUrl() {
        if (typeof window === 'undefined') return '';
        const hash = (window.location.hash || '').replace(/^#/, '');
        const hashParams = new URLSearchParams(hash);
        const fromHash = hashParams.get('tgWebAppData') || hashParams.get('initData');
        if (fromHash) return fromHash;
        const qs = new URLSearchParams(window.location.search || '');
        return qs.get('tgWebAppData') || qs.get('initData') || '';
    }

    async function resolveInitData(maxWaitMs = 250) {
        if (resolvedInitData) return resolvedInitData;
        const startedAt = Date.now();
        while ((Date.now() - startedAt) <= maxWaitMs) {
            const tg = getTelegram();
            if (tg && tg.initData) {
                resolvedInitData = tg.initData;
                return resolvedInitData;
            }
            await new Promise((resolve) => setTimeout(resolve, 25));
        }
        resolvedInitData = resolveInitDataFromUrl();
        return resolvedInitData;
    }

    function applyTheme(theme) {
        if (!theme || typeof document === 'undefined') return;
        const root = document.documentElement;
        const map = {
            '--bg-color': theme.bg_color,
            '--text-color': theme.text_color,
            '--text-muted': theme.hint_color,
            '--card-bg': theme.secondary_bg_color,
            '--primary': theme.button_color,
            '--primary-text': theme.button_text_color,
        };
        for (const [prop, value] of Object.entries(map)) {
            if (value) root.style.setProperty(prop, value);
        }
    }

    // Canonical 2-decimal precision for billions ("1.23 tỷ"). The legacy
    // dashboard.js used 1-decimal; aligning to this is a precision boost,
    // not a regression — same rounding rule across all dashboards.
    function formatMoneyShort(amount) {
        const abs = Math.abs(amount);
        if (abs >= 1_000_000_000) {
            return (amount / 1_000_000_000).toFixed(2).replace(/\.?0+$/, '') + ' tỷ';
        }
        if (abs >= 1_000_000) {
            return (amount / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'tr';
        }
        if (abs >= 1_000) return Math.round(amount / 1_000) + 'k';
        return Math.round(amount) + 'đ';
    }

    function formatMoneyFull(amount) {
        return new Intl.NumberFormat('en-US').format(Math.round(amount)) + 'đ';
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // 12s watchdog matches the existing per-dashboard contract: long
    // enough for cold market-data fetches on a poor 3G uplink, short
    // enough that the retry button fires before the user closes the app.
    async function fetchAPI(endpoint, options = {}) {
        const controller = new AbortController();
        const tid = setTimeout(() => controller.abort(), 12000);
        const headers = { 'Content-Type': 'application/json' };
        try {
            const initData = await resolveInitData();
            // No initData (tg.initData empty AND no URL-hash/query fallback)
            // means the page carries no Telegram session — opened in a plain
            // browser, or a launch that delivered nothing. The server would
            // 401, but that 401 is indistinguishable from a *rejected* session
            // (wrong bot token). Throw a distinct error so the UI can say
            // "open from inside Telegram" instead of conflating both as one
            // opaque "phiên không hợp lệ".
            if (!initData) throw new Error('NO_INIT_DATA');
            headers['X-Telegram-Init-Data'] = initData;
            const response = await fetch('/miniapp/api' + endpoint, {
                ...options,
                headers: { ...headers, ...(options.headers || {}) },
                signal: controller.signal,
            });
            if (!response.ok) throw new Error('API ' + response.status);
            const payload = await response.json();
            if (payload.error) throw new Error(payload.error.message || 'API error');
            return payload.data;
        } finally {
            clearTimeout(tid);
        }
    }

    // Build headers for a POST mutation with the resolved initData
    // attached. Mirrors fetchAPI's auth handling so a mutation can't omit
    // the header that the page-load GET sent — critical when the page
    // recovered initData from the URL hash (empty tg.initData).
    async function authHeaders(extra = {}) {
        const headers = { 'Content-Type': 'application/json', ...extra };
        const initData = await resolveInitData();
        if (initData) headers['X-Telegram-Init-Data'] = initData;
        return headers;
    }

    const DATE_FORMAT_BY_LANGUAGE = {
        vi: { locale: 'vi-VN', options: { day: '2-digit', month: '2-digit', year: 'numeric' } },
        en: { locale: 'en-GB', options: { day: '2-digit', month: '2-digit', year: 'numeric' } },
    };

    function resolveDateFormat() {
        const tg = getTelegram();
        const lang = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code || 'vi').toLowerCase();
        return DATE_FORMAT_BY_LANGUAGE[lang] || DATE_FORMAT_BY_LANGUAGE[lang.split('-')[0]] || DATE_FORMAT_BY_LANGUAGE.vi;
    }

    // Contract: `iso` is YYYY-MM-DD. Appending T00:00:00 forces local-tz
    // interpretation so a transaction logged on 2025-12-31 in Hanoi
    // doesn't render as 2025-12-30 in a UTC-rendering environment.
    function formatDate(iso) {
        if (!iso) return '--/--/----';
        const d = new Date(iso + 'T00:00:00');
        const fmt = resolveDateFormat();
        return d.toLocaleDateString(fmt.locale, fmt.options);
    }

    window.DashboardCommon = {
        applyTheme,
        formatMoneyShort,
        formatMoneyFull,
        escapeHtml,
        fetchAPI,
        resolveInitData,
        authHeaders,
        formatDate,
        resolveDateFormat,
    };
})();
