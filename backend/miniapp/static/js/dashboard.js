// Telegram Mini App — Dashboard v1
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

    els.retryBtn.addEventListener('click', renderDashboard);
    els.addExpenseBtn?.addEventListener('click', () => showExpenseModal());
    els.expenseCancel?.addEventListener('click', hideExpenseModal);
    els.expenseSave?.addEventListener('click', saveExpense);
    els.expenseDelete?.addEventListener('click', deleteExpense);
    els.expenseMonth?.addEventListener('change', renderDashboard);
    initExpenseForm();

    renderDashboard();

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
        if (abs >= 1_000_000_000) return (amount / 1_000_000_000).toFixed(1).replace(/\.0$/, '') + ' tỷ';
        if (abs >= 1_000_000) return (amount / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'tr';
        if (abs >= 1_000) return Math.round(amount / 1_000) + 'k';
        return Math.round(amount) + 'đ';
    }

    function formatMoneyFull(amount) {
        return new Intl.NumberFormat('vi-VN').format(Math.round(amount)) + 'đ';
    }

    async function fetchAPI(endpoint, options = {}) {
        const controller = new AbortController();
        const tid = setTimeout(() => controller.abort(), 12000);
        const headers = { 'Content-Type': 'application/json' };
        if (tg && tg.initData) {
            headers['X-Telegram-Init-Data'] = tg.initData;
        }
        try {
            const response = await fetch('/miniapp/api' + endpoint, { ...options, headers: { ...headers, ...(options.headers || {}) }, signal: controller.signal });
            if (!response.ok) {
                throw new Error('API ' + response.status);
            }
            const payload = await response.json();
            if (payload.error) throw new Error(payload.error.message || 'API error');
            return payload.data;
        } finally {
            clearTimeout(tid);
        }
    }

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

    function reportLoaded() {
        if (loadBeaconSent) return;
        loadBeaconSent = true;
        const loadTimeMs = Math.round(performance.now() - pageStartedAt);
        const headers = { 'Content-Type': 'application/json' };
        if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
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

    const DATE_FORMAT_BY_LANGUAGE = {
        vi: { locale: 'vi-VN', options: { day: '2-digit', month: '2-digit', year: 'numeric' } },
        en: { locale: 'en-GB', options: { day: '2-digit', month: '2-digit', year: 'numeric' } },
    };

    function resolveDateFormat() {
        const lang = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code || 'vi').toLowerCase();
        return DATE_FORMAT_BY_LANGUAGE[lang] || DATE_FORMAT_BY_LANGUAGE[lang.split('-')[0]] || DATE_FORMAT_BY_LANGUAGE.vi;
    }

    function formatDate(iso) {
        if (!iso) return '--/--/----';
        const d = new Date(iso + 'T00:00:00');
        const fmt = resolveDateFormat();
        return d.toLocaleDateString(fmt.locale, fmt.options);
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
})();
