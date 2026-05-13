# Phase 4A — Financial Twin Conservative MVP (Chi Tiết Triển Khai)

> **Đây là phase wow-factor đầu tiên: turn tracking → predictive future vision.**
>
> **Thời gian ước tính:** ~3 tuần (15-18 ngày dev với Claude Code velocity)
> **Mục tiêu cuối Phase:** User có thể xem "Bé Tiền năm 2030/2035" qua Telegram (text + PNG chart) hoặc Mini App basic, với probability cone P10/P50/P90 từ Monte Carlo simulation, kèm Optimal trajectory comparison.
> **Điều kiện "Done":** Twin engine ship, weekly cron chạy stable, Telegram + Mini App basic surface working, prediction snapshots được store để 6 tháng sau có "predictions vs actual".
>
> **Prerequisites:**
> - Phase 3.9 (market data real) đã ship — μ, σ historical lấy từ real provider data.
> - Phase 3.9.5 (UX polish) đã ship — menu Tài sản / Cashflow / Market clean để Twin reuse.
> - Phase 3.8 Wealth Completion (rental, multi-income, recurring, goals) — Twin cần snapshot net worth chính xác.

---

## 🎯 Triết Lý Thiết Kế Phase 4A

### 1. "Probability Over Precision" (Strategy Principle #3)
Không hiển thị single-number predictions. Mọi projection đều có cone P10/P50/P90 (10th/50th/90th percentile). Frame copy honestly: "có thể nằm trong khoảng" — không bao giờ "sẽ là".

### 2. "Conservative MVP — Cut Ruthlessly"
Tham vọng Twin lớn (life event simulator, what-if mua nhà, retirement planner). MVP scope **chỉ 2 trajectories**: Current (BAU) và Optimal (+10% savings, rebalance theo target allocation). Mọi thứ khác defer Phase 4B.

### 3. "Trust Through Transparency"
Mỗi prediction lưu snapshot vào `twin_projections` table. Sau 6 tháng có data để render "predictions vs actual" — chính là moat ở Phase 4B. Phase 4A đặt foundation, không hiển thị accuracy tracking ngay.

### 4. "Channel-Agnostic Foundation"
User đã confirm sẽ mở rộng Zalo sau Telegram. Twin surface phải đi qua `Notifier` port + `ContentRenderer` abstraction để Phase 5+ thêm Zalo adapter không phải refactor. Mini App webview cũng phải agnostic (Telegram WebApp SDK trước, Zalo Mini Program sau dùng cùng API endpoint).

### 5. "Weekly Heavy, Daily Light"
Monte Carlo 1000 paths × multi-asset × 10y là expensive. Weekly cron (Sunday 23:00) chạy cho tất cả active users. Morning briefing chỉ show delta giữa actual net worth (cập nhật real-time) và cone snapshot mới nhất. On-demand recompute trigger khi user thay đổi asset > 5% net worth.

---

## 📅 Phân Bổ Thời Gian (~3 Tuần)

| Tuần | Focus | Deliverable chính |
|------|-------|-------------------|
| **Tuần 1** | Engine + Persistence | Monte Carlo simulator, asset class distributions, `twin_projections` migration, weekly cron skeleton |
| **Tuần 2** | Telegram Surface + Optimal Trajectory | Twin menu entry, PNG chart render, morning briefing integration, optimal trajectory engine + target allocation per wealth level |
| **Tuần 3** | Mini App Basic + Polish | Mini App webview shell, Twin dashboard layout, API endpoint, channel-agnostic refactor, trust framing copy, perf tuning, regression |

### Critical Path

```
S1-S6 (Engine, Tuần 1)
   ↓
S7-S11 (Persistence + Cron, Tuần 1 cuối)
   ↓
S12-S16 (Telegram surface, Tuần 2 đầu) ─┬→ S17-S20 (Mini App, Tuần 3)
S21-S23 (Optimal trajectory, Tuần 2 cuối) ┘
   ↓
S24-S27 (Polish + Trust + Perf + Tests, Tuần 3 cuối)
```

Engine (Epic 1) là blocker cho mọi thứ. Mini App (Epic 4) độc lập với Telegram surface (Epic 3) — có thể parallel sau khi engine xong.

---

## 🗂️ Cấu Trúc Thay Đổi (Files Touched)

