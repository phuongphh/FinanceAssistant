// Node smoke harness for the static dashboard IIFE bundles.
//
// Loads a dashboard JS file inside a Node `vm` sandbox with a minimal
// `window`/`document`/`Telegram.WebApp`/`fetch`/`Chart` stub. Reports
// whether the IIFE (or DOMContentLoaded bootstrap, for cashflow) ran
// without throwing and whether it issued at least one network request
// — the proof that the bootstrap reached its initial `renderDashboard`
// call. This is the test that would have caught the Temporal Dead Zone
// bug in expense_dashboard.js where init silently aborted before the
// first fetch.
//
// Invoked from backend/tests/test_dashboard_init_smoke.py via
// subprocess. Exit 0 + JSON on the last stdout line on success;
// exit 1 + JSON describing the throw on failure.

'use strict';

const fs = require('fs');
const vm = require('vm');
const path = require('path');

function makeElement(id) {
    const noop = () => {};
    const el = {
        id: id || '',
        hidden: false,
        disabled: false,
        innerHTML: '',
        textContent: '',
        value: '',
        src: '',
        href: '',
        dataset: {},
        style: { setProperty: noop, display: '' },
        classList: {
            add: noop,
            remove: noop,
            toggle: noop,
            contains: () => false,
        },
        children: [],
        childNodes: [],
        addEventListener: noop,
        removeEventListener: noop,
        setAttribute: noop,
        removeAttribute: noop,
        querySelector: () => null,
        querySelectorAll: () => [],
        appendChild: noop,
        removeChild: noop,
        replaceChildren: noop,
        focus: noop,
        click: noop,
        getContext: () => ({
            clearRect: noop, fillRect: noop, beginPath: noop, arc: noop,
            stroke: noop, fill: noop, moveTo: noop, lineTo: noop,
            measureText: () => ({ width: 0 }),
        }),
        closest: () => null,
        parentElement: null,
    };
    return el;
}

function makeContext() {
    const fetchCalls = [];
    const documentListeners = Object.create(null);

    const documentStub = {
        getElementById: (id) => makeElement(id),
        querySelector: () => null,
        querySelectorAll: () => [],
        createElement: (tag) => makeElement(tag),
        addEventListener: (event, fn) => {
            (documentListeners[event] = documentListeners[event] || []).push(fn);
        },
        removeEventListener: () => {},
        hidden: false,
        body: makeElement('body'),
        documentElement: makeElement('html'),
        readyState: 'complete',
    };

    const tgWebApp = {
        ready: () => {},
        expand: () => {},
        close: () => {},
        themeParams: {},
        initData: '',
        initDataUnsafe: { user: { language_code: 'vi' } },
        showAlert: () => {},
        showConfirm: (_msg, cb) => { if (cb) cb(false); },
        sendData: () => {},
        BackButton: { show: () => {}, hide: () => {}, onClick: () => {} },
        MainButton: { show: () => {}, hide: () => {}, setText: () => {}, onClick: () => {} },
    };

    const sessionStorage = {
        _store: Object.create(null),
        getItem(k) { return Object.prototype.hasOwnProperty.call(this._store, k) ? this._store[k] : null; },
        setItem(k, v) { this._store[k] = String(v); },
        removeItem(k) { delete this._store[k]; },
        clear() { this._store = Object.create(null); },
    };

    // Build a single sandbox object that is both `window` and `globalThis`
    // — this matches browser semantics closely enough for the IIFE
    // bootstrap path, which is all this smoke test exercises.
    const ctx = {};
    ctx.window = ctx;
    ctx.self = ctx;
    ctx.globalThis = ctx;

    ctx.console = {
        log: (...args) => process.stderr.write('[js:log] ' + args.join(' ') + '\n'),
        error: (...args) => process.stderr.write('[js:error] ' + args.join(' ') + '\n'),
        warn: (...args) => process.stderr.write('[js:warn] ' + args.join(' ') + '\n'),
        info: (...args) => process.stderr.write('[js:info] ' + args.join(' ') + '\n'),
        debug: () => {},
    };
    ctx.document = documentStub;
    ctx.location = { href: 'http://localhost/', search: '', pathname: '/', reload: () => {} };
    ctx.sessionStorage = sessionStorage;
    ctx.localStorage = sessionStorage;
    ctx.confirm = () => false;
    ctx.alert = () => {};
    ctx.Telegram = { WebApp: tgWebApp };
    ctx.addEventListener = () => {};
    ctx.removeEventListener = () => {};

    ctx.setTimeout = (fn, ms) => setTimeout(fn, Math.min(Math.max(ms | 0, 0), 50));
    ctx.clearTimeout = (id) => clearTimeout(id);
    ctx.setInterval = (fn, ms) => setInterval(fn, ms);
    ctx.clearInterval = (id) => clearInterval(id);
    ctx.requestAnimationFrame = (fn) => setTimeout(fn, 16);
    ctx.cancelAnimationFrame = (id) => clearTimeout(id);

    ctx.URLSearchParams = URLSearchParams;
    ctx.URL = URL;
    ctx.AbortController = AbortController;
    ctx.AbortSignal = AbortSignal;
    ctx.fetch = (url, opts) => {
        fetchCalls.push({ url: String(url), opts: opts || null });
        return Promise.resolve({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: { get: () => null },
            json: () => Promise.resolve({ data: {} }),
            text: () => Promise.resolve(''),
        });
    };

    ctx.Chart = class FakeChart {
        constructor() {}
        destroy() {}
        update() {}
        resize() {}
    };

    ctx.performance = { now: () => 0 };

    // Bind language built-ins straight from the host realm.
    [
        'Object', 'Array', 'String', 'Number', 'Boolean', 'Symbol', 'Map',
        'Set', 'WeakMap', 'WeakSet', 'Promise', 'Date', 'RegExp', 'Error',
        'TypeError', 'ReferenceError', 'RangeError', 'SyntaxError', 'Math',
        'JSON', 'parseFloat', 'parseInt', 'isNaN', 'isFinite',
        'encodeURIComponent', 'decodeURIComponent', 'encodeURI', 'decodeURI',
        'Intl', 'Reflect', 'Proxy',
    ].forEach((name) => { ctx[name] = globalThis[name]; });

    return { ctx, fetchCalls, documentListeners };
}

