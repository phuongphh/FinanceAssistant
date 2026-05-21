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

    function getTelegram() {
        return (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) || null;
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
        return new Intl.NumberFormat('vi-VN').format(Math.round(amount)) + 'đ';
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
        const tg = getTelegram();
        const controller = new AbortController();
        const tid = setTimeout(() => controller.abort(), 12000);
        const headers = { 'Content-Type': 'application/json' };
        if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        try {
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
        formatDate,
        resolveDateFormat,
    };
})();