```
finance_assistant/
├── content/
│   ├── twin_copy.yaml                       # ⭐ NEW — Bé Tiền Twin narratives, cone framings, trust copy
│   └── menu_copy.yaml                       # ⭐ — Thêm entry "🔮 Twin" trong main menu
│
├── backend/
│   ├── twin/                                # ⭐ NEW MODULE
│   │   ├── __init__.py
│   │   ├── engine/
│   │   │   ├── monte_carlo.py               # Core simulator (lognormal multi-asset)
│   │   │   ├── distributions.py             # Asset class μ, σ table
│   │   │   ├── cone_aggregator.py           # P10/P50/P90 extraction per year
│   │   │   └── optimal_trajectory.py        # Rebalance + savings boost simulation
│   │   ├── allocation/
│   │   │   ├── target_allocation.py         # Target % per wealth level
│   │   │   └── rebalance_calculator.py      # Suggested allocation delta
│   │   ├── services/
│   │   │   ├── twin_projection_service.py   # Orchestrate: snapshot → MC → store
│   │   │   ├── twin_query_service.py        # Read latest projection + actual delta
│   │   │   └── twin_chart_service.py        # PNG render (matplotlib)
│   │   └── schedulers/
│   │       └── weekly_twin_updater.py       # Sunday 23:00 cron
│   │
│   ├── bot/handlers/
│   │   ├── twin_handler.py                  # ⭐ NEW — Telegram Twin menu actions
│   │   └── briefing.py                      # ⭐ — Add Twin delta line to morning briefing
│   │
│   ├── intent/handlers/
│   │   └── query_twin.py                    # ⭐ NEW — Intent QUERY_TWIN handler
│   │
│   ├── api/
│   │   └── routes/
│   │       └── twin.py                      # ⭐ NEW — REST endpoint GET /api/twin/{user_id}
│   │
│   ├── adapters/
│   │   ├── chart_renderer.py                # ⭐ NEW — matplotlib → PNG bytes
│   │   └── miniapp_auth.py                  # ⭐ NEW — Telegram WebApp initData verify
│   │
│   └── ports/
│       └── content_renderer.py              # ⭐ NEW — Channel-agnostic content (text + chart_url)
│
├── miniapp/                                 # ⭐ NEW (basic Telegram WebApp)
│   ├── index.html
│   ├── src/
│   │   ├── main.ts                          # WebApp SDK init
│   │   ├── views/
│   │   │   └── TwinDashboard.tsx
│   │   ├── components/
│   │   │   ├── ConeChart.tsx                # Plotly/Chart.js cone rendering
│   │   │   ├── ScenarioToggle.tsx           # Current vs Optimal
│   │   │   └── KPICards.tsx
│   │   └── api/twinClient.ts
│   └── vite.config.ts
│
├── alembic/versions/
│   └── 20260720_phase4a_twin_projections.py # ⭐ NEW migration
│
└── tests/
    └── test_phase_4a/
        ├── test_monte_carlo.py              # Engine correctness (deterministic seed)
        ├── test_cone_aggregator.py          # P10/P50/P90 boundary tests
        ├── test_optimal_trajectory.py
        ├── test_target_allocation.py        # 4 wealth levels mapping
        ├── test_twin_projection_service.py  # Integration: assets → projection
        ├── test_twin_chart_service.py       # PNG render smoke
        ├── test_weekly_updater.py
        ├── test_twin_handler.py             # Telegram surface
        ├── test_query_twin.py
        ├── test_twin_api.py                 # REST endpoint
        ├── test_miniapp_auth.py             # WebApp initData verify
        └── test_perf_twin.py                # MC < 2s, weekly cron < 5min/100u
```

**Note:** Phase 4A có 1 migration mới (`twin_projections`), không modify migration cũ.

---

## 🗄️ Database Schema

### Table `twin_projections`

```sql
CREATE TABLE twin_projections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    computed_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    horizon_years   INTEGER NOT NULL,                -- 5 hoặc 10
    scenario        VARCHAR(20) NOT NULL,            -- 'current' | 'optimal'
    -- Inputs snapshot (frozen at compute time)
    base_net_worth      NUMERIC(20, 2) NOT NULL,
    monthly_savings     NUMERIC(20, 2) NOT NULL,
    allocation_snapshot JSONB NOT NULL,              -- {stocks: %, crypto: %, gold: %, cash: %, real_estate: %}
    -- Outputs (cone per year)
    cone_data       JSONB NOT NULL,                  -- [{year: 1, p10: ..., p50: ..., p90: ...}, ...]
    -- Metadata
    sim_paths       INTEGER NOT NULL DEFAULT 1000,
    seed            BIGINT,                          -- reproducibility
    engine_version  VARCHAR(20) NOT NULL,            -- '4a.1.0'
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX idx_twin_proj_user_latest ON twin_projections(user_id, computed_at DESC);
CREATE INDEX idx_twin_proj_user_scenario ON twin_projections(user_id, scenario, computed_at DESC);
```

**Why JSONB cho cone_data:** Cone shape có thể thay đổi (e.g. thêm P25/P75 sau), JSONB tránh migration mỗi lần. Trade-off: kém query-able — chấp nhận vì query pattern luôn là "load full cone cho 1 user latest".

