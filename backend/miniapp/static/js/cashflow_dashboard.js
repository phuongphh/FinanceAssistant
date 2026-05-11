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
const HEADERS = () => ({
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": tg?.initData ?? "",
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

function fmtMoney(v) {
    if (isNaN(v)) return "—";
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)} tỷ`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} tr`;
    if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(0)}k`;
    return v.toFixed(0) + " đ";
}

function escHtml(s) {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
