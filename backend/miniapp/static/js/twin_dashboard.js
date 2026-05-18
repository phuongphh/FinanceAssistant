// Financial Twin dashboard — Phase 4A Epic 4 + Phase 4B S4 Scenario Comparison.
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
        presentAnchorBtn: document.getElementById('present-anchor-btn'),
        growthRate: document.getElementById('growth-rate'),
        breakdownPanel: document.getElementById('net-worth-breakdown'),
        lifeOutcomeSection: document.getElementById('life-outcome-section'),
        lifeOutcomeCopy: document.getElementById('life-outcome-copy'),
        lifeOutcomeRefresh: document.getElementById('life-outcome-refresh'),
        computedAt: document.getElementById('computed-at'),
        coneChart: document.getElementById('cone-chart'),
        kpiGrid: document.getElementById('kpi-grid'),
        allocationList: document.getElementById('allocation-list'),
        scenarioBtns: Array.from(document.querySelectorAll('.scenario-btn')),
        ctaBtn: document.getElementById('cta-btn'),
        openWealthBtn: document.getElementById('open-wealth-btn'),
        comparisonSection: document.getElementById('comparison-section'),
        comparisonBadges: document.getElementById('comparison-badges'),
        savingsCta: document.getElementById('savings-cta'),
        optimalInfoBtn: document.getElementById('optimal-info-btn'),
        uncertaintySection: document.getElementById('uncertainty-section'),
        uncertaintyList: document.getElementById('uncertainty-list'),
        uncertaintyHint: document.getElementById('uncertainty-hint'),
        storyFlow: document.getElementById('story-flow'),
        storyStep: document.getElementById('story-step'),
        storySkip: document.getElementById('story-skip'),
        storyCard: document.getElementById('story-card'),
        storyPrev: document.getElementById('story-prev'),
        storyNext: document.getElementById('story-next'),
        technicalDetail: document.getElementById('technical-detail'),
        openTechnicalBtn: document.getElementById('open-technical-btn'),
    };

    let currentScenario = new URLSearchParams(window.location.search).get('scenario') || 'current';
    let chart = null;
    let storyScreens = [];
    let storyIndex = 0;
    let storyMode = "compact";
    const etags = Object.create(null);
    const cache = Object.create(null);

    els.retryBtn.addEventListener('click', () => load(currentScenario, { force: true }));
    els.openWealthBtn.addEventListener('click', () => { window.location.href = '/miniapp/wealth?source=twin_empty'; });
    els.scenarioBtns.forEach((btn) => btn.addEventListener('click', () => switchScenario(btn.dataset.scenario)));
    if (els.optimalInfoBtn) els.optimalInfoBtn.addEventListener('click', showOptimalTooltip);
    if (els.presentAnchorBtn) els.presentAnchorBtn.addEventListener('click', toggleBreakdown);
    if (els.deltaPill) els.deltaPill.addEventListener('click', showCausalityPlaceholder);
    if (els.growthRate) els.growthRate.addEventListener('click', showMaintainedProjection);
    if (els.lifeOutcomeRefresh) els.lifeOutcomeRefresh.addEventListener('click', refreshLifeOutcome);
    if (els.storyPrev) els.storyPrev.addEventListener('click', () => moveStory(-1));
    if (els.storyNext) els.storyNext.addEventListener('click', () => moveStory(1));
    if (els.storySkip) els.storySkip.addEventListener('click', skipStory);
    if (els.openTechnicalBtn) els.openTechnicalBtn.addEventListener('click', openTechnicalDetail);

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
        renderStoryFlow(data);
        renderPresentAnchor(data);
        renderDelta(data.delta_vs_p50);
        els.computedAt.textContent = data.computed_at ? `cập nhật ${formatDate(data.computed_at)}` : '—';
        renderChart(data.cone || []);
        renderLifeOutcome(data);
        renderKpis(data.cone || [], data.scenario_labels || {});
        renderAllocation(data.allocation || {});
        renderComparisonDeltas(data);
        renderUncertaintyBreakdown(data);
        renderCtaBtn(data);
        showState('content');
        reportLoaded();
    }


    function renderStoryFlow(data) {
        const flow = data.story_flow || {};
        storyScreens = flow.screens || [];
        storyMode = flow.mode || 'compact';
        storyIndex = 0;
        if (!els.storyFlow || !storyScreens.length) return;
        els.storySkip.textContent = flow.skip_label || 'Bỏ qua, xem nhanh';
        els.technicalDetail.hidden = true;
        els.openTechnicalBtn.hidden = false;
        els.storyFlow.hidden = false;
        renderStoryScreen();
        postTwinEvent('story_opened', storyScreens[0] && storyScreens[0].id);
    }

    function renderStoryScreen() {
        const screen = storyScreens[storyIndex] || {};
        const cards = (screen.cards || []).map(renderScenarioStoryCard).join('');
        els.storyStep.textContent = `${storyIndex + 1}/${storyScreens.length}`;
        els.storyCard.innerHTML = `
            <div class="story-emoji">${escapeHtml(screen.emoji || '🔮')}</div>
            <h2>${escapeHtml(screen.title || '')}</h2>
            <p>${escapeHtml(screen.body || '')}</p>
            ${cards ? `<div class="story-scenario-grid">${cards}</div>` : ''}
            ${screen.hint ? `<p class="section-hint">${escapeHtml(screen.hint)}</p>` : ''}
        `;
        els.storyPrev.disabled = storyIndex === 0;
        els.storyNext.textContent = storyIndex === storyScreens.length - 1 ? 'Hoàn tất' : 'Tiếp →';
        postTwinEvent('screen_viewed', screen.id);
    }

    function renderScenarioStoryCard(card) {
        const mascot = card.mascot || {};
        return `<article class="story-scenario-card">
            <div>
                <strong>${escapeHtml(card.label || card.p_code || '')}</strong>
                <span>${formatMoneyShort(Number(card.amount || 0))}</span>
            </div>
            <img src="${escapeAttr(mascot.asset_url || '')}" alt="${escapeAttr(mascot.alt || '')}" loading="lazy" onerror="this.replaceWith(document.createTextNode('${escapeAttr(mascot.fallback || '🔮')}'))">
        </article>`;
    }

    function moveStory(delta) {
        if (!storyScreens.length) return;
        if (delta > 0 && storyIndex === storyScreens.length - 1) {
            els.storyFlow.hidden = true;
            postTwinEvent('story_completed', storyScreens[storyIndex].id);
            return;
        }
        storyIndex = Math.max(0, Math.min(storyScreens.length - 1, storyIndex + delta));
        renderStoryScreen();
    }

    function skipStory() {
        if (!storyScreens.length) return;
        storyIndex = storyScreens.length - 1;
        renderStoryScreen();
        postTwinEvent('story_skipped', storyScreens[storyIndex].id);
    }

    function openTechnicalDetail() {
        els.technicalDetail.hidden = false;
        els.openTechnicalBtn.hidden = true;
        postTwinEvent('chart_opened', 'technical_detail');
        setTimeout(() => { if (chart) chart.resize(); }, 0);
    }

    function postTwinEvent(eventType, screenId) {
        const headers = { 'Accept': 'application/json', 'Content-Type': 'application/json' };
        if (tg && tg.initData) headers['X-Telegram-Init-Data'] = tg.initData;
        fetch('/api/twin/events', {
            method: 'POST',
            headers,
            body: JSON.stringify({ event_type: eventType, screen_id: screenId || null, flow_mode: storyMode }),
            keepalive: true,
        }).catch(() => {});
    }

    function renderPresentAnchor(data) {
        const anchor = data.present_anchor || {};
        els.netWorth.textContent = anchor.present_label ? anchor.present_label.replace('Hiện tại: ', '') : formatMoneyFull(Number(data.actual_net_worth || data.base_net_worth || 0));
        if (els.growthRate) els.growthRate.textContent = anchor.growth_rate_label || 'Đang theo dõi nhịp';
        if (els.breakdownPanel) {
            const entries = Object.entries(anchor.breakdown || {});
            els.breakdownPanel.innerHTML = entries.length ? entries.map(([key, value]) => `<div><span>${labelAsset(key)}</span><strong>${value}</strong></div>`).join('') : '<p>Chưa có breakdown tài sản.</p>';
            els.breakdownPanel.dataset.maintained = anchor.projected_if_maintained_label || '';
        }
        els.deltaPill.classList.toggle('amber', anchor.tone === 'amber');
        els.deltaPill.classList.toggle('positive', anchor.tone === 'positive');
    }

    function renderDelta(raw) {
        if (raw === null || raw === undefined) {
            els.deltaPill.textContent = 'Ổn định';
            return;
        }
        const value = Number(raw || 0);
        if (Math.abs(value) < 100000) { els.deltaPill.textContent = 'Ổn định'; return; }
        const arrow = value >= 0 ? '↑ Tăng' : '↓ Giảm';
        els.deltaPill.textContent = `${arrow} ${formatMoneyShort(Math.abs(value))}`;
    }

    function renderChart(cone) {
        if (chart) chart.destroy();
        const labels = cone.map((p) => `Năm ${p.year}`);
        chart = new Chart(els.coneChart, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    series(labelFor('p90'), cone.map((p) => Number(p.p90)), 'rgba(20,184,166,0.20)', '#14B8A6', '+1'),
                    series(labelFor('p50'), cone.map((p) => Number(p.p50)), 'transparent', '#6D5DFB', false),
                    series(labelFor('p10'), cone.map((p) => Number(p.p10)), 'rgba(59,130,246,0.12)', '#3B82F6', '-1'),
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
        return { label, data, borderColor, backgroundColor, borderWidth: label.includes('Bình thường') || label === 'P50' ? 3 : 2, pointRadius: 3, tension: 0.32, fill };
    }

    function renderLifeOutcome(data) {
        if (!els.lifeOutcomeSection) return;
        if (!data.life_outcome) { els.lifeOutcomeSection.hidden = true; return; }
        els.lifeOutcomeCopy.textContent = data.life_outcome;
        els.lifeOutcomeSection.hidden = false;
    }

    function renderKpis(cone, labels) {
        const byYear = Object.fromEntries(cone.map((p) => [p.year, p]));
        const point = byYear[10] || cone[cone.length - 1] || {};
        els.kpiGrid.innerHTML = ['p10', 'p50', 'p90'].map((key) => `
            <article class="kpi-card">
                <div class="kpi-label">${(labels[key] && labels[key].label) || key.toUpperCase()}</div>
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

    function renderComparisonDeltas(data) {
        if (!els.comparisonSection) return;
        const deltas = data.comparison_deltas;
        if (!deltas || !deltas.length || data.scenario !== 'current') {
            els.comparisonSection.hidden = true;
            return;
        }
        els.comparisonBadges.innerHTML = deltas.map((d) => {
            const positive = d.delta_pct >= 0;
            const sign = positive ? '+' : '';
            return `<div class="comparison-badge">
                <div class="badge-year">Năm ${d.year}</div>
                <div class="badge-values">
                    <span class="badge-label">Hiện tại: ${formatMoneyShort(Number(d.current_p50))}</span>
                    <span class="delta-badge-pill ${positive ? 'positive' : 'negative'}">${sign}${d.delta_pct.toFixed(1)}%</span>
                    <span class="badge-label">Tối ưu: ${formatMoneyShort(Number(d.optimal_p50))}</span>
                </div>
            </div>`;
        }).join('');
        if (data.monthly_savings_needed && Number(data.monthly_savings_needed) > 0) {
            els.savingsCta.textContent = `Để đạt P50 tối ưu, bạn cần tiết kiệm thêm ~${formatMoneyShort(Number(data.monthly_savings_needed))}/tháng`;
        } else {
            els.savingsCta.textContent = 'Danh mục hiện tại đã khá gần mức tối ưu — tiếp tục duy trì nhé!';
        }
        els.savingsCta.hidden = false;
        els.comparisonSection.hidden = false;
    }

    function renderUncertaintyBreakdown(data) {
        if (!els.uncertaintySection) return;
        const contributors = data.uncertainty_contributors;
        if (!contributors || !contributors.length) {
            els.uncertaintySection.hidden = true;
            return;
        }
        els.uncertaintyList.innerHTML = contributors.map((c) => {
            const pct = c.contribution_pct;
            return `<div class="uncertainty-row">
                <span class="uncertainty-label">${labelAsset(c.asset_class)}</span>
                <div class="uncertainty-bar-wrap">
                    <div class="uncertainty-bar" style="width:${Math.min(100, pct)}%"></div>
                </div>
                <span class="uncertainty-pct">${pct.toFixed(1)}%</span>
            </div>`;
        }).join('');
        const total = contributors.reduce((s, c) => s + c.contribution_pct, 0);
        els.uncertaintyHint.textContent = `Hai nhóm này tạo ra ~${Math.round(total)}% độ rộng vùng 🌧️–☀️.`;
        els.uncertaintySection.hidden = false;
    }

    function renderCtaBtn(data) {
        if (data.scenario === 'optimal') {
            els.ctaBtn.textContent = 'Quay lại Hiện tại';
            els.ctaBtn.onclick = () => switchScenario('current');
        } else {
            els.ctaBtn.textContent = 'Thay đổi để đạt Optimal';
            els.ctaBtn.onclick = () => switchScenario('optimal');
        }
    }

    function labelFor(key) {
        const data = cache[currentScenario] || {};
        const labels = data.scenario_labels || {};
        return (labels[key] && labels[key].label) || key.toUpperCase();
    }

    function toggleBreakdown() {
        if (!els.breakdownPanel) return;
        const next = els.breakdownPanel.hidden;
        els.breakdownPanel.hidden = !next;
        els.presentAnchorBtn.setAttribute('aria-expanded', next ? 'true' : 'false');
    }

    function showCausalityPlaceholder() {
        const msg = 'Bé Tiền sẽ giải thích nguyên nhân thay đổi ở Story 3.2.';
        if (tg && tg.showAlert) tg.showAlert(msg); else alert(msg);
    }

    function showMaintainedProjection() {
        const msg = (els.breakdownPanel && els.breakdownPanel.dataset.maintained) || 'Bé Tiền cần thêm dữ liệu để ước tính nhịp duy trì.';
        if (tg && tg.showAlert) tg.showAlert(msg); else alert(msg);
    }

    function refreshLifeOutcome() {
        const key = `lifeOutcomeRefresh:${new Date().toISOString().slice(0, 10)}`;
        const used = Number(localStorage.getItem(key) || 0);
        if (used >= 3) {
            const msg = 'Hôm nay bạn đã đổi ví dụ 3 lần rồi nhé.';
            if (tg && tg.showAlert) tg.showAlert(msg); else alert(msg);
            return;
        }
        localStorage.setItem(key, String(used + 1));
        load(currentScenario, { force: true });
    }

    function showOptimalTooltip() {
        const msg = 'Kịch bản Tối Ưu giả định: tăng tỷ trọng tài sản sinh lời, tiết kiệm đều đặn hơn, và phân bổ theo danh mục mục tiêu đã cài đặt.';
        if (tg && tg.showAlert) tg.showAlert(msg);
        else alert(msg);
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
    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    }

    function escapeAttr(value) { return escapeHtml(value); }

    function labelAsset(name) {
        return ({ stocks_vn: 'Cổ phiếu VN', stocks_global: 'Cổ phiếu quốc tế', crypto: 'Crypto', gold: 'Vàng', cash_savings: 'Tiền mặt', real_estate_vn: 'Bất động sản', bonds_vn: 'Trái phiếu' })[name] || name;
    }
}());