**Soft delete:** Không cần — projection là derived data, có thể recompute. Giữ history > 6 tháng để phục vụ Phase 4B "predictions vs actual".

---

## 🔧 Epic 1 — Twin Engine (Monte Carlo Core)

**Goal:** Build pure-function Monte Carlo simulator: input (current portfolio, monthly savings, horizon, allocation strategy) → output (cone data per year). Không touch DB, không touch Telegram — pure compute layer.

### S1 — Asset class return distributions

**Layer:** module data + service
**File:** `backend/twin/engine/distributions.py`

Define μ (mean annual return), σ (annual std) per asset class dựa vào historical VN data + global benchmarks:

| Asset class | μ (annual) | σ (annual) | Source |
|-------------|-----------|-----------|--------|
| `stocks_vn` | 11% | 22% | VN-Index 2015-2025 historical |
| `stocks_global` | 8% | 16% | S&P 500 long-term |
| `crypto` | 25% | 65% | BTC + ETH 2018-2025, capped to avoid extreme tails |
| `gold` | 6% | 14% | SJC 2015-2025 |
| `cash_savings` | 5.5% | 1% | VN bank deposit rate range |
| `real_estate_vn` | 9% | 12% | Vietnamese residential index (proxy) |
| `bonds_vn` | 6% | 4% | Government bond yields |

**Acceptance:**
- [ ] `get_distribution(asset_class: str) → ReturnDistribution(mu, sigma, source_note)` API
- [ ] Source citations documented in module docstring
- [ ] Unit test: all 7 asset classes return non-zero, σ > 0
- [ ] Config externalizable to YAML for future tuning (do NOT hardcode in code per CLAUDE.md content rule)

### S2 — Monte Carlo simulator (single asset)

**Layer:** engine
**File:** `backend/twin/engine/monte_carlo.py`

Lognormal model: yearly return `r_t ~ LogNormal(μ - σ²/2, σ)`. Price path `V_t = V_{t-1} × (1 + r_t) + monthly_contrib × 12`.

**Acceptance:**
- [ ] `simulate_single_asset(initial: Decimal, monthly_contrib: Decimal, dist: ReturnDistribution, years: int, paths: int = 1000, seed: int = None) → ndarray[paths, years]`
- [ ] Decimal preserved at boundary, internal compute via numpy float64 (compromise — projection inherently imprecise)
- [ ] Deterministic with seed (regression-friendly)
- [ ] Perf: 1000 paths × 10y < 50ms
- [ ] Unit test: P50 of 10y stocks_vn ≈ initial × (1.11)^10 ± 10%

### S3 — Multi-asset portfolio simulation

**Layer:** engine
**File:** `backend/twin/engine/monte_carlo.py`

Combine N asset class simulations with correlation matrix (correlations: stocks_vn ↔ crypto = 0.3, stocks_vn ↔ gold = -0.1, others ≈ 0).

**Acceptance:**
- [ ] `simulate_portfolio(allocation: dict[asset_class, Decimal], monthly_savings: Decimal, savings_split: dict[asset_class, float], horizon: int) → ndarray[paths, years]`
- [ ] Correlation matrix configurable (default in YAML)
- [ ] Per-asset simulation results aggregated per path
- [ ] Perf: 5 asset classes × 1000 paths × 10y < 1.5s

### S4 — Cone aggregator (P10/P50/P90 extraction)

**Layer:** engine
**File:** `backend/twin/engine/cone_aggregator.py`

Transform `ndarray[paths, years]` → list of `(year, p10, p50, p90)`.

**Acceptance:**
- [ ] `aggregate_cone(sim_result: ndarray, percentiles: list[int] = [10, 50, 90]) → list[ConePoint]`
- [ ] Year 0 = today's net worth (deterministic, all percentiles equal)
- [ ] Return Decimal for display, round to nearest 1000 VND
- [ ] Validate monotonic: p10 ≤ p50 ≤ p90 cho mỗi year (assertion)

### S5 — Pure-function integration test

**Layer:** test
**File:** `tests/test_phase_4a/test_monte_carlo.py`

End-to-end engine test with fixture portfolio (Mass Affluent persona, 500tr net worth, 60% stocks, 20% gold, 20% cash, save 15tr/month).

**Acceptance:**
- [ ] Deterministic with seed=42 → exact cone values asserted (golden file)
- [ ] P50 at year 10 between 1.2 tỷ và 2.5 tỷ (sanity range for Mass Affluent baseline)
- [ ] No exceptions, no NaN/Inf in output

### S6 — Engine version stamp

**Layer:** engine
**File:** `backend/twin/engine/__init__.py`

Constant `ENGINE_VERSION = "4a.1.0"` stored on every `twin_projections` row → future-Phuong có thể filter "predictions made by old engine" khi accuracy tracking.

