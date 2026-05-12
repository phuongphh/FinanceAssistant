// Expense dashboard — mirrors wealth_dashboard.js structure for visual/UX
// consistency. One bundled `/api/expense-dashboard/overview` round-trip
// loads hero total, category breakdown (pie + list), 30-day trend, and
// the month's expense rows. Add/edit/delete happens inline via a modal
// (no chat round-trip) because expense edits are simple compared to the
// type-specific asset wizard.
(function () {
    'use strict';

    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        applyTheme(tg.themeParams || {});
    }

    const els = {
        loading: document.getElementById('loading'),
        error: document.getElementById('error'),
        errorMessage: document.getElementById('error-message'),
        content: document.getElementById('content'),
        retryBtn: document.getElementById('retry-btn'),
        emptyState: document.getElementById('empty-state'),
        breakdownSection: document.getElementById('breakdown-section'),
        trendSection: document.getElementById('trend-section'),
        expensesSection: document.getElementById('expenses-section'),
        totalSpent: document.getElementById('total-spent'),
        changeIcon: document.getElementById('change-icon'),
        changeAmount: document.getElementById('change-amount'),
        changePeriod: document.getElementById('change-period'),
        monthPill: document.getElementById('month-pill'),
        txnCount: document.getElementById('txn-count'),
        breakdownList: document.getElementById('breakdown-list'),
        pieChart: document.getElementById('pie-chart'),
        trendChart: document.getElementById('trend-chart'),
        trendHeading: document.getElementById('trend-heading'),
        expensesList: document.getElementById('expenses-list'),
        addExpenseBtn: document.getElementById('add-expense-btn'),
        addFirstExpenseBtn: document.getElementById('add-first-expense-btn'),
        modal: document.getElementById('expense-modal'),
        modalTitle: document.getElementById('expense-modal-title'),
        modalAmount: document.getElementById('expense-amount'),
        modalCategory: document.getElementById('expense-category'),
        modalDate: document.getElementById('expense-date'),
        modalNote: document.getElementById('expense-note'),
        modalPayment: document.getElementById('expense-payment'),
        modalDelete: document.getElementById('expense-delete-btn'),
        modalCancel: document.getElementById('expense-cancel-btn'),
        modalSave: document.getElementById('expense-save-btn'),
    };

    // Keep in sync with backend/config/categories.py. Inlined to avoid
    // an extra round-trip on first paint — the canonical labels arrive
    // from the API for each row, so this list only feeds the form select.
    const CATEGORIES = [
        ['food', '🍜 Ăn uống'],
        ['transport', '🚗 Di chuyển'],
        ['housing', '🏠 Nhà cửa'],
        ['shopping', '👕 Mua sắm'],
        ['health', '💊 Sức khỏe'],
        ['education', '📚 Giáo dục'],
        ['entertainment', '🎮 Giải trí'],
        ['utility', '⚡ Tiện ích'],
        ['investment', '📊 Đầu tư'],
        ['saving', '💰 Tiết kiệm'],
        ['gift', '🎁 Quà tặng'],
        ['transfer', '🔄 Chuyển khoản'],
        ['other', '📌 Khác'],
    ];

    let pieChart = null;
    let trendChart = null;
    let lastOverview = null;
    let editingExpenseId = null;
    const pageStartedAt = performance.now();
    let loadBeaconSent = false;
    const SOURCE = new URLSearchParams(window.location.search).get('source');

    initModalForm();
    els.retryBtn.addEventListener('click', renderDashboard);
    els.addExpenseBtn.addEventListener('click', () => openModal());
    els.addFirstExpenseBtn.addEventListener('click', () => openModal());
    els.expensesList.addEventListener('click', onExpenseRowClick);
    els.modalCancel.addEventListener('click', closeModal);
    els.modalSave.addEventListener('click', onSave);
    els.modalDelete.addEventListener('click', onDelete);
    els.modal.addEventListener('click', (e) => {
        if (e.target === els.modal) closeModal();
    });

    renderDashboard();

    // -- Theme + utils ----------------------------------------------------

    function applyTheme(theme) {
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

    function formatMonthLabel(monthKey) {
        if (!monthKey) return '';
        const [year, month] = monthKey.split('-');
        return `Tháng ${parseInt(month, 10)}/${year}`;
    }

    function formatDate(iso) {
        if (!iso) return '--/--';
        const d = new Date(iso + 'T00:00:00');
        return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' });
    }

    async function fetchAPI(endpoint, options = {}) {
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

    // -- Top-level render -------------------------------------------------

    async function renderDashboard() {
        showState('loading');
        try {
            const params = new URLSearchParams();
            if (SOURCE) params.set('source', SOURCE);
            const qs = params.toString() ? `?${params.toString()}` : '';
            const data = await fetchAPI('/expense-dashboard/overview' + qs);
            lastOverview = data;

            renderHero(data);
            const isEmpty = (data.transaction_count || 0) === 0;
            toggleSections(isEmpty);

            if (!isEmpty) {
                renderPie(data.breakdown || []);
                renderBreakdownList(data.breakdown || []);
                renderTrend(data.daily_trend || []);
                renderExpenses(data.expenses || []);
            }

            showState('content');
            reportLoaded();
        } catch (err) {
            console.error(err);
            els.errorMessage.textContent = buildErrorMessage(err);
            showState('error');
            if (tg && tg.showAlert) tg.showAlert('Không tải được dữ liệu, thử lại nhé.');
        }
    }

    function renderHero(data) {
        els.totalSpent.textContent = formatMoneyFull(data.total_spent || 0);
        els.monthPill.textContent = formatMonthLabel(data.month);
        els.txnCount.textContent = `${data.transaction_count || 0} giao dịch`;

        // For expenses, "up" (spending more) is bad → red, "down" → green.
        const change = data.change_month || { amount: 0, pct: 0 };
        const pct = Number(change.pct || 0);
        const amount = Number(change.amount || 0);
        const tolerance = 0.05;
        let direction = 'flat';
        let icon = '➖';
        let sign = '';
        if (pct > tolerance) {
            direction = 'down'; icon = '📈'; sign = '+';
        } else if (pct < -tolerance) {
            direction = 'up'; icon = '📉'; sign = '−';
        }
        els.changeIcon.textContent = icon;
        const absAmount = formatMoneyShort(Math.abs(amount));
        const absPct = Math.abs(pct).toFixed(1);
        els.changeAmount.textContent =
            direction === 'flat'
                ? '0₫ (0.0%)'
                : `${sign}${absAmount} (${sign}${absPct}%)`;
        els.changePeriod.textContent = 'so với tháng trước';
        const heroChange = els.changeIcon.parentElement;
        if (heroChange) {
            heroChange.classList.remove('up', 'down', 'flat');
            heroChange.classList.add(direction);
        }
    }

    function toggleSections(isEmpty) {
        els.emptyState.hidden = !isEmpty;
        els.breakdownSection.hidden = isEmpty;
        els.trendSection.hidden = isEmpty;
        els.expensesSection.hidden = isEmpty;
    }

    // -- Pie / breakdown --------------------------------------------------

    function renderPie(breakdown) {
        if (pieChart) pieChart.destroy();
        if (!breakdown.length) {
            els.pieChart.style.display = 'none';
            return;
        }
        els.pieChart.style.display = 'block';
        pieChart = new Chart(els.pieChart, {
            type: 'doughnut',
            data: {
                labels: breakdown.map((b) => b.name),
                datasets: [{
                    data: breakdown.map((b) => b.amount),
                    backgroundColor: breakdown.map((b) => b.color),
                    borderWidth: 2,
                    borderColor: '#ffffff',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` ${ctx.label}: ${formatMoneyShort(ctx.parsed)}`,
                        },
                    },
                },
            },
        });
    }

    function renderBreakdownList(breakdown) {
        if (!breakdown.length) {
            els.breakdownList.innerHTML = '';
            return;
        }
        const total = breakdown.reduce((s, b) => s + (b.amount || 0), 0) || 1;
        els.breakdownList.innerHTML = breakdown.map((b) => {
            const pct = ((b.amount || 0) / total) * 100;
            return `
                <div class="breakdown-row">
                    <span class="breakdown-icon">${escapeHtml(b.emoji)}</span>
                    <span class="breakdown-label">${escapeHtml(b.name)}</span>
                    <span class="breakdown-value">${formatMoneyShort(b.amount)}</span>
                    <span class="breakdown-pct">${pct.toFixed(0)}%</span>
                </div>
            `;
        }).join('');
    }

    // -- Trend ------------------------------------------------------------

    function renderTrend(daily) {
        if (trendChart) trendChart.destroy();
        if (!daily.length) {
            els.trendChart.style.display = 'none';
            return;
        }
        els.trendChart.style.display = 'block';
        trendChart = new Chart(els.trendChart, {
            type: 'line',
            data: {
                labels: daily.map((d) => d.date.slice(5)),
                datasets: [{
                    data: daily.map((d) => d.amount),
                    borderColor: '#FF6B6B',
                    backgroundColor: 'rgba(255,107,107,0.15)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` ${formatMoneyShort(ctx.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { callback: (v) => formatMoneyShort(v) },
                    },
                    x: { ticks: { maxTicksLimit: 6 } },
                },
            },
        });
    }

    // -- Expenses list ----------------------------------------------------

    function renderExpenses(items) {
        if (!items.length) {
            els.expensesList.innerHTML = '<p class="empty-state">Chưa có giao dịch nào tháng này 🌱</p>';
            return;
        }
        els.expensesList.innerHTML = items.map((it) => {
            const title = it.merchant || it.note || it.category_label || 'Chi tiêu';
            return `
                <div class="expense-row" data-id="${escapeHtml(it.id)}">
                    <span class="expense-icon">${escapeHtml(it.category_emoji || '📌')}</span>
                    <div class="expense-info">
                        <div class="expense-title">${escapeHtml(title)}</div>
                        <div class="expense-meta">${formatDate(it.expense_date)} · ${escapeHtml(it.category_label || 'Chưa phân loại')}</div>
                    </div>
                    <div class="expense-amount">${formatMoneyShort(it.amount || 0)}</div>
                    <div class="expense-actions">
                        <button class="expense-action-btn expense-edit-btn" type="button" aria-label="Sửa ${escapeHtml(title)}">✏️</button>
                        <button class="expense-action-btn expense-delete-row-btn" type="button" aria-label="Xoá ${escapeHtml(title)}">🗑️</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    async function onExpenseRowClick(event) {
        const row = event.target.closest('.expense-row[data-id]');
        if (!row) return;
        const id = row.dataset.id;
        const item = (lastOverview?.expenses || []).find((x) => x.id === id);
        if (!item) return;

        if (event.target.closest('.expense-delete-row-btn')) {
            await onQuickDelete(item);
            return;
        }
        if (event.target.closest('.expense-edit-btn')) {
            openModal(item);
        }
    }

    async function onQuickDelete(item) {
        const title = item.merchant || item.note || item.category_label || 'chi tiêu này';
        const message = `Xoá "${title}"?\nThao tác này không thể hoàn tác.`;
        const confirmed = await new Promise((resolve) => {
            if (tg && tg.showConfirm) tg.showConfirm(message, resolve);
            else resolve(window.confirm(message));
        });
        if (!confirmed) return;
        try {
            await fetchAPI(`/expenses/${item.id}`, { method: 'DELETE' });
        } catch (_err) {
            if (tg && tg.showAlert) tg.showAlert('Không xoá được chi tiêu, thử lại nhé.');
            return;
        }
        await renderDashboard();
    }

    // -- Modal: add / edit / delete ---------------------------------------

    function initModalForm() {
        els.modalCategory.innerHTML = CATEGORIES.map(
            ([code, label]) => `<option value="${code}">${escapeHtml(label)}</option>`
        ).join('');
    }

    function openModal(item) {
        editingExpenseId = item?.id || null;
        els.modalTitle.textContent = editingExpenseId ? 'Sửa chi tiêu' : 'Thêm chi tiêu';
        els.modalAmount.value = item ? Math.round(item.amount || 0) : '';
        els.modalCategory.value = item?.category || 'other';
        els.modalDate.value = item?.expense_date || new Date().toISOString().slice(0, 10);
        els.modalNote.value = item?.merchant || item?.note || '';
        els.modalPayment.value = item?.payment_method || '';
        els.modalDelete.hidden = !editingExpenseId;
        els.modalSave.disabled = false;
        els.modalDelete.disabled = false;
        els.modal.hidden = false;
        setTimeout(() => els.modalAmount.focus(), 50);
    }

    function closeModal() {
        els.modal.hidden = true;
        editingExpenseId = null;
    }

    async function onSave() {
        const amount = parseFloat(els.modalAmount.value);
        if (!amount || amount < 1000) {
            if (tg && tg.showAlert) tg.showAlert('Số tiền phải từ 1.000đ.');
            else window.alert('Số tiền phải từ 1.000đ.');
            return;
        }
        const note = els.modalNote.value.trim();
        const body = {
            amount,
            category: els.modalCategory.value || 'other',
            expense_date: els.modalDate.value,
            note: note || null,
            merchant: note || null,
            payment_method: els.modalPayment.value.trim() || null,
        };
        els.modalSave.disabled = true;
        try {
            if (editingExpenseId) {
                await fetchAPI(`/expenses/${editingExpenseId}`, {
                    method: 'PATCH',
                    body: JSON.stringify(body),
                });
            } else {
                await fetchAPI('/expenses', {
                    method: 'POST',
                    body: JSON.stringify(body),
                });
            }
        } catch (_err) {
            els.modalSave.disabled = false;
            if (tg && tg.showAlert) tg.showAlert('Không lưu được, thử lại nhé.');
            return;
        }
        closeModal();
        await renderDashboard();
    }

    async function onDelete() {
        if (!editingExpenseId) return;
        const confirmed = await new Promise((resolve) => {
            const msg = 'Xoá chi tiêu này?\nThao tác không thể hoàn tác.';
            if (tg && tg.showConfirm) tg.showConfirm(msg, resolve);
            else resolve(window.confirm(msg));
        });
        if (!confirmed) return;
        els.modalDelete.disabled = true;
        try {
            await fetchAPI(`/expenses/${editingExpenseId}`, { method: 'DELETE' });
        } catch (_err) {
            els.modalDelete.disabled = false;
            if (tg && tg.showAlert) tg.showAlert('Không xoá được, thử lại nhé.');
            return;
        }
        closeModal();
        await renderDashboard();
    }

    // -- Misc -------------------------------------------------------------

    function showState(state) {
        els.loading.hidden = state !== 'loading';
        els.error.hidden = state !== 'error';
        els.content.hidden = state !== 'content';
    }

    function buildErrorMessage(err) {
        if (err && err.name === 'AbortError') return 'Kết nối quá chậm — thử lại nhé.';
        if (err && err.message === 'API 401') return 'Phiên đăng nhập Telegram không hợp lệ.';
        if (err && err.message === 'API 422') return 'Tham số không hợp lệ.';
        return 'Không tải được dữ liệu, thử lại nhé.';
    }

    function reportLoaded() {
        if (loadBeaconSent) return;
        loadBeaconSent = true;
        const loadTimeMs = Math.round(performance.now() - pageStartedAt);
        const headers = { 'Content-Type': 'application/json' };
        if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        fetch('/miniapp/api/events/loaded', {
            method: 'POST',
            headers,
            body: JSON.stringify({ load_time_ms: loadTimeMs, page: 'expense' }),
            keepalive: true,
        }).catch(() => { /* analytics best-effort */ });
    }
})();
