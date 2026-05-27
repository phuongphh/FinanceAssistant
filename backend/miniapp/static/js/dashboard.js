// Telegram Mini App — Dashboard v1
(function () {
    'use strict';

    // Shared helpers from /miniapp/static/js/dashboard_common.js — loaded
    // first via the template. Destructure at IIFE top so bindings exit
    // TDZ before any caller (per the smoke-harness contract).
    const { applyTheme, formatMoneyShort, formatMoneyFull, escapeHtml, fetchAPI, formatDate, authHeaders } = window.DashboardCommon;

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
        totalSpent: document.getElementById('total-spent'),
        transactionCount: document.getElementById('transaction-count'),
        monthLabel: document.getElementById('month-label'),
        categoryList: document.getElementById('category-list'),
        categoryChart: document.getElementById('category-chart'),
        trendChart: document.getElementById('trend-chart'),
        addExpenseBtn: document.getElementById('add-expense-btn'),
        expenseMonth: document.getElementById('expense-month'),
        expenseList: document.getElementById('expense-list'),
        expenseEmpty: document.getElementById('expense-empty'),
        expenseModal: document.getElementById('expense-modal'),
        expenseModalTitle: document.getElementById('expense-modal-title'),
        expenseAmount: document.getElementById('expense-amount'),
        expenseCategory: document.getElementById('expense-category'),
        expenseDate: document.getElementById('expense-date'),
        expenseNote: document.getElementById('expense-note'),
        expensePayment: document.getElementById('expense-payment'),
        expenseDelete: document.getElementById('expense-delete'),
        expenseCancel: document.getElementById('expense-cancel'),
        expenseSave: document.getElementById('expense-save'),
    };

    let categoryChart = null;
    let trendChart = null;
    const pageStartedAt = performance.now();
    let loadBeaconSent = false;
    let editingExpenseId = null;
    const CATEGORIES = [
        ['food', '🍜 Ăn uống'], ['transport', '🚗 Di chuyển'], ['housing', '🏠 Nhà cửa'],
        ['shopping', '👕 Mua sắm'], ['health', '💊 Sức khỏe'], ['education', '📚 Giáo dục'],
        ['entertainment', '🎮 Giải trí'], ['utility', '⚡ Tiện ích'], ['investment', '📊 Đầu tư'],
        ['saving', '💰 Tiết kiệm'], ['gift', '🎁 Quà tặng'], ['other', '📌 Chưa phân loại'],
    ];

    // See expense_dashboard.js: bootstrap guard so a sync throw (DOM
    // mismatch, TDZ, Telegram shim drift) doesn't leave the user stuck
    // on the initial "Đang tải dashboard…" spinner forever.
    try {
        els.retryBtn.addEventListener('click', renderDashboard);
        els.addExpenseBtn?.addEventListener('click', () => showExpenseModal());
        els.expenseCancel?.addEventListener('click', hideExpenseModal);
        els.expenseSave?.addEventListener('click', saveExpense);
        els.expenseDelete?.addEventListener('click', deleteExpense);
        els.expenseMonth?.addEventListener('change', renderDashboard);
        initExpenseForm();

        renderDashboard();
    } catch (err) {
        handleInitFailure(err);
    }

    function handleInitFailure(err) {
        console.error('dashboard init failed', err);
        if (els.errorMessage) {
            els.errorMessage.textContent = 'Không mở được dashboard, tải lại giúp mình nhé.';
        }
        showState('error');
        if (els.retryBtn) {
            els.retryBtn.addEventListener('click', () => window.location.reload(), { once: true });
        }
    }

    // applyTheme, formatMoneyShort, formatMoneyFull, fetchAPI moved to
    // dashboard_common.js — destructured at the top of the IIFE.
    // Note: legacy local formatMoneyShort showed "1.2 tỷ" (1-decimal);
    // the shared one shows "1.23 tỷ" (2-decimal), aligning with the
    // expense + wealth dashboards. Tiny precision boost, not regression.

    async function renderDashboard() {
        showState('loading');
        try {
            const monthQs = els.expenseMonth?.value ? '?month=' + encodeURIComponent(els.expenseMonth.value) : '';
            const data = await fetchAPI('/overview' + monthQs);
            els.totalSpent.textContent = formatMoneyFull(data.total_spent || 0);
            els.transactionCount.textContent = data.transaction_count || 0;
            els.monthLabel.textContent = formatMonthLabel(data.month);
            if (els.expenseMonth && !els.expenseMonth.value && data.month) els.expenseMonth.value = data.month;

            renderCategoryChart(data.top_categories || []);
            renderCategoryList(data.top_categories || []);
            renderTrendChart(data.daily_trend || []);
            renderExpenseList(data.expenses || []);
            showState('content');
            reportLoaded();
        } catch (err) {
            console.error(err);
            els.errorMessage.textContent = buildErrorMessage(err);
            showState('error');
            if (tg && tg.showAlert) tg.showAlert('Không tải được dữ liệu, thử lại nhé.');
        }
    }

    async function reportLoaded() {
        if (loadBeaconSent) return;
        loadBeaconSent = true;
        const loadTimeMs = Math.round(performance.now() - pageStartedAt);
        const headers = await authHeaders();
        fetch('/miniapp/api/events/loaded', {
            method: 'POST',
            headers,
            body: JSON.stringify({ load_time_ms: loadTimeMs }),
            keepalive: true,
        }).catch(() => { /* analytics best-effort */ });
    }

    function showState(state) {
        els.loading.hidden = state !== 'loading';
        els.error.hidden = state !== 'error';
        els.content.hidden = state !== 'content';
    }

    function formatMonthLabel(monthKey) {
        if (!monthKey) return '';
        const [year, month] = monthKey.split('-');
        return `Tháng ${parseInt(month, 10)}/${year}`;
    }

    function buildErrorMessage(err) {
        if (err && err.name === 'AbortError') return 'Kết nối quá chậm — thử lại nhé.';
        if (err && err.message === 'NO_INIT_DATA') return 'Hãy mở lại trang này từ trong Telegram nhé.';
        if (err && err.message === 'API 401') return 'Phiên đăng nhập Telegram không hợp lệ.';
        if (err && err.message === 'API 404') return 'Chưa có dữ liệu — hãy ghi giao dịch đầu tiên.';
        return 'Không tải được dữ liệu, thử lại nhé.';
    }

    function renderCategoryChart(categories) {
        if (categoryChart) categoryChart.destroy();
        if (!categories.length) {
            els.categoryChart.style.display = 'none';
            return;
        }
        els.categoryChart.style.display = 'block';

        categoryChart = new Chart(els.categoryChart, {
            type: 'doughnut',
            data: {
                labels: categories.map(c => c.name),
                datasets: [{
                    data: categories.map(c => c.amount),
                    backgroundColor: categories.map(c => c.color),
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
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

    function renderCategoryList(categories) {
        if (!categories.length) {
            els.categoryList.innerHTML = '<p class="empty-state">Chưa có chi tiêu nào tháng này 🌱</p>';
            return;
        }
        const maxAmount = Math.max.apply(null, categories.map(c => c.amount));
        els.categoryList.innerHTML = categories.map(cat => `
            <div class="category-row">
                <div class="category-info">
                    <span class="emoji">${cat.emoji}</span>
                    <span class="name">${escapeHtml(cat.name)}</span>
                </div>
                <div class="category-bar-wrap">
                    <div class="category-bar" style="width: ${(cat.amount / maxAmount * 100).toFixed(1)}%; background: ${cat.color}"></div>
                </div>
                <div class="category-amount">${formatMoneyShort(cat.amount)}</div>
            </div>
        `).join('');
    }

    function renderTrendChart(daily) {
        if (trendChart) trendChart.destroy();
        if (!daily.length) {
            els.trendChart.style.display = 'none';
            return;
        }
        els.trendChart.style.display = 'block';

        trendChart = new Chart(els.trendChart, {
            type: 'line',
            data: {
                labels: daily.map(d => d.date.slice(5)),
                datasets: [{
                    data: daily.map(d => d.amount),
                    borderColor: '#4ECDC4',
                    backgroundColor: 'rgba(78,205,196,0.15)',
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
                    x: {
                        ticks: { maxTicksLimit: 6 },
                    },
                },
            },
        });
    }


    function initExpenseForm() {
        if (els.expenseCategory) {
            els.expenseCategory.innerHTML = CATEGORIES.map(([code, label]) =>
                `<option value="${code}">${escapeHtml(label)}</option>`
            ).join('');
        }
        if (els.expenseDate) els.expenseDate.valueAsDate = new Date();
    }

    function renderExpenseList(items) {
        if (!els.expenseList) return;
        els.expenseEmpty.hidden = items.length > 0;
        els.expenseList.innerHTML = items.map(item => `
            <button class="expense-item" type="button" data-id="${escapeHtml(item.id)}">
                <span class="expense-emoji">${escapeHtml(item.category_emoji || '📌')}</span>
                <span class="expense-info">
                    <strong>${escapeHtml(item.merchant || item.note || item.category_label || 'Chi tiêu')}</strong>
                    <small>${formatDate(item.expense_date)} · ${escapeHtml(item.category_label || 'Chưa phân loại')}</small>
                </span>
                <span class="expense-amount">${formatMoneyShort(item.amount || 0)}</span>
            </button>
        `).join('');
        els.expenseList.querySelectorAll('.expense-item').forEach((row) => {
            const item = items.find(x => x.id === row.dataset.id);
            row.addEventListener('click', () => showExpenseModal(item));
        });
    }

    function showExpenseModal(item) {
        editingExpenseId = item?.id || null;
        els.expenseModalTitle.textContent = editingExpenseId ? 'Sửa chi tiêu' : 'Thêm chi tiêu';
        els.expenseAmount.value = item ? Math.round(item.amount || 0) : '';
        els.expenseCategory.value = item?.category || 'other';
        els.expenseDate.value = item?.expense_date || new Date().toISOString().slice(0, 10);
        els.expenseNote.value = item?.merchant || item?.note || '';
        els.expensePayment.value = item?.payment_method || '';
        els.expenseDelete.hidden = !editingExpenseId;
        els.expenseModal.hidden = false;
    }

    function hideExpenseModal() {
        els.expenseModal.hidden = true;
        editingExpenseId = null;
    }

    async function saveExpense() {
        const amount = parseFloat(els.expenseAmount.value);
        if (!amount || amount < 1000) {
            tg?.showAlert?.('Số tiền phải từ 1.000đ.');
            return;
        }
        const body = {
            amount,
            category: els.expenseCategory.value || 'other',
            expense_date: els.expenseDate.value,
            note: els.expenseNote.value.trim(),
            merchant: els.expenseNote.value.trim(),
            payment_method: els.expensePayment.value.trim(),
        };
        const url = editingExpenseId ? `/expenses/${editingExpenseId}` : '/expenses';
        const method = editingExpenseId ? 'PATCH' : 'POST';
        await fetchAPI(url, { method, body: JSON.stringify(body) });
        hideExpenseModal();
        await renderDashboard();
    }

    async function deleteExpense() {
        if (!editingExpenseId) return;
        const ok = window.confirm('Xoá chi tiêu này?');
        if (!ok) return;
        await fetchAPI(`/expenses/${editingExpenseId}`, { method: 'DELETE' });
        hideExpenseModal();
        await renderDashboard();
    }

    // escapeHtml, formatDate, resolveDateFormat moved to
    // dashboard_common.js — destructured at the top of the IIFE.
})();