**Acceptance:**
- [ ] Constant exported và consumed by `twin_projection_service`
- [ ] Bump rule documented: minor bump khi tuning distributions, major bump khi đổi model

---

## 🔧 Epic 2 — Persistence & Scheduler

**Goal:** Wrap engine với storage layer + scheduler. Lock down "what was predicted on which date" để 6 tháng sau có ground truth comparison.

### S7 — `twin_projections` migration

**Layer:** alembic
**File:** `alembic/versions/20260720_phase4a_twin_projections.py`

SQL như định nghĩa ở section "Database Schema". Multi-tenant ready với user_id.

**Acceptance:**
- [ ] `alembic upgrade head` apply clean
- [ ] Indexes created
- [ ] `alembic downgrade -1` reversible
- [ ] No data loss on existing tables

### S8 — `twin_projection_service.compute_and_store`

**Layer:** service
**File:** `backend/twin/services/twin_projection_service.py`

Pipeline: load user's current net worth + allocation → call engine → aggregate cone → INSERT row.

**Acceptance:**
- [ ] Async method `compute_and_store(user_id: UUID, scenario: Literal['current', 'optimal'], horizon: int = 10) → TwinProjection`
- [ ] Reads current portfolio via existing `wealth_service.get_current_portfolio`
- [ ] Computes monthly_savings from `cashflow_service.last_3_month_avg_savings`
- [ ] **NO `db.commit()`** — caller owns transaction (CLAUDE.md layer contract)
- [ ] Both scenarios stored in same call (1 INSERT for current, 1 for optimal)
- [ ] Engine version stamped

### S9 — Weekly cron updater

**Layer:** scheduler
**File:** `backend/twin/schedulers/weekly_twin_updater.py`

Runs Sunday 23:00 ICT. Iterates active users (logged in last 30 days), calls `compute_and_store` for each.

**Acceptance:**
- [ ] Scheduled via existing scheduler infra (check `backend/scheduled/` pattern)
- [ ] Batch processing với concurrency limit (10 users parallel)
- [ ] Per-user failure isolated (logged, not crash batch)
- [ ] Metrics: total users, succeeded, failed, total_time
- [ ] Perf budget: 100 users < 5 minutes (10 in parallel, each ~3s)

### S10 — On-demand recompute trigger

**Layer:** service + event hook
**File:** `backend/twin/services/twin_projection_service.py`, asset entry hooks

Hook into asset CREATE / UPDATE / DELETE: if `|delta_net_worth| / current_net_worth > 5%` → enqueue background task `compute_and_store`.

**Acceptance:**
- [ ] `should_recompute(user_id, delta_net_worth) → bool` helper
- [ ] Background task (asyncio.create_task per CLAUDE.md webhook path rule)
- [ ] Debounce: don't recompute if last compute < 1 hour ago
- [ ] Test: simulate 3 quick consecutive edits → only 1 recompute

### S11 — Daily snapshot delta (read-only)

**Layer:** service
**File:** `backend/twin/services/twin_query_service.py`

No DB write. Reads latest projection + current actual net worth → compute "actual vs P50 delta".

**Acceptance:**
- [ ] `get_twin_snapshot(user_id) → TwinSnapshot(latest_cone, actual_net_worth, delta_vs_p50, cone_age_days)`
- [ ] Used by morning briefing
- [ ] `cone_age_days` exposed để UI có thể show "Cone updated 3 days ago"
- [ ] Stale handling: nếu cone > 14 days (cron missed) → flag `is_stale=True`

---

## 🔧 Epic 3 — Telegram Twin Surface

**Goal:** Twin entry point trong Telegram menu, PNG chart, morning briefing integration, narrative LLM-generated.

### S12 — Menu entry "🔮 Twin"

**Layer:** content + handler
**Files:** `content/menu_copy.yaml`, `backend/bot/handlers/menu_handler.py`

Top-level menu item next to Tài sản / Dòng tiền / Thị trường / Mục tiêu.

**Acceptance:**
- [ ] Menu button `🔮 Bé Tiền tương lai`
- [ ] Click → submenu: `📈 Xem trajectory` / `⚖️ So sánh Optimal` / `📊 Mở Mini App` / `ℹ️ Twin hoạt động ra sao`
- [ ] Adaptive intro per wealth level (Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa)
- [ ] vi-localization-checker pass

### S13 — PNG cone chart renderer

**Layer:** adapter + service
**Files:** `backend/adapters/chart_renderer.py`, `backend/twin/services/twin_chart_service.py`

Matplotlib renders cone (shaded between P10 and P90, line at P50, optionally overlay Optimal cone in second color).

**Acceptance:**
- [ ] `render_cone_chart(cone: list[ConePoint], optimal: list[ConePoint] | None, width: int = 800, height: int = 600) → bytes`
- [ ] Vietnamese labels (`content/twin_copy.yaml`), VND formatted (tỷ / triệu)
- [ ] Watermark "Bé Tiền — dự phóng, không phải dự đoán" ở góc
- [ ] Perf: < 500ms per chart
- [ ] Test: golden image comparison for fixed fixture

