/**
 * Phase 4B Epic 3 — Cashflow Dashboard JS
 *
 * Architecture:
 * - Reads initData from Telegram.WebApp for auth
 * - GET /api/cashflow/forecast — forecast + alert flags
 * - GET /api/cashflow/patterns — confirmed patterns
 * - PATCH /api/cashflow/patterns/:id — inline edit
 * - POST /api/cashflow/patterns — add manual pattern
 *
 * No framework: vanilla JS + async/await.
 * Target: Telegram Mini App WebView (Chromium-based, modern APIs available).
 */

"use strict";

const tg = window.Telegram?.WebApp;
const API_BASE = "";     // same origin as the HTML

// Telegram injects launch params into the URL HASH fragment
// (#tgWebAppData=…); when telegram-web-app.js hasn't populated
// tg.initData yet, the hash is the authoritative fallback so the
// request still carries auth instead of triggering a 401. This bundle
// is standalone (no dashboard_common.js), so the helper is inlined.
function resolveInitData() {
    if (tg?.initData) return tg.initData;
    const fromHash = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
    const fromSearch = new URLSearchParams(window.location.search || "");
    return fromHash.get("tgWebAppData") || fromHash.get("initData")
        || fromSearch.get("tgWebAppData") || fromSearch.get("initData") || "";
}

const HEADERS = () => ({
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": resolveInitData(),
});

// ── Bootstrap ──────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    tg?.expand();
    tg?.ready();
    await loadAll();
    document.getElementById("retry-btn")?.addEventListener("click", loadAll);
    document.getElementById("add-pattern-btn")?.addEventListener("click", showAddModal);
    document.getElementById("add-cancel")?.addEventListener("click", hideAddModal);
    document.getElementById("add-save")?.addEventListener("click", saveNewPattern);
    document.getElementById("edit-cancel")?.addEventListener("click", hideEditModal);
    document.getElementById("edit-save")?.addEventListener("click", saveEdit);
    document.getElementById("alert-detail-btn")?.addEventListener("click", scrollToPatterns);
});

async function loadAll() {
    showSection("loading");
    try {
        const [forecast, patterns] = await Promise.all([
            fetchJSON("/api/cashflow/forecast"),
            fetchJSON("/api/cashflow/patterns"),
        ]);
        renderForecast(forecast);
        renderPatterns(patterns);
        renderAlertBanner(forecast);
        showSection("content");
    } catch (err) {
        console.error("cashflow load failed:", err);
        document.getElementById("error-message").textContent =
            err.status === 404
                ? "Chưa có dữ liệu dự báo — Bé Tiền đang cập nhật."
                : "Không tải được dữ liệu. Vui lòng thử lại.";
        showSection("error");
    }
}

// ── Render ─────────────────────────────────────────────────────────────────

function renderForecast(forecast) {
    if (!forecast || !forecast.monthly_data?.length) return;

    // Chart — request a server-rendered PNG (the chart.py endpoint)
    // Fall back gracefully if the endpoint is slow or unavailable.
    const chartEl = document.getElementById("cashflow-chart");
    const fallbackEl = document.getElementById("chart-fallback");
    chartEl.src = `/api/cashflow/chart?t=${Date.now()}`;
    chartEl.addEventListener("error", () => {
        chartEl.hidden = true;
        fallbackEl.hidden = false;
        fallbackEl.textContent = "Biểu đồ tạm thời không khả dụng.";
    });

    // Monthly summary cards
    const container = document.getElementById("month-cards");
    container.innerHTML = "";
    for (const m of forecast.monthly_data) {
        const d = new Date(m.month + "T00:00:00");
        const label = `Tháng ${d.getMonth() + 1}/${d.getFullYear()}`;
        const net = parseFloat(m.net);
        const balEom = parseFloat(m.balance_eom);
        const netSign = net >= 0 ? "+" : "−";
        const netClass = net >= 0 ? "net-positive" : "net-negative";

        const card = document.createElement("div");
        card.className = "month-card";
        card.innerHTML = `
            <div class="month-label">${label}</div>
            <div class="net-amount ${netClass}">${netSign}${fmtMoney(Math.abs(net))}</div>
            <div class="balance-label">Số dư cuối tháng</div>
            <div class="balance-amount">${fmtMoney(balEom)}</div>
        `;
        container.appendChild(card);
    }
}

function renderAlertBanner(forecast) {
    const banner = document.getElementById("alert-banner");
    const alertText = document.getElementById("alert-text");
    if (!forecast?.low_balance_risk || !forecast.low_balance_month) {
        banner.hidden = true;
        return;
    }
    const d = new Date(forecast.low_balance_month + "T00:00:00");
    const monthLabel = `Tháng ${d.getMonth() + 1}/${d.getFullYear()}`;

    // Find balance for that month
    const monthData = forecast.monthly_data.find(m => m.month === forecast.low_balance_month);
    const balance = monthData ? parseFloat(monthData.balance_eom) : 0;
    const threshold = forecast.low_balance_threshold
        ? parseFloat(forecast.low_balance_threshold) : null;

    let text = `${monthLabel}: số dư dự báo ${fmtMoney(balance)}`;
    if (threshold) text += ` (dưới ngưỡng an toàn ${fmtMoney(threshold)})`;
    alertText.textContent = text;
    banner.hidden = false;
}