async function run(target) {
    const source = fs.readFileSync(target, 'utf8');
    const { ctx, fetchCalls, documentListeners } = makeContext();
    vm.createContext(ctx);

    // Mirror the production load order: dashboard_common.js (shared
    // helpers exposed on window.DashboardCommon) is loaded by every
    // template before the dashboard-specific bundle. Skip when the
    // target IS dashboard_common.js itself, or for any file that
    // doesn't reference DashboardCommon (eg. legacy bundles that
    // haven't been refactored to use shared helpers).
    const COMMON = path.join(path.dirname(target), 'dashboard_common.js');
    if (
        target !== COMMON
        && fs.existsSync(COMMON)
        && source.includes('DashboardCommon')
    ) {
        try {
            vm.runInContext(fs.readFileSync(COMMON, 'utf8'), ctx, {
                filename: 'dashboard_common.js',
                timeout: 5000,
            });
        } catch (err) {
            return {
                ok: false,
                error: 'dashboard_common.js failed to load: ' + String(err.message || err),
                stack: err.stack ? String(err.stack).split('\n').slice(0, 4).join(' | ') : null,
                domContentLoadedErrors: [],
                fetchCalls: 0,
                urls: [],
            };
        }
    }

    const errors = [];
    let initError = null;
    try {
        vm.runInContext(source, ctx, { filename: path.basename(target), timeout: 5000 });
    } catch (err) {
        initError = err;
    }

    // Cashflow dashboard bootstraps via DOMContentLoaded instead of IIFE.
    // An uncaught throw inside one of those callbacks aborts the rest of
    // the bootstrap chain — same failure shape as the IIFE TDZ bug this
    // harness was built to catch — so it must count as a failure, not
    // just a logged side-channel error.
    if (!initError && documentListeners.DOMContentLoaded) {
        for (const fn of documentListeners.DOMContentLoaded) {
            try {
                await fn();
            } catch (err) {
                errors.push(String(err && err.message || err));
            }
        }
    }

    // Let microtasks settle so any sync-fired fetch resolves and the
    // dashboard's own try/catch can swallow downstream render errors.
    await new Promise((resolve) => setTimeout(resolve, 80));

    const ok = !initError && errors.length === 0;
    return {
        ok,
        error: initError
            ? String(initError.message || initError)
            : (errors[0] || null),
        stack: initError && initError.stack ? String(initError.stack).split('\n').slice(0, 4).join(' | ') : null,
        domContentLoadedErrors: errors,
        fetchCalls: fetchCalls.length,
        urls: fetchCalls.map((c) => c.url).slice(0, 5),
    };
}

const target = process.argv[2];
if (!target) {
    process.stderr.write('Usage: node js_dashboard_smoke.cjs <dashboard.js>\n');
    process.exit(2);
}

run(target).then((result) => {
    process.stdout.write(JSON.stringify(result) + '\n');
    process.exit(result.ok ? 0 : 1);
}).catch((err) => {
    process.stdout.write(JSON.stringify({ ok: false, error: String(err && err.message || err), fetchCalls: 0, urls: [] }) + '\n');
    process.exit(1);
});