### S14 — Twin handler — view trajectory

**Layer:** bot handler
**File:** `backend/bot/handlers/twin_handler.py`

Action `(twin, view_current)` → load snapshot via `twin_query_service` → render PNG → send photo + caption.

**Acceptance:**
- [ ] Caption Vietnamese, Bé Tiền persona, includes cone range "có thể nằm trong khoảng X tỷ — Y tỷ năm 2036"
- [ ] Caption notes "Cập nhật lần cuối N ngày trước"
- [ ] Empty state: net worth < 10tr → message "Bé Tiền chưa đủ data, thêm tài sản trước nhé"
- [ ] Uses `Notifier` port, NOT direct telegram_service (layer contract)

### S15 — Morning briefing Twin line

**Layer:** handler
**File:** `backend/bot/handlers/briefing.py`

Add 1-2 line section: "🔮 Trajectory: actual {NW} vs P50 dự phóng {P50}. {emoji} {behind/on-track/ahead}".

**Acceptance:**
- [ ] Only show if Twin projection exists (skip for new users)
- [ ] Color/emoji: ahead +5% (🚀), on-track ±5% (🎯), behind -5% (🌱 + encouraging copy)
- [ ] Copy via `content/twin_copy.yaml`
- [ ] Persona check: NEVER harsh on "behind" — Bé Tiền tone

### S16 — LLM narrative ("Bé Tiền năm 2036")

**Layer:** service + LLM
**File:** `backend/twin/services/twin_query_service.py`

Optional advisory call (Tier 2 LLM) generates 2-3 sentence narrative from cone data. Caching key includes user_id + cone_hash.

**Acceptance:**
- [ ] Prompt template in `content/twin_copy.yaml` → `twin_narrative_prompt`
- [ ] DeepSeek call via existing `llm_service` (no direct adapter)
- [ ] Cache TTL 7 days (same as weekly cone)
- [ ] Schema-validate output (length 50-200 chars, no markdown)
- [ ] Fallback to template-based narrative nếu LLM fail

---

## 🔧 Epic 4 — Mini App Basic Twin Dashboard

**Goal:** Telegram WebApp basic — 1 view (Twin dashboard). Architect channel-agnostic để Phase 5+ thêm Zalo Mini Program dùng cùng backend API.

### S17 — Mini App webview shell

**Layer:** frontend (new)
**Files:** `miniapp/index.html`, `miniapp/src/main.ts`, `miniapp/vite.config.ts`

Vite + TypeScript + React (or Preact for size). Telegram WebApp SDK integrated.

**Acceptance:**
- [ ] Built bundle < 200KB gzipped
- [ ] WebApp SDK `init`, theme params applied (dark/light)
- [ ] Hosted at `https://app.bétiền.vn/twin` (or staging URL TBD)
- [ ] Telegram bot button "📊 Mở Twin Dashboard" launches webview với initData

### S18 — Twin dashboard layout

**Layer:** frontend
**Files:** `miniapp/src/views/TwinDashboard.tsx`, `miniapp/src/components/*.tsx`

Layout: header (net worth + delta) → cone chart (Chart.js or Plotly) → scenario toggle (Current ↔ Optimal) → KPI cards (P10/P50/P90 at year 5 and 10) → CTA "Thay đổi để đạt Optimal".

**Acceptance:**
- [ ] Cone chart interactive: hover/tap → tooltip với year + range
- [ ] Scenario toggle smooth (no full reload)
- [ ] Responsive 320px-768px
- [ ] Loading skeleton while API fetch
- [ ] Empty state matches Telegram empty state

### S19 — REST API endpoint

**Layer:** API route
**File:** `backend/api/routes/twin.py`

`GET /api/twin?scenario=current` → JSON projection. Auth via Telegram WebApp `initData` HMAC verify.

**Acceptance:**
- [ ] Endpoint returns `{base_net_worth, allocation, cone: [...], computed_at, scenario, engine_version}`
- [ ] `initData` HMAC validated với bot token (per Telegram WebApp spec)
- [ ] 401 if invalid initData
- [ ] Caching: ETag based on `computed_at`, 304 on match
- [ ] Channel-agnostic: endpoint không assume Telegram — auth layer separate

### S20 — Deep-link integration

**Layer:** bot handler + content
**Files:** `backend/bot/handlers/twin_handler.py`, `content/menu_copy.yaml`

Action `(twin, open_miniapp)` → send inline button với `web_app: {url: ...}` payload.

**Acceptance:**
- [ ] Inline button "📊 Mở Twin Dashboard" trong Twin submenu + sau morning briefing
- [ ] URL includes user context (no PII, just session token nếu cần)
- [ ] Fallback message nếu user on platform không support WebApp