function renderPatterns(patterns) {
    const incomeList = document.getElementById("income-list");
    const expenseList = document.getElementById("expense-list");
    const noIncome = document.getElementById("no-income");
    const noExpense = document.getElementById("no-expense");

    incomeList.innerHTML = "";
    expenseList.innerHTML = "";

    const incomes = patterns.filter(p => p.pattern_type === "income");
    const expenses = patterns.filter(p => p.pattern_type === "expense");

    noIncome.hidden = incomes.length > 0;
    noExpense.hidden = expenses.length > 0;

    for (const p of incomes) {
        incomeList.appendChild(patternCard(p));
    }
    for (const p of expenses) {
        expenseList.appendChild(patternCard(p));
    }
}

function patternCard(p) {
    const div = document.createElement("div");
    div.className = `pattern-item pattern-${p.pattern_type}`;
    div.dataset.id = p.id;
    const icon = p.pattern_type === "income" ? "💰" : "💸";
    const dayStr = p.typical_day ? `ngày ${p.typical_day} hàng tháng` : "hàng tháng";
    div.innerHTML = `
        <span class="pattern-icon">${icon}</span>
        <div class="pattern-info">
            <div class="pattern-name">${escHtml(p.name || p.description || "—")}</div>
            <div class="pattern-meta">${dayStr}</div>
        </div>
        <span class="pattern-amount">${fmtMoney(parseFloat(p.expected_amount))}</span>
    `;
    div.addEventListener("click", () => showEditModal(p));
    return div;
}

// ── Edit modal ─────────────────────────────────────────────────────────────

let _editingPatternId = null;

function showEditModal(pattern) {
    _editingPatternId = pattern.id;
    document.getElementById("edit-modal-title").textContent =
        `Sửa: ${pattern.name || pattern.description || "Khoản định kỳ"}`;
    document.getElementById("edit-amount").value = parseFloat(pattern.expected_amount);
    document.getElementById("edit-day").value = pattern.typical_day || "";
    document.getElementById("edit-modal").hidden = false;
}

function hideEditModal() {
    document.getElementById("edit-modal").hidden = true;
    _editingPatternId = null;
}

async function saveEdit() {
    if (!_editingPatternId) return;
    const amount = parseFloat(document.getElementById("edit-amount").value);
    const day = parseInt(document.getElementById("edit-day").value) || null;
    if (!amount || amount < 1000) {
        tg?.showAlert("Số tiền phải ≥ 1,000 đ.");
        return;
    }
    try {
        await fetchJSON(`/api/cashflow/patterns/${_editingPatternId}`, {
            method: "PATCH",
            body: JSON.stringify({
                expected_amount: amount,
                expected_day_of_month: day,
            }),
        });
        hideEditModal();
        await loadAll();
    } catch {
        tg?.showAlert("Cập nhật thất bại. Thử lại sau.");
    }
}

// ── Add modal ──────────────────────────────────────────────────────────────

function showAddModal() {
    document.getElementById("add-modal").hidden = false;
}

function hideAddModal() {
    document.getElementById("add-modal").hidden = true;
}

async function saveNewPattern() {
    const type = document.getElementById("add-type").value;
    const name = document.getElementById("add-name").value.trim();
    const amount = parseFloat(document.getElementById("add-amount").value);
    const day = parseInt(document.getElementById("add-day").value) || null;

    if (!name) { tg?.showAlert("Vui lòng nhập tên khoản."); return; }
    if (!amount || amount < 1000) { tg?.showAlert("Số tiền phải ≥ 1,000 đ."); return; }

    try {
        await fetchJSON("/api/cashflow/patterns", {
            method: "POST",
            body: JSON.stringify({
                pattern_type: type,
                name,
                expected_amount: amount,
                expected_day_of_month: day,
            }),
        });
        hideAddModal();
        await loadAll();
    } catch {
        tg?.showAlert("Thêm khoản thất bại. Thử lại sau.");
    }
}

// ── Utilities ──────────────────────────────────────────────────────────────

function showSection(id) {
    for (const s of ["loading", "error", "content"]) {
        const el = document.getElementById(s);
        if (el) el.hidden = (s !== id);
    }
}

function scrollToPatterns() {
    document.getElementById("income-section")?.scrollIntoView({ behavior: "smooth" });
}

async function fetchJSON(url, options = {}) {
    const res = await fetch(API_BASE + url, {
        ...options,
        headers: { ...HEADERS(), ...(options.headers || {}) },
    });
    if (!res.ok) {
        const err = new Error(`HTTP ${res.status}`);
        err.status = res.status;
        throw err;
    }
    return res.json();
}

// Round only to nearest 1,000đ — same rule as DashboardCommon.formatMoneyShort.
function fmtMoney(v) {
    if (isNaN(v)) return "—";
    const value = Number(v) || 0;
    const sign = value < 0 ? '-' : '';
    const raw = Math.abs(value);
    if (raw < 1) return '0đ';
    if (raw < 1_000) return sign + Math.round(raw) + 'đ';
    const thousandsTotal = Math.round(raw / 1_000);
    if (thousandsTotal < 1_000) return sign + thousandsTotal + 'k';
    if (thousandsTotal < 1_000_000) {
        const millions = Math.floor(thousandsTotal / 1_000);
        const thousands = thousandsTotal % 1_000;
        if (thousands === 0) return sign + millions + 'tr';
        return sign + millions + 'tr' + String(thousands).padStart(3, '0');
    }
    const trTotal = Math.round(raw / 1_000_000);
    const billions = Math.floor(trTotal / 1_000);
    const millions = trTotal % 1_000;
    if (millions === 0) return sign + billions + ' tỷ';
    return sign + billions + 'tỷ' + String(millions).padStart(3, '0');
}

function escHtml(s) {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
