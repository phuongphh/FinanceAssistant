// Expense dashboard — mirrors wealth_dashboard.js structure for visual/UX
// consistency. One bundled `/api/expense-dashboard/overview` round-trip
// loads hero total, category breakdown (pie + list), 30-day trend, and
// the month's expense rows. Add/edit/delete happens inline via a modal
// (no chat round-trip). After a mutation the UI patches local state +
// recomputes totals so the user sees the change instantly; a background
// reload reconciles with the server.
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
        moneyInSection: document.getElementById('money-in-section'),
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
        categoryFilter: document.getElementById('category-filter'),
        expensesList: document.getElementById('expenses-list'),
        moneyInList: document.getElementById('money-in-list'),
        moneyInTotal: document.getElementById('money-in-total'),
        addExpenseBtn: document.getElementById('add-expense-btn'),
        addMoneyInBtn: document.getElementById('add-money-in-btn'),
        addFirstExpenseBtn: document.getElementById('add-first-expense-btn'),
        modal: document.getElementById('expense-modal'),
        modalTitle: document.getElementById('expense-modal-title'),
        modalAmount: document.getElementById('expense-amount'),
        modalType: document.getElementById('expense-type'),
        modalCategory: document.getElementById('expense-category'),
        modalDate: document.getElementById('expense-date'),
        modalNote: document.getElementById('expense-note'),
        modalPayment: document.getElementById('expense-payment'),
        modalSource: document.getElementById('expense-source'),
        modalDelete: document.getElementById('expense-delete-btn'),
        modalCancel: document.getElementById('expense-cancel-btn'),
        modalSave: document.getElementById('expense-save-btn'),
    };

    // Keep in sync with backend/config/categories.py. Inlined to avoid
    // an extra round-trip on first paint — the canonical labels arrive
    // from the API for each row, so this list only feeds the form select
    // and the category filter dropdown.
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

    // Localised tables live next to CATEGORIES so init-phase callers
    // (initModalForm, applyLocalizedKeywords, renderExpenses) can read
    // them without tripping the TDZ on `const` bindings declared lower
    // in the IIFE body. Function declarations are hoisted; `const` is not.
    const DATE_FORMAT_BY_LANGUAGE = {
        vi: { locale: 'vi-VN', options: { day: '2-digit', month: '2-digit', year: 'numeric' } },
        en: { locale: 'en-GB', options: { day: '2-digit', month: '2-digit', year: 'numeric' } },
    };
    const UI_KEYWORDS = {
        vi: {
            reverse: 'Huỷ',
            reverseConfirmTitle: 'Huỷ giao dịch này?',
            reverseFailed: 'Không huỷ được giao dịch, thử lại nhé.',
        },
        en: {
            reverse: 'Reverse',
            reverseConfirmTitle: 'Reverse this transaction?',
            reverseFailed: 'Cannot reverse transaction. Please try again.',
        },
    };

    let pieChart = null;
    let trendChart = null;
    let lastOverview = null;
    let editingExpenseId = null;
    let currentTrendDays = 30;
    let currentSort = window.sessionStorage.getItem('expense.sort') || 'date_desc';
    let currentCategoryFilter = '';
    const pageStartedAt = performance.now();
    let loadBeaconSent = false;
    const SOURCE = new URLSearchParams(window.location.search).get('source');
    let refreshInFlight = false;
    let lastRefreshAt = 0;
    let activeRequestId = 0;

    // Guard the entire bootstrap. A synchronous throw here (eg. a TDZ
    // violation, a DOM element missing from the template, a Telegram
    // shim mismatch) would otherwise abort the IIFE silently and leave
    // the user staring at the initial "Đang tải chi tiêu…" spinner
    // forever — the failure mode that motivated this guard.
    try {
        initModalForm();
        applyLocalizedKeywords();
        initCategoryFilter();
        els.retryBtn.addEventListener('click', () => renderDashboard({ showSpinner: true }));
        els.addExpenseBtn.addEventListener('click', () => openModal(null, 'expense'));
        if (els.addMoneyInBtn) els.addMoneyInBtn.addEventListener('click', () => openModal(null, 'money_in'));
        if (els.addFirstExpenseBtn) els.addFirstExpenseBtn.addEventListener('click', () => openModal(null, 'expense'));
        els.expensesList.addEventListener('click', onExpenseRowClick);
        if (els.moneyInList) els.moneyInList.addEventListener('click', onExpenseRowClick);
        els.modalCancel.addEventListener('click', closeModal);
        els.modalSave.addEventListener('click', onSave);
        els.modalDelete.addEventListener('click', onDelete);
        els.modal.addEventListener('click', (e) => {
            if (e.target === els.modal) closeModal();
        });
        els.categoryFilter.addEventListener('change', () => {
            currentCategoryFilter = els.categoryFilter.value || '';
            renderExpensesSection();
        });
        document.querySelectorAll('.period-btn').forEach((btn) => {
            btn.addEventListener('click', () => onPeriodChange(btn));
        });
        document.querySelectorAll('.asset-sort-btn').forEach((btn) => {
            btn.addEventListener('click', () => onSortChange(btn));
        });
        updateSortButtons();

        document.addEventListener('visibilitychange', onResumeRefresh);
        window.addEventListener('focus', onResumeRefresh);
        window.addEventListener('pageshow', onPageShowRefresh);

        renderDashboard({ showSpinner: true });
    } catch (err) {
        handleInitFailure(err);
    }

    function handleInitFailure(err) {
        console.error('expense_dashboard init failed', err);
        if (els.errorMessage) {
            els.errorMessage.textContent = 'Không mở được trang chi tiêu, tải lại giúp mình nhé.';
        }
        showState('error');
        // The original retry listener may not have attached if init threw
        // before that line, so bind a fresh hard-reload listener as a
        // last-resort escape hatch.
        if (els.retryBtn) {
            els.retryBtn.addEventListener('click', () => window.location.reload(), { once: true });
        }
    }

    // -- Theme + utils ----------------------------------------------------


    function onPageShowRefresh(event) {
        if (event && event.persisted) onResumeRefresh();
    }

    function onResumeRefresh() {
        if (document.hidden) return;
        const now = Date.now();
        // Debounce focus/visibility storms from Telegram Desktop panel toggles.
        if (refreshInFlight || (now - lastRefreshAt) < 3000) return;
        lastRefreshAt = now;
        renderDashboard({ showSpinner: false });
    }

    function failAfter(ms) {
        return new Promise((_, reject) => {
            window.setTimeout(() => reject(new Error('API timeout')), ms);
        });
    }

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

    function resolveLanguageCode() {
        return (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code || 'vi').toLowerCase();
    }

    function resolveKeywords() {
        const lang = resolveLanguageCode();
        return UI_KEYWORDS[lang] || UI_KEYWORDS[lang.split('-')[0]] || UI_KEYWORDS.vi;
    }

    function resolveDateFormat() {
        const lang = resolveLanguageCode();
        return DATE_FORMAT_BY_LANGUAGE[lang] || DATE_FORMAT_BY_LANGUAGE[lang.split('-')[0]] || DATE_FORMAT_BY_LANGUAGE.vi;
    }

    function formatDate(iso) {
        if (!iso) return '--/--/----';
        const d = new Date(iso + 'T00:00:00');
        const fmt = resolveDateFormat();
        return d.toLocaleDateString(fmt.locale, fmt.options);
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

    async function renderDashboard({ showSpinner = false } = {}) {
        const requestId = ++activeRequestId;
        if (refreshInFlight) return;
        refreshInFlight = true;
        if (showSpinner) showState('loading');
        try {
            const params = new URLSearchParams();
            if (SOURCE) params.set('source', SOURCE);
            params.set('_t', String(Date.now()));
            const qs = params.toString() ? `?${params.toString()}` : '';
            const data = await Promise.race([
                fetchAPI('/expense-dashboard/overview' + qs, { cache: 'no-store' }),
                failAfter(15000),
            ]);
            if (requestId !== activeRequestId) return;
            lastOverview = data;

            renderAll();
            showState('content');
            reportLoaded();
        } catch (err) {
            console.error(err);
            // If we already have a snapshot, keep it on screen and just
            // alert silently — refreshes from optimistic mutations
            // shouldn't blow away the user's view on a transient blip.
            if (lastOverview) {
                if (tg && tg.showAlert) tg.showAlert('Đồng bộ thất bại, mình sẽ thử lại sau.');
                return;
            }
            els.errorMessage.textContent = buildErrorMessage(err);
            showState('error');
            if (tg && tg.showAlert) tg.showAlert('Không tải được dữ liệu, thử lại nhé.');
        } finally {
            refreshInFlight = false;
        }
    }

    function renderAll() {
        if (!lastOverview) return;
        renderHero(lastOverview);
        const isEmpty = ((lastOverview.transaction_count || 0) === 0) && !((lastOverview.money_in || []).length);
        toggleSections(isEmpty);
        if (!isEmpty) {
            renderPie(lastOverview.breakdown || []);
            renderBreakdownList(lastOverview.breakdown || []);
            renderTrend(lastOverview.daily_trend || []);
            populateCategoryFilter(lastOverview.breakdown || []);
            renderExpensesSection();
            renderMoneyInSection();
        }
    }

    function renderHero(data) {
        els.totalSpent.textContent = formatMoneyFull(data.total_spent || 0);
        els.monthPill.textContent = formatMonthLabel(data.month);
        const moneyInCount = (data.money_in || []).length;
        els.txnCount.textContent = `${data.transaction_count || 0} chi · ${moneyInCount} tiền vào`;

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
        if (els.moneyInSection) els.moneyInSection.hidden = isEmpty;
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

    async function onPeriodChange(btn) {
        document.querySelectorAll('.period-btn').forEach((b) => {
            b.classList.remove('active');
            b.removeAttribute('aria-selected');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        currentTrendDays = parseInt(btn.dataset.days, 10);
        const labelMap = { 30: '30 ngày', 90: '90 ngày', 365: '1 năm' };
        els.trendHeading.textContent = `Xu hướng ${labelMap[currentTrendDays] || ''}`.trim();

        try {
            const trend = await fetchAPI(`/expense-dashboard/trend?days=${currentTrendDays}`);
            renderTrend(trend);
        } catch (err) {
            console.error(err);
            if (tg && tg.showAlert) tg.showAlert('Không tải được dữ liệu xu hướng.');
        }
    }

    // -- Expenses list (sort + filter) -----------------------------------

    function populateCategoryFilter(breakdown) {
        const previous = currentCategoryFilter;
        // Keep "Tất cả" + one option per category present in the current month.
        const opts = ['<option value="">Tất cả</option>'].concat(
            breakdown.map(
                (b) => `<option value="${escapeHtml(b.code)}">${escapeHtml(b.emoji)} ${escapeHtml(b.name)}</option>`
            )
        );
        els.categoryFilter.innerHTML = opts.join('');
        // Preserve user's filter selection across re-renders if still valid.
        if (previous && breakdown.some((b) => b.code === previous)) {
            els.categoryFilter.value = previous;
            currentCategoryFilter = previous;
        } else {
            els.categoryFilter.value = '';
            currentCategoryFilter = '';
        }
    }

    function onSortChange(btn) {
        const nextSort = btn.dataset.sort || 'date_desc';
        if (nextSort === currentSort) return;
        currentSort = nextSort;
        try {
            window.sessionStorage.setItem('expense.sort', currentSort);
        } catch (_e) { /* private mode */ }
        updateSortButtons();
        renderExpensesSection();
    }

    function updateSortButtons() {
        document.querySelectorAll('.asset-sort-btn').forEach((btn) => {
            const active = btn.dataset.sort === currentSort;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
    }

    function renderExpensesSection() {
        const items = filteredSortedExpenses();
        renderExpenses(items);
    }

    function renderMoneyInSection() {
        if (!els.moneyInList) return;
        if (els.moneyInTotal) {
            els.moneyInTotal.textContent = `+${formatMoneyShort((lastOverview && lastOverview.money_in_total) || 0)}`;
        }
        const items = ((lastOverview && lastOverview.money_in) || []).slice().sort(
            (a, b) => (b.expense_date || '').localeCompare(a.expense_date || '') || (b.id || '').localeCompare(a.id || '')
        );
        renderMoneyIn(items);
    }

    function filteredSortedExpenses() {
        const all = (lastOverview && lastOverview.expenses) || [];
        let items = all;
        if (currentCategoryFilter) {
            items = items.filter((it) => it.category === currentCategoryFilter);
        }
        const sorters = {
            date_desc: (a, b) => (b.expense_date || '').localeCompare(a.expense_date || '') || (b.id || '').localeCompare(a.id || ''),
            date_asc: (a, b) => (a.expense_date || '').localeCompare(b.expense_date || '') || (a.id || '').localeCompare(b.id || ''),
            amount_desc: (a, b) => (b.amount || 0) - (a.amount || 0),
            amount_asc: (a, b) => (a.amount || 0) - (b.amount || 0),
        };
        return items.slice().sort(sorters[currentSort] || sorters.date_desc);
    }

    function renderExpenses(items) {
        if (!items.length) {
            const emptyMsg = currentCategoryFilter
                ? 'Không có giao dịch nào ở loại này.'
                : 'Chưa có giao dịch nào tháng này 🌱';
            els.expensesList.innerHTML = `<p class="empty-state">${escapeHtml(emptyMsg)}</p>`;
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
                        <button class="expense-action-btn expense-delete-row-btn" type="button" aria-label="${escapeHtml(resolveKeywords().reverse)} ${escapeHtml(title)}">↩️</button>
                    </div>
                </div>
            `;
        }).join('');
    }


    function sourceLabel(it) {
        const map = {
            cash: 'Tiền mặt',
            bank_account: 'Tài khoản',
            momo: 'Ví Momo',
            vnpay: 'Ví VNPay',
            zalopay: 'Ví ZaloPay',
            viettelpay: 'Ví ViettelPay',
        };
        if (it.source_type === 'e_wallet') return map[it.e_wallet_provider] || 'Ví điện tử';
        return map[it.source_type] || 'Chưa chọn nguồn';
    }

    function renderMoneyIn(items) {
        if (!els.moneyInList) return;
        if (!items.length) {
            els.moneyInList.innerHTML = '<p class="empty-state">Chưa có khoản tiền vào tháng này 🌱</p>';
            return;
        }
        els.moneyInList.innerHTML = items.map((it) => {
            const title = it.merchant || it.note || 'Tiền vào';
            const source = sourceLabel(it);
            return `
                <div class="expense-row money-in-row" data-id="${escapeHtml(it.id)}">
                    <span class="expense-icon">💚</span>
                    <div class="expense-info">
                        <div class="expense-title">${escapeHtml(title)}</div>
                        <div class="expense-meta">${formatDate(it.expense_date)} · Nguồn: ${escapeHtml(source)}</div>
                    </div>
                    <div class="expense-amount money-in-amount">+${formatMoneyShort(it.amount || 0)}</div>
                    <div class="expense-actions">
                        <button class="expense-action-btn expense-edit-btn" type="button" aria-label="Sửa ${escapeHtml(title)}">✏️</button>
                        <button class="expense-action-btn expense-delete-row-btn" type="button" aria-label="${escapeHtml(resolveKeywords().reverse)} ${escapeHtml(title)}">↩️</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    async function onExpenseRowClick(event) {
        const row = event.target.closest('.expense-row[data-id]');
        if (!row) return;
        const id = row.dataset.id;
        const item = (lastOverview?.expenses || []).concat(lastOverview?.money_in || []).find((x) => x.id === id);
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
        const keywords = resolveKeywords();
        const message = `${keywords.reverseConfirmTitle}\nBạn có chắc muốn đảo ngược giao dịch này?`;
        const confirmed = await new Promise((resolve) => {
            if (tg && tg.showConfirm) tg.showConfirm(message, resolve);
            else resolve(window.confirm(message));
        });
        if (!confirmed) return;
        applyDeleteOptimistic(item.id);
        try {
            await fetchAPI(`/expenses/${item.id}`, { method: 'DELETE' });
        } catch (_err) {
            if (tg && tg.showAlert) tg.showAlert(resolveKeywords().reverseFailed);
            await renderDashboard();
            return;
        }
        await renderDashboard();
    }

    // -- Optimistic UI helpers --------------------------------------------
    //
    // Mutations patch ``lastOverview`` in place (remove/replace/append row,
    // adjust totals + breakdown) and re-render immediately. A background
    // reload then reconciles with the server — if the server disagrees the
    // user sees the corrected state, otherwise the screen never flickers.

    function recomputeOverview() {
        const expenses = lastOverview.expenses || [];
        let total = 0;
        const byCat = new Map();
        for (const e of expenses) {
            total += e.amount || 0;
            const code = e.category || 'other';
            const prev = byCat.get(code) || {
                code,
                name: e.category_label || code,
                emoji: e.category_emoji || '📌',
                color: '#808080',
                amount: 0,
            };
            // Preserve canonical color from previous breakdown if present.
            const known = (lastOverview.breakdown || []).find((b) => b.code === code);
            if (known) prev.color = known.color;
            prev.amount += e.amount || 0;
            byCat.set(code, prev);
        }
        lastOverview.total_spent = total;
        lastOverview.transaction_count = expenses.length;
        lastOverview.money_in_total = (lastOverview.money_in || []).reduce((s, e) => s + (e.amount || 0), 0);
        lastOverview.breakdown = Array.from(byCat.values()).sort(
            (a, b) => b.amount - a.amount
        );
        const prev = lastOverview.change_month?.previous || 0;
        const change_amount = total - prev;
        const change_pct = prev > 0 ? (change_amount / prev) * 100.0 : 0;
        lastOverview.change_month = { amount: change_amount, pct: change_pct, previous: prev };
    }

    function applyDeleteOptimistic(id) {
        if (!lastOverview) return;
        lastOverview.expenses = (lastOverview.expenses || []).filter((x) => x.id !== id);
        lastOverview.money_in = (lastOverview.money_in || []).filter((x) => x.id !== id);
        recomputeOverview();
        renderAll();
    }

    function applyUpsertOptimistic(item) {
        if (!lastOverview) return;
        const targetKey = item.transaction_type === 'money_in' ? 'money_in' : 'expenses';
        const otherKey = targetKey === 'money_in' ? 'expenses' : 'money_in';
        lastOverview[otherKey] = (lastOverview[otherKey] || []).filter((x) => x.id !== item.id);
        const list = lastOverview[targetKey] || [];
        const idx = list.findIndex((x) => x.id === item.id);
        if (idx >= 0) list[idx] = item;
        else list.unshift(item);
        lastOverview[targetKey] = list;
        recomputeOverview();
        renderAll();
    }

    // -- Modal: add / edit / delete ---------------------------------------

    function initModalForm() {
        els.modalCategory.innerHTML = CATEGORIES.map(
            ([code, label]) => `<option value="${code}">${escapeHtml(label)}</option>`
        ).join('');
    }

    function applyLocalizedKeywords() {
        const keywords = resolveKeywords();
        if (els.modalDelete) els.modalDelete.textContent = keywords.reverse;
    }

    function initCategoryFilter() {
        // Seed with only "Tất cả" until first overview lands.
        els.categoryFilter.innerHTML = '<option value="">Tất cả</option>';
    }

    function openModal(item, forcedType) {
        editingExpenseId = item?.id || null;
        const txType = item?.transaction_type || forcedType || 'expense';
        els.modalTitle.textContent = editingExpenseId ? (txType === 'money_in' ? 'Sửa tiền vào' : 'Sửa chi tiêu') : (txType === 'money_in' ? 'Thêm tiền vào' : 'Thêm chi tiêu');
        els.modalType.value = txType;
        els.modalAmount.value = item ? Math.round(item.amount || 0) : '';
        els.modalCategory.value = item?.category || 'other';
        els.modalDate.value = item?.expense_date || new Date().toISOString().slice(0, 10);
        els.modalNote.value = item?.merchant || item?.note || '';
        els.modalPayment.value = item?.payment_method || '';
        els.modalSource.value = sourceValue(item);
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


    function sourceValue(item) {
        if (!item || !item.source_type) return '';
        if (item.source_type === 'e_wallet') return `e_wallet:${item.e_wallet_provider || 'momo'}`;
        return item.source_type;
    }

    function parseSourceValue(value) {
        if (!value) return { source_type: null, e_wallet_provider: null };
        if (value.startsWith('e_wallet:')) {
            return { source_type: 'e_wallet', e_wallet_provider: value.split(':')[1] || 'momo' };
        }
        return { source_type: value, e_wallet_provider: null };
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
            transaction_type: els.modalType.value || 'expense',
            category: els.modalCategory.value || 'other',
            expense_date: els.modalDate.value,
            note: note || null,
            merchant: note || null,
            payment_method: els.modalPayment.value.trim() || null,
            ...parseSourceValue(els.modalSource.value),
        };
        els.modalSave.disabled = true;
        let saved;
        try {
            if (editingExpenseId) {
                saved = await fetchAPI(`/expenses/${editingExpenseId}`, {
                    method: 'PATCH',
                    body: JSON.stringify(body),
                });
            } else {
                saved = await fetchAPI('/expenses', {
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
        // POST/PATCH return the canonical row — patch UI without waiting
        // for the round-trip refresh, then reconcile in the background.
        if (saved && saved.id) applyUpsertOptimistic(saved);
        renderDashboard();
    }

    async function onDelete() {
        if (!editingExpenseId) return;
        const confirmed = await new Promise((resolve) => {
            const msg = `${resolveKeywords().reverseConfirmTitle}\nBạn có chắc muốn đảo ngược giao dịch này?`;
            if (tg && tg.showConfirm) tg.showConfirm(msg, resolve);
            else resolve(window.confirm(msg));
        });
        if (!confirmed) return;
        els.modalDelete.disabled = true;
        const idToDelete = editingExpenseId;
        try {
            await fetchAPI(`/expenses/${idToDelete}`, { method: 'DELETE' });
        } catch (_err) {
            els.modalDelete.disabled = false;
            if (tg && tg.showAlert) tg.showAlert(resolveKeywords().reverseFailed);
            return;
        }
        closeModal();
        applyDeleteOptimistic(idToDelete);
        renderDashboard();
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