---

## 🔧 Epic 5 — Optimal Trajectory & Allocation

**Goal:** Compute "what if user save +10% và rebalance theo target allocation cho wealth level" — show cone tốt hơn bao nhiêu.

### S21 — Target allocation per wealth level

**Layer:** module
**File:** `backend/twin/allocation/target_allocation.py`

| Wealth Level | Stocks VN | Stocks Global | Crypto | Gold | Cash | Real Estate |
|--------------|-----------|---------------|--------|------|------|-------------|
| Khởi Đầu (0-30tr) | 20% | 0% | 5% | 10% | 65% | 0% |
| Trẻ Năng Động (30-200tr) | 40% | 10% | 10% | 10% | 30% | 0% |
| Trung Lưu Vững (200tr-1 tỷ) | 35% | 15% | 5% | 15% | 15% | 15% |
| Tinh Hoa (1 tỷ+) | 25% | 20% | 5% | 15% | 10% | 25% |

Source citation in module docstring (rule-of-thumb, not investment advice — disclaimer mandatory).

**Acceptance:**
- [ ] `get_target_allocation(wealth_level: WealthLevel) → dict[asset_class, float]`
- [ ] Sums to 1.0 ± 0.001
- [ ] Externalizable to `content/allocation_targets.yaml` for tuning without redeploy
- [ ] Disclaimer "Đây là gợi ý chung, không phải lời khuyên đầu tư" prominent

### S22 — Optimal trajectory simulator

**Layer:** engine
**File:** `backend/twin/engine/optimal_trajectory.py`

Same Monte Carlo as Epic 1 but:
1. Initial allocation rebalanced to target (sell over, buy under)
2. Monthly savings = current × 1.10
3. New savings split per target allocation

**Acceptance:**
- [ ] `simulate_optimal(user_portfolio, wealth_level, horizon, savings_boost=1.10) → ndarray`
- [ ] Reuses `simulate_portfolio` from Epic 1
- [ ] Returns same shape as current trajectory (for direct comparison)
- [ ] Tax / transaction cost ignored (MVP simplification, documented)

### S23 — Comparison handler (Telegram)

**Layer:** bot handler
**File:** `backend/bot/handlers/twin_handler.py`

Action `(twin, compare_optimal)` → render dual-cone chart (Current + Optimal overlay) → Vietnamese explainer of the delta + concrete action prompts ("Tăng tiết kiệm 10%", "Rebalance crypto từ X% → Y%").

**Acceptance:**
- [ ] Dual cone visible với legend
- [ ] Caption surfaces 2-3 actionable steps (savings + rebalance)
- [ ] Concrete numbers: "Năm 2036 có thể tăng từ 4.2 tỷ → 5.8 tỷ (+38%)"
- [ ] Bé Tiền persona: encouraging, not preachy
- [ ] CTA "Bắt đầu kế hoạch" → defer Phase 4B (just informative for MVP)

---

## 🔧 Epic 6 — Channel-Agnostic Foundation & Polish

**Goal:** Lock down Twin codepath để Phase 5 thêm Zalo dễ. Plus trust framing, perf, tests.

### S24 — `ContentRenderer` port

**Layer:** ports
**File:** `backend/ports/content_renderer.py`

Protocol interface: `render_twin_view(snapshot) → ChannelContent(text, images: list[bytes], buttons: list[Button])`. Channel-specific adapters (TelegramAdapter, future ZaloAdapter) consume.

**Acceptance:**
- [ ] Protocol defined with `render_twin_view`, `render_briefing`, `render_milestone`
- [ ] `TelegramContentRenderer` implementation passes existing twin handler tests
- [ ] Twin handler refactored to call port, not telegram directly
- [ ] Stub `ZaloContentRenderer` file with `raise NotImplementedError` + TODO comment (intent signal only, not wired)
- [ ] Architecture decision recorded in `docs/architecture/twin-channel-abstraction.md`

### S25 — Trust framing audit

**Layer:** content YAML
**File:** `content/twin_copy.yaml`

Ensure EVERY user-facing Twin string includes uncertainty framing.

**Acceptance:**
- [ ] No copy says "sẽ là", "chắc chắn", "dự đoán" — always "có thể", "dự phóng", "khả năng"
- [ ] Watermark on every chart
- [ ] FAQ entry "Tại sao Bé Tiền không cho con số chính xác?" trong submenu Twin
- [ ] vi-localization-checker pass + manual read-aloud test

### S26 — Performance benchmarks

**Layer:** test
**File:** `tests/test_phase_4a/test_perf_twin.py`

