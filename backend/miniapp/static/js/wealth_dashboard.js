// Wealth dashboard — Phase 3A (P3A-21, P3A-23, P3A-24).
//
// Loads /miniapp/api/wealth/overview, renders hero net-worth card,
// doughnut breakdown, line trend (with period selector), milestone
// progress (every wealth level — level-up milestones at band edges and
// sub-milestones inside a band), and asset list. Confetti fires when a
// user crosses a wealth-level threshold between session loads.
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
        assetsSection: document.getElementById('assets-section'),
        netWorth: document.getElementById('net-worth'),
        changeIcon: document.getElementById('change-icon'),
        changeAmount: document.getElementById('change-amount'),
        changePeriod: document.getElementById('change-period'),
        levelPill: document.getElementById('level-pill'),
        assetCount: document.getElementById('asset-count'),
        breakdownList: document.getElementById('breakdown-list'),
        pieChart: document.getElementById('pie-chart'),
        trendChart: document.getElementById('trend-chart'),
        trendHeading: document.getElementById('trend-heading'),
        milestoneSection: document.getElementById('milestone-section'),
        milestoneFill: document.getElementById('milestone-fill'),
        milestoneCurrent: document.getElementById('milestone-current'),
        milestoneTarget: document.getElementById('milestone-target'),
        milestoneCheer: document.getElementById('milestone-cheer'),
        assetsList: document.getElementById('assets-list'),
        addAssetBtn: document.getElementById('add-asset-btn'),
        addFirstAssetBtn: document.getElementById('add-first-asset-btn'),
        confetti: document.getElementById('confetti-canvas'),
    };

    let pieChart = null;
    let trendChart = null;
    let currentPeriod = 90;
    let currentAssetSort = window.sessionStorage.getItem('wealth.asset_sort') || 'value_desc';
    let lastOverview = null;
    const pageStartedAt = performance.now();
    let loadBeaconSent = false;

    // ``source`` query string lets the briefing button attribute the open
    // (?source=briefing). Same pattern used by the deep-link from /menu.
    const SOURCE = new URLSearchParams(window.location.search).get('source');
    const LEVEL_LABELS = {
        starter: 'Khởi Đầu',
        young_prof: 'Trẻ Năng Động',
        mass_affluent: 'Trung Lưu Vững',
        hnw: 'Tinh Hoa',
        vip: 'Đỉnh Cao',
    };
    const LEVEL_RANK = ['starter', 'young_prof', 'mass_affluent', 'hnw', 'vip'];
    const LAST_LEVEL_KEY = 'wealth.last_level';

    els.retryBtn.addEventListener('click', renderDashboard);
    els.addAssetBtn.addEventListener('click', closeAndAddAsset);
    els.addFirstAssetBtn.addEventListener('click', closeAndAddAsset);
    els.assetsList.addEventListener('click', onAssetRowClick);

    document.querySelectorAll('.period-btn').forEach((btn) => {
        btn.addEventListener('click', () => onPeriodChange(btn));
    });
    document.querySelectorAll('.asset-sort-btn').forEach((btn) => {
        btn.addEventListener('click', () => onAssetSortChange(btn));
    });
    updateAssetSortButtons();

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

    async function fetchAPI(endpoint) {
        const controller = new AbortController();
        const tid = setTimeout(() => controller.abort(), 12000);
        const headers = { 'Content-Type': 'application/json' };
        if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        try {
            const response = await fetch('/miniapp/api' + endpoint, {
                headers,
                signal: controller.signal,
            });
            if (!response.ok) throw new Error('API ' + response.status);
            const payload = await response.json();
            if (payload.error) {
                throw new Error(payload.error.message || 'API error');
            }
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
            params.set('sort', currentAssetSort);
            const qs = params.toString() ? `?${params.toString()}` : '';
            const data = await fetchAPI('/wealth/overview' + qs);
            lastOverview = data;

            renderHero(data);
            const isEmpty = (data.asset_count || 0) === 0;
            toggleSections(isEmpty);

            if (!isEmpty) {
                renderPie(data.breakdown || []);
                renderBreakdownList(data.breakdown || []);
                renderTrend(data.trend || []);
                currentAssetSort = data.asset_sort || currentAssetSort;
                window.sessionStorage.setItem('wealth.asset_sort', currentAssetSort);
                updateAssetSortButtons();
                renderAssets(data.assets || []);
            }

            renderMilestone(data);
            maybeCelebrateLevelUp(data.level);

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
        els.netWorth.textContent = formatMoneyFull(data.net_worth || 0);

        // Show both absolute amount and % vs hôm qua, e.g. "+217 tỷ (3%)".
        // Color + icon tag the .hero-change element via .up / .down / .flat
        // so CSS paints it green / red / neutral.
        const change = data.change_day || { amount: 0, pct: 0 };
        const pct = Number(change.pct || 0);
        const amount = Number(change.amount || 0);
        const tolerance = 0.05;  // < 0.05% reads as "flat" — UI sugar
        let direction = 'flat';
        let icon = '➖';
        let sign = '';
        if (pct > tolerance) {
            direction = 'up'; icon = '📈'; sign = '+';
        } else if (pct < -tolerance) {
            direction = 'down'; icon = '📉'; sign = '−';
        }
        els.changeIcon.textContent = icon;
        const absAmount = formatMoneyShort(Math.abs(amount));
        const absPct = Math.abs(pct).toFixed(1);
        els.changeAmount.textContent =
            direction === 'flat'
                ? '0₫ (0.0%)'
                : `${sign}${absAmount} (${sign}${absPct}%)`;
        els.changePeriod.textContent = 'so với hôm qua';
        const heroChange = els.changeIcon.parentElement;
        if (heroChange) {
            heroChange.classList.remove('up', 'down', 'flat');
            heroChange.classList.add(direction);
        }

        els.levelPill.textContent = data.level_label || LEVEL_LABELS[data.level] || data.level || '—';
        els.assetCount.textContent = `${data.asset_count || 0} tài sản`;
    }

    function toggleSections(isEmpty) {
        els.emptyState.hidden = !isEmpty;
        els.breakdownSection.hidden = isEmpty;
        els.trendSection.hidden = isEmpty;
        els.assetsSection.hidden = isEmpty;
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
                labels: breakdown.map((b) => b.label),
                datasets: [{
                    data: breakdown.map((b) => b.value),
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
        els.breakdownList.innerHTML = breakdown.map((b) => `
            <div class="breakdown-row">
                <span class="breakdown-icon">${escapeHtml(b.icon)}</span>
                <span class="breakdown-label">${escapeHtml(b.label)}</span>
                <span class="breakdown-value">${formatMoneyShort(b.value)}</span>
                <span class="breakdown-pct">${(b.pct || 0).toFixed(0)}%</span>
            </div>
        `).join('');
    }

    // -- Trend ------------------------------------------------------------

    function renderTrend(trend) {
        if (trendChart) trendChart.destroy();
        if (!trend.length) {
            els.trendChart.style.display = 'none';
            return;
        }
        els.trendChart.style.display = 'block';
        trendChart = new Chart(els.trendChart, {
            type: 'line',
            data: {
                labels: trend.map((t) => t.date.slice(5)),
                datasets: [{
                    data: trend.map((t) => t.value),
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
        currentPeriod = parseInt(btn.dataset.days, 10);
        const labelMap = { 30: '30 ngày', 90: '90 ngày', 365: '1 năm' };
        els.trendHeading.textContent = `Xu hướng ${labelMap[currentPeriod] || ''}`.trim();

        try {
            const trend = await fetchAPI(`/wealth/trend?days=${currentPeriod}`);
            renderTrend(trend);
        } catch (err) {
            console.error(err);
            if (tg && tg.showAlert) tg.showAlert('Không tải được dữ liệu xu hướng.');
        }
    }

    // -- Milestone --------------------------------------------------------

    function renderMilestone(data) {
        const level = data.level;
        const milestone = data.next_milestone;
        if (!milestone || milestone.target <= 0) {
            els.milestoneSection.hidden = true;
            return;
        }
        els.milestoneSection.hidden = false;

        const pct = Math.max(0, Math.min(100, milestone.pct_progress || 0));
        // Animate from 0% on first render so the bar visibly fills.
        els.milestoneFill.style.width = '0%';
        requestAnimationFrame(() => {
            els.milestoneFill.style.width = pct + '%';
        });
        els.milestoneCurrent.textContent = formatMoneyShort(data.net_worth || 0);
        els.milestoneTarget.textContent = formatMoneyShort(milestone.target);

        const remaining = milestone.remaining || 0;
        if (remaining <= 0) {
            els.milestoneCheer.textContent = '🎉 Bạn đã chạm mốc — chuẩn bị lên cấp!';
        } else if (milestone.target_level && milestone.target_level !== level) {
            els.milestoneCheer.textContent =
                `Còn ${formatMoneyShort(remaining)} nữa để đạt ${milestone.target_label || 'mốc tiếp theo'}!`;
        } else {
            // Sub-milestone inside the current band — don't claim the user
            // is climbing toward their current level's label.
            els.milestoneCheer.textContent =
                `Còn ${formatMoneyShort(remaining)} nữa để cán mốc ${formatMoneyShort(milestone.target)}!`;
        }
    }

    function maybeCelebrateLevelUp(currentLevel) {
        if (!currentLevel) return;
        let previous = null;
        try {
            previous = window.localStorage.getItem(LAST_LEVEL_KEY);
        } catch (_e) {
            // Private browsing / iframe sandbox may block localStorage —
            // skip the celebration silently rather than throwing.
            return;
        }
        try {
            window.localStorage.setItem(LAST_LEVEL_KEY, currentLevel);
        } catch (_e) {
            return;
        }
        if (!previous || previous === currentLevel) return;
        const prevIdx = LEVEL_RANK.indexOf(previous);
        const curIdx = LEVEL_RANK.indexOf(currentLevel);
        if (prevIdx >= 0 && curIdx > prevIdx) {
            launchConfetti();
            if (tg && tg.HapticFeedback) {
                try { tg.HapticFeedback.notificationOccurred('success'); } catch (_e) { /* noop */ }
            }
        }
    }

    // -- Assets list ------------------------------------------------------

    function onAssetSortChange(btn) {
        const nextSort = btn.dataset.sort || 'alpha';
        if (nextSort === currentAssetSort) return;
        currentAssetSort = nextSort;
        window.sessionStorage.setItem('wealth.asset_sort', currentAssetSort);
        updateAssetSortButtons();
        renderDashboard();
    }

    function updateAssetSortButtons() {
        document.querySelectorAll('.asset-sort-btn').forEach((btn) => {
            const active = btn.dataset.sort === currentAssetSort;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
    }

    function renderAssets(assets) {
        if (!assets.length) {
            els.assetsList.innerHTML = '<p class="empty-state">Chưa có tài sản nào — thêm tài sản đầu tiên nhé.</p>';
            return;
        }
        els.assetsList.innerHTML = assets.map((a) => {
            const positive = (a.change || 0) >= 0;
            const sign = positive ? '+' : '';
            const cls = positive ? 'positive' : 'negative';
            // Subtitle composes "<Type> · <Subtype>" so the user can tell
            // apart e.g. Techcombank Thanh toán vs Techcombank Tiết kiệm.
            const subtitle = a.subtype_label
                ? `${escapeHtml(a.type_label)} · ${escapeHtml(a.subtype_label)}`
                : escapeHtml(a.type_label);
            // Backend merges rows with the same name+subtype; surface the
            // bundle count so users know one card represents multiple
            // entries (e.g. two ``Tiền mặt`` deposits → ``×2``).
            const countBadge = (a.count || 1) > 1
                ? `<span class="asset-count">×${a.count}</span>`
                : '';
            const memberIds = Array.isArray(a.member_ids) ? a.member_ids : [a.id];
            return `
                <div class="asset-card" data-asset-id="${escapeHtml(a.id)}" data-asset-ids="${escapeHtml(memberIds.join(','))}">
                    <span class="asset-icon">${escapeHtml(a.icon)}</span>
                    <div class="asset-info">
                        <div class="asset-name">${escapeHtml(a.name)}${countBadge}</div>
                        <div class="asset-type">${subtitle}</div>
                    </div>
                    <div class="asset-value">
                        <div class="asset-current">${formatMoneyShort(a.current_value)}</div>
                        <div class="asset-change ${cls}">${sign}${(a.change_pct || 0).toFixed(1)}%</div>
                    </div>
                    <div class="asset-actions">
                        <button class="asset-action-btn asset-edit-btn" type="button" aria-label="Sửa ${escapeHtml(a.name)}">✏️</button>
                        <button class="asset-action-btn asset-delete-btn" type="button" aria-label="Xoá ${escapeHtml(a.name)}">🗑️</button>
                    </div>
                </div>
            `;
        }).join('');
    }

    // -- Confetti (vanilla, < 2KB) ----------------------------------------

    // Lightweight celebration: 80 colored squares falling for ~1.5s. Avoids
    // bringing in a 30KB confetti library when we only need this once per
    // user lifetime (level-up).
    function launchConfetti() {
        const canvas = els.confetti;
        if (!canvas || !canvas.getContext) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        canvas.width = window.innerWidth * dpr;
        canvas.height = window.innerHeight * dpr;
        canvas.style.width = window.innerWidth + 'px';
        canvas.style.height = window.innerHeight + 'px';
        ctx.scale(dpr, dpr);

        const colors = ['#4ECDC4', '#3B82F6', '#F59E0B', '#EF4444', '#10B981', '#8B5CF6'];
        const pieces = [];
        for (let i = 0; i < 80; i++) {
            pieces.push({
                x: Math.random() * window.innerWidth,
                y: -20 - Math.random() * window.innerHeight * 0.4,
                vx: (Math.random() - 0.5) * 4,
                vy: 2 + Math.random() * 4,
                size: 6 + Math.random() * 6,
                color: colors[i % colors.length],
                rot: Math.random() * Math.PI,
                vrot: (Math.random() - 0.5) * 0.3,
            });
        }

        const startedAt = performance.now();
        function frame(now) {
            const elapsed = now - startedAt;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            for (const p of pieces) {
                p.x += p.vx;
                p.y += p.vy;
                p.vy += 0.05;
                p.rot += p.vrot;
                ctx.save();
                ctx.translate(p.x, p.y);
                ctx.rotate(p.rot);
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
                ctx.restore();
            }
            if (elapsed < 1800) {
                requestAnimationFrame(frame);
            } else {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
        }
        requestAnimationFrame(frame);
    }

    // -- Misc -------------------------------------------------------------

    async function onAssetRowClick(event) {
        const deleteBtn = event.target.closest('.asset-delete-btn');
        const editBtn = event.target.closest('.asset-edit-btn');
        const card = event.target.closest('.asset-card[data-asset-id]');
        if (!card) return;

        if (deleteBtn) {
            await onAssetDeleteClick(card);
            return;
        }
        if (!editBtn) return;

        const assetId = card.dataset.assetId;
        const assetIds = (card.dataset.assetIds || '').split(',').filter(Boolean);
        if (!assetId && !assetIds.length) return;
        editBtn.disabled = true;
        try {
            const headers = { 'Content-Type': 'application/json' };
            if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
            const response = await fetch('/miniapp/api/wealth/start-asset-edit', {
                method: 'POST',
                headers,
                body: JSON.stringify({ asset_id: assetId, asset_ids: assetIds }),
            });
            if (!response.ok) throw new Error('API ' + response.status);
        } catch (_err) {
            if (tg && tg.showAlert) tg.showAlert('Không mở được màn sửa, thử lại nhé.');
            editBtn.disabled = false;
            return;
        }
        if (tg && tg.close) tg.close();
    }

    async function onAssetDeleteClick(card) {
        const assetId = card.dataset.assetId;
        const assetIds = (card.dataset.assetIds || '').split(',').filter(Boolean);
        if (!assetId && !assetIds.length) return;

        const assetName = card.querySelector('.asset-name')?.firstChild?.textContent?.trim() || 'tài sản này';
        const message = `Xoá "${assetName}"?\nThao tác này không thể hoàn tác.`;

        const confirmed = await new Promise((resolve) => {
            if (tg && tg.showConfirm) {
                tg.showConfirm(message, resolve);
            } else {
                resolve(window.confirm(message));
            }
        });
        if (!confirmed) return;

        const deleteBtn = card.querySelector('.asset-delete-btn');
        if (deleteBtn) deleteBtn.disabled = true;

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
            const idsToDelete = assetIds.length ? assetIds : [assetId];
            const response = await fetch('/miniapp/api/wealth/delete-asset', {
                method: 'POST',
                headers,
                body: JSON.stringify({ asset_ids: idsToDelete }),
            });
            if (!response.ok) throw new Error('API ' + response.status);
        } catch (_err) {
            if (tg && tg.showAlert) tg.showAlert('Không xoá được tài sản, thử lại nhé.');
            if (deleteBtn) deleteBtn.disabled = false;
            return;
        }
        renderDashboard();
    }

    async function closeAndAddAsset() {
        // Disable both buttons to prevent a double-tap firing the wizard
        // twice — a second call would just reset the flow but it's wasted
        // work and a wasted Telegram message.
        if (els.addAssetBtn) els.addAssetBtn.disabled = true;
        if (els.addFirstAssetBtn) els.addFirstAssetBtn.disabled = true;

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
            // Wait for the bot to post the type-picker before closing
            // the WebApp — otherwise the user lands on an empty chat
            // and assumes the button did nothing.
            await fetch('/miniapp/api/wealth/start-asset-wizard', {
                method: 'POST',
                headers,
            });
        } catch (_err) {
            // Best-effort: even on failure we still close so the user
            // isn't stuck staring at the dashboard.
        }
        if (tg && tg.close) tg.close();
    }

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
            body: JSON.stringify({ load_time_ms: loadTimeMs, page: 'wealth' }),
            keepalive: true,
        }).catch(() => { /* analytics best-effort */ });
    }
})();
