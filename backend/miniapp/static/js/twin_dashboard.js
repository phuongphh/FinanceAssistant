// Financial Twin dashboard — Phase 4A Epic 4.
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
        retryBtn: document.getElementById('retry-btn'),
        empty: document.getElementById('empty-state'),
        emptyCopy: document.getElementById('empty-copy'),
        content: document.getElementById('content'),
        netWorth: document.getElementById('net-worth'),
        deltaPill: document.getElementById('delta-pill'),
        computedAt: document.getElementById('computed-at'),
        coneChart: document.getElementById('cone-chart'),
        kpiGrid: document.getElementById('kpi-grid'),
        allocationList: document.getElementById('allocation-list'),
        scenarioBtns: Array.from(document.querySelectorAll('.scenario-btn')),
        ctaBtn: document.getElementById('cta-btn'),
        openWealthBtn: document.getElementById('open-wealth-btn'),
    };

    let currentScenario = new URLSearchParams(window.location.search).get('scenario') || 'current';
    let chart = null;
    const etags = Object.create(null);
    const cache = Object.create(null);

    els.retryBtn.addEventListener('click', () => load(currentScenario, { force: true }));
    els.ctaBtn.addEventListener('click', () => switchScenario('optimal'));
    els.openWealthBtn.addEventListener('click', () => { window.location.href = '/miniapp/wealth?source=twin_empty'; });
    els.scenarioBtns.forEach((btn) => btn.addEventListener('click', () => switchScenario(btn.dataset.scenario)));

    switchScenario(currentScenario);

    function switchScenario(scenario) {
        currentScenario = scenario === 'optimal' ? 'optimal' : 'current';
        els.scenarioBtns.forEach((btn) => {
            const active = btn.dataset.scenario === currentScenario;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        load(currentScenario);
    }

    async function load(scenario, options) {
        if (!cache[scenario] || options && options.force) showState('loading');
        try {
            const headers = buildHeaders(scenario);
            const response = await fetch(`/api/twin?scenario=${encodeURIComponent(scenario)}`, { headers });
            if (response.status === 304 && cache[scenario]) {
                render(cache[scenario]);
                return;
            }
            if (!response.ok) throw new Error(response.status === 401 ? 'Phiên Telegram hết hạn. Mở lại từ bot nhé.' : 'Không tải được Twin Dashboard.');
            const etag = response.headers.get('ETag');
            if (etag) etags[scenario] = etag;
            const body = await response.json();
            if (body.error) throw new Error(body.error);
            cache[scenario] = body.data;
            render(body.data);
        } catch (err) {
            console.error(err);
            els.errorMessage.textContent = err.message || 'Không tải được Twin Dashboard.';
            showState('error');
            if (tg && tg.showAlert) tg.showAlert(els.errorMessage.textContent);
        }
    }

    function buildHeaders(scenario) {
        const headers = { 'Accept': 'application/json' };
        if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        if (etags[scenario]) headers['If-None-Match'] = etags[scenario];
        return headers;
    }

    function render(data) {
        if (!data.has_projection) {
            els.emptyCopy.textContent = data.empty_state || els.emptyCopy.textContent;
            showState('empty');
            return;
        }
        els.netWorth.textContent = formatMoneyFull(Number(data.actual_net_worth || data.base_net_worth || 0));
        renderDelta(data.delta_vs_p50);
        els.computedAt.textContent = data.computed_at ? `cập nhật ${formatDate(data.computed_at)}` : '—';
        renderChart(data.cone || []);
        renderKpis(data.cone || []);
        renderAllocation(data.allocation || {});
        showState('content');
        reportLoaded();
    }

    function renderDelta(raw) {
        if (raw === null || raw === undefined) {
            els.deltaPill.textContent = 'đang theo dõi';
            return;
        }
        const value = Number(raw || 0);
        const sign = value >= 0 ? '+' : '−';
        els.deltaPill.textContent = `${sign}${formatMoneyShort(Math.abs(value))} vs P50`;
    }

    function renderChart(cone) {
        if (chart) chart.destroy();
        const labels = cone.map((p) => `Năm ${p.year}`);
        chart = new Chart(els.coneChart, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    series('P90', cone.map((p) => Number(p.p90)), 'rgba(20,184,166,0.20)', '#14B8A6', '+1'),
                    series('P50', cone.map((p) => Number(p.p50)), 'transparent', '#6D5DFB', false),
                    series('P10', cone.map((p) => Number(p.p10)), 'rgba(239,68,68,0.12)', '#EF4444', '-1'),
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: true, labels: { usePointStyle: true, boxWidth: 8 } },
                    tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatMoneyShort(ctx.parsed.y)}` } },
                },
                scales: { y: { ticks: { callback: (value) => formatMoneyShort(value) } } },
            },
        });
    }

    function series(label, data, backgroundColor, borderColor, fill) {
        return { label, data, borderColor, backgroundColor, borderWidth: label === 'P50' ? 3 : 2, pointRadius: 3, tension: 0.32, fill };
    }

    function renderKpis(cone) {
        const byYear = Object.fromEntries(cone.map((p) => [p.year, p]));
        const point = byYear[10] || cone[cone.length - 1] || {};
        els.kpiGrid.innerHTML = ['p10', 'p50', 'p90'].map((key) => `
            <article class="kpi-card">
                <div class="kpi-label">${key.toUpperCase()}</div>
                <div class="kpi-value">${formatMoneyShort(Number(point[key] || 0))}</div>
                <div class="kpi-year">năm ${point.year || '—'}</div>
            </article>
        `).join('');
    }

    function renderAllocation(allocation) {
        const entries = Object.entries(allocation).sort((a, b) => b[1] - a[1]);
        if (!entries.length) {
            els.allocationList.innerHTML = '<p class="section-hint">Chưa có phân bổ tài sản.</p>';
            return;
        }
        els.allocationList.innerHTML = entries.map(([name, value]) => {
            const pct = Math.round(Number(value) * 1000) / 10;
            return `<div class="allocation-row"><div><strong>${labelAsset(name)}</strong><div class="allocation-bar"><div class="allocation-fill" style="width:${Math.min(100, pct)}%"></div></div></div><span>${pct.toFixed(1)}%</span></div>`;
        }).join('');
    }

    function showState(state) {
        els.loading.hidden = state !== 'loading';
        els.error.hidden = state !== 'error';
        els.empty.hidden = state !== 'empty';
        els.content.hidden = state !== 'content';
    }

    function reportLoaded() {
        if (!tg || !tg.initData) return;
        fetch('/miniapp/api/events/loaded', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': tg.initData },
            body: JSON.stringify({ page: 'twin', scenario: currentScenario }),
        }).catch(() => {});
    }

    function applyTheme(theme) {
        const root = document.documentElement;
        if (theme.bg_color) root.style.setProperty('--bg', theme.bg_color);
        if (theme.text_color) root.style.setProperty('--text', theme.text_color);
        if (theme.hint_color) root.style.setProperty('--text-muted', theme.hint_color);
        if (theme.button_color) root.style.setProperty('--primary', theme.button_color);
        if (theme.button_text_color) root.style.setProperty('--primary-text', theme.button_text_color);
    }

    function formatMoneyShort(value) {
        if (value >= 1_000_000_000) return `${trim(value / 1_000_000_000)} tỷ`;
        if (value >= 1_000_000) return `${trim(value / 1_000_000)}tr`;
        if (value >= 1_000) return `${trim(value / 1_000)}k`;
        return `${Math.round(value).toLocaleString('vi-VN')}đ`;
    }

    function formatMoneyFull(value) { return `${Math.round(value).toLocaleString('vi-VN')}đ`; }
    function trim(value) { return value.toFixed(value >= 10 ? 0 : 1).replace('.0', ''); }
    function formatDate(value) { return new Date(value).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' }); }
    function labelAsset(name) {
        return ({ stocks_vn: 'Cổ phiếu VN', stocks_global: 'Cổ phiếu quốc tế', crypto: 'Crypto', gold: 'Vàng', cash_savings: 'Tiền mặt', real_estate_vn: 'Bất động sản', bonds_vn: 'Trái phiếu' })[name] || name;
    }
}());