**Acceptance:**
- [ ] Single user Monte Carlo (5 asset, 1000 paths, 10y): p95 < 2s
- [ ] Weekly cron 100 users: < 5 minutes total
- [ ] Chart PNG render: p95 < 500ms
- [ ] API endpoint `GET /api/twin`: p95 < 200ms (cached cone, no recompute)
- [ ] Mini App bundle: gzipped < 200KB
- [ ] Benchmark CSV saved to `docs/current/phase-4A/phase-4A-benchmark.md`

### S27 — Test suite + quality gates

**Layer:** test
**Files:** `tests/test_phase_4a/*`

**Acceptance:**
- [ ] All Epic 1-5 unit tests pass
- [ ] Integration: full pipeline from fake portfolio → cron → DB → query → handler → mocked Telegram send
- [ ] `uv run pytest tests/test_phase_4a/` green
- [ ] `uv run ruff check .` clean
- [ ] `layer-contract-checker` agent pass
- [ ] `vi-localization-checker` agent pass
- [ ] `prompt-tester` agent pass on `twin_narrative_prompt`

---

## 📐 Layer Mapping & Contract Compliance

| Story | Layers touched | Critical contract concerns |
|-------|---------------|----------------------------|
| S1-S6 | engine (pure) | Pure functions, no I/O, no DB |
| S7 | migration | Idempotent, reversible |
| S8 | service | NO `db.commit()` (caller owns) |
| S9 | scheduler/worker | Commit at worker boundary only |
| S10 | service + asyncio | Background task via `asyncio.create_task`, no LLM in webhook path |
| S11 | service (read) | Read-only, no commit |
| S12-S16 | content + bot handler + LLM service | Handler routes, service computes, NO direct telegram_service import |
| S13 | adapter | Chart adapter is the ONLY layer touching matplotlib |
| S17-S20 | frontend + API route | API auth at boundary, route thin → service |
| S19 | API | Decimal serialization, ETag, no business logic in route |
| S21-S22 | module + engine | Pure, allocation YAML-driven |
| S23 | handler | Reuse Epic 3 patterns |
| S24 | port + adapter | Telegram handler uses port, never direct |
| S25 | content | YAML-only, no hardcoded strings |
| S26 | benchmark | Offline, no prod hit |

**Quality gates** (run before merge):
- `uv run ruff check .`
- `uv run pytest tests/test_phase_4a/` (all pass)
- `uv run pytest tests/` (regression)
- `layer-contract-checker` agent — clean
- `vi-localization-checker` agent — clean
- `prompt-tester` agent — Twin narrative prompt OK

---

## ⚠️ Risk & Rollback

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Monte Carlo accuracy questioned by user | High | Medium | Trust framing copy (S25), watermark, FAQ |
| Weekly cron compute time blows up at scale | Medium | High | Concurrency limit, benchmark gate (S26), early alerting |
| Mini App auth bug → unauthorized access to other users' twins | Low | Critical | initData HMAC verify (S19), penetration test pre-launch |
| Asset class μ/σ outdated → cones unrealistic | Medium | Medium | YAML externalized (S1), document review cadence (annual) |
| Telegram non-premium users can't see custom emoji | Low | Low | Twin doesn't rely on custom emoji (matplotlib chart channel) |
| Zalo arrives later → channel abstraction premature | Low | Low | Single port interface, minimal stub (S24) — low cost |
| Engine version mismatch when reading old projections | Low | Medium | Stamp engine_version (S6), filter logic in Phase 4B accuracy tracking |
| Optimal trajectory advice triggers regulatory concern (investment advice) | Medium | High | Disclaimer prominent (S21), copy reviewed by legal |

**Rollback strategy:**
- Per-Story commits, can revert individual Story
- Migration reversible (S7)
- Twin menu entry behind feature flag `TWIN_ENABLED` (default true post-launch, can disable via env if cron fails)
- Mini App URL behind separate flag `TWIN_MINIAPP_ENABLED` — can disable webview while keeping Telegram surface

---

## ✅ Definition of Done

Phase 4A considered DONE when:

- [ ] All 27 Stories shipped với AC checked
- [ ] 6 Epic Issues closed on GitHub
- [ ] Manual TC suite signed off (see `phase-4A-test-cases.md`)
- [ ] `phase-status.yaml` updated: 4A → done, next phase → current
- [ ] `vi-localization-checker` pass
- [ ] `layer-contract-checker` pass
- [ ] `prompt-tester` pass on Twin prompts
- [ ] Pytest suite green (full repo, not just Phase 4A)
- [ ] Weekly cron deployed + observed for 2 consecutive Sundays without issue
- [ ] Performance benchmarks meet targets (S26)
- [ ] Mini App deployed to staging URL + smoke test via real Telegram premium account
- [ ] `phase-4A-deploy-announcements.md` written
- [ ] Architecture doc `twin-channel-abstraction.md` committed
- [ ] At least 5 internal users have viewed Twin and given feedback
- [ ] Branch `claude/phase-4a-docs-tAoJ0` (docs) + implementation branches merged

---

## 🚧 Out of Scope (Defer to Phase 4B / Later)

- ❌ Goal-locked trajectory ("để đạt goal X cần tiết kiệm Y") — Phase 4B
- ❌ Life event simulator (mua nhà, đẻ con, nghỉ hưu sớm) — Phase 4B
- ❌ "Predictions vs Actual" tracking UI — Phase 4B (data foundation laid here)
- ❌ Twin avatar character art / illustration — Phase 4.5 or later (chart-first MVP)
- ❌ Share-able Twin image (FB/Zalo) — Phase 4B
- ❌ Zalo Mini Program — Phase 5+ (architecture prepared via S24)
- ❌ Pattern-based cashflow forecasting v2 — Phase 4B
- ❌ Real peer cohort comparison — Phase 5
- ❌ ML-based trend prediction — Phase 8+
- ❌ Push notifications when projection updates dramatically — Phase 4B
- ❌ Multi-currency display — single VND focus throughout

---

## 🧭 Tư Vấn Sản Phẩm — Recommendations Cho Phase 4B+

Vì bạn yêu cầu tư vấn lộ trình, dưới đây là 5 khuyến nghị nối tiếp 4A:

### 1. Phase 4B nên bao gồm "Predictions vs Actual" SỚM
Sau 4A có 2-3 tháng snapshot dữ liệu. Render "Tháng 8 dự phóng tháng 11 = 520tr, thực tế = 535tr (+2.9%)" — đây là trust-builder mạnh nhất. Đừng để đến Tết mới làm — user mất niềm tin trước khi thấy bằng chứng đúng.

### 2. Goals integration mạnh tay ở 4B
Phase 3.8 đã có Goals. Phase 4B nên cho phép Twin "lock onto goal" — user chọn 1 goal → Twin compute "savings rate cần thiết để P50 chạm goal trong horizon". Đây là USP rõ ràng hơn Optimal trajectory generic.

### 3. Đừng vội build Life Event Simulator
Strategy đề cập "mua nhà / đẻ con / nghỉ hưu sớm" là wow nhưng rất phức tạp (tax, lãi suất vay, chi phí nuôi con VN). Đặt vào Phase 4C riêng (2-3 tuần) hoặc đợi sau Tết. Risk: user nhập input sai → output buồn cười → mất trust.

### 4. Zalo Mini Program nên là Phase 5 sub-phase
Telegram penetration VN ở mass affluent ~ 30%, Zalo ~ 90%. Sau Tết 2027 đưa Zalo lên là move chiến lược. Phase 4A's channel-agnostic foundation (S24) chuẩn bị cho điều này nhưng KHÔNG implement Zalo trong 4A — sẽ làm scope explode.

### 5. Cohort data → Behavioral Engine (Phase 5) cần soft launch sớm
Phase 5 (Behavioral Engine + Peer Benchmarking) chỉ value cao khi có ≥200 active users với 3+ tháng data. Soft launch tháng 6/2026 + tháng 7/8 ship Phase 4A = đầu Phase 5 (~tháng 9) mới có ~3 tháng cohort. Marginal. Suy nghĩ insert "Phase 4C: Cohort Bootstrapping" — synthetic cohort + invite-friend mechanic — để tăng N user trước khi build behavioral engine.

### Đề xuất roadmap update

| Phase | Timing | Note |
|-------|--------|------|
| 4A (this) | Late July 2026 | Twin Conservative MVP |
| **4B** | Mid August 2026 | Twin Polish + **Goals-locked trajectory** + **Predictions vs Actual UI** + Pattern-based cashflow forecasting v2 |
| **4C (new?)** | Late August 2026 | **Life Event Simulator** (mua nhà / nghỉ hưu) — chỉ build nếu 4A/4B feedback strong |
| 4.5 | Mid September | Achievement + Wealth Badges (private) |
| **5A (new split)** | Late September | Behavioral Engine (anomaly + nudges) — KHÔNG cần peer data |
| **5B (new split)** | Mid October | Peer Benchmarking — sau khi có ≥500 users |
| 6 | Late October | Household Mode |
| 7A | November | Tết Special Features |
| 7B | Jan-Feb 2027 | Pricing live + viral push + Zalo Mini Program kickoff |

**Critical insight:** Tết 2027 launch không cần Twin perfect. Cần Twin **trustworthy + sticky**. Predictions-vs-actual UI ở 4B = trust. Goals-locked trajectory + daily morning briefing Twin line = sticky. Đủ rồi. Đừng over-engineer life events trước Tết — risk thấp value cao là sau Tết.

---

*Document version: 1.0 — initial draft 2026-05-11*
*Update khi scope thay đổi hoặc discoveries trong implementation.*
