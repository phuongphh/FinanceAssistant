# Phase 4A — GitHub Issues

> **Reference:** [phase-4A-detailed.md](./phase-4A-detailed.md)
> **Structure:** Epic-as-parent / Story-as-child (consistent with Phase 3.5, 3.7, 3.8.5, 3.9, 3.9.5)
> **Total:** 6 Epics, 27 Stories, ~15-18 ngày work
> **Labels:** `phase-4a`, `twin`, plus per-Epic labels

---

## Phase Overview

Phase 4A là wow-factor đầu tiên: turn tracking → Financial Twin với probability cones (P10/P50/P90) qua Monte Carlo 1000 paths. Surface qua Telegram (text + PNG chart) và Mini App basic (1 dashboard view). Architecture channel-agnostic chuẩn bị Zalo expansion sau.

**Critical path:** Epic 1 (engine) → Epic 2 (persistence + cron) → Epic 3 (Telegram surface) + Epic 5 (optimal trajectory) parallel → Epic 4 (Mini App) → Epic 6 (channel abstraction + polish).

**Scope decisions locked:**
- Monte Carlo 1000 paths, lognormal per asset class (7 classes, μ/σ historical)
- 2 trajectories: Current + Optimal (+10% savings, rebalance theo wealth level)
- Weekly cron + daily snapshot delta (no daily MC recompute)
- Telegram + Mini App basic (NO Zalo at this phase — abstraction only)

---

# Epic 1: Twin Engine (Monte Carlo Core)

**Labels:** `epic`, `phase-4a`, `twin`, `engine`
**Estimate:** 3-4 ngày (Tuần 1)
**Goal:** Build pure-function Monte Carlo simulator. Pure compute, no I/O, no Telegram.

**Stories:** S1-S6

---

## [Story] P4A-S1: Asset class return distributions

**Labels:** `story`, `phase-4a`, `twin`, `engine`, `data`
**Parent:** Epic 1
**Estimate:** 0.5 ngày

### Description
Define μ (mean annual return) và σ (annual std) cho 7 asset classes dựa vào historical VN + global data. Externalizable YAML.

### Acceptance Criteria
- [ ] `backend/twin/engine/distributions.py` exports `get_distribution(asset_class) → ReturnDistribution`
- [ ] 7 classes: `stocks_vn`, `stocks_global`, `crypto`, `gold`, `cash_savings`, `real_estate_vn`, `bonds_vn`
- [ ] Source citation in docstring
- [ ] Externalizable to `content/twin_distributions.yaml`
- [ ] Unit test: all classes return non-zero μ, σ > 0
- [ ] Disclaimer "historical ≠ future" prominent

### Technical Notes
- VN-Index 2015-2025: μ ≈ 11%, σ ≈ 22%
- Crypto caps to avoid extreme tails

### Dependencies
None.

---

## [Story] P4A-S2: Monte Carlo simulator (single asset)

**Labels:** `story`, `phase-4a`, `twin`, `engine`
**Parent:** Epic 1
**Estimate:** 0.5 ngày

### Description
Lognormal return path simulation cho 1 asset class. Decimal at boundary, numpy float64 internally.

### Acceptance Criteria
- [ ] `simulate_single_asset(initial, monthly_contrib, dist, years, paths=1000, seed=None) → ndarray[paths, years]`
- [ ] Deterministic với seed
- [ ] Perf: 1000 paths × 10y < 50ms
- [ ] Unit test: P50 of 10y stocks_vn ≈ initial × 1.11^10 ± 10%
- [ ] No NaN/Inf in output

### Dependencies
S1.

---

## [Story] P4A-S3: Multi-asset portfolio simulation

**Labels:** `story`, `phase-4a`, `twin`, `engine`
**Parent:** Epic 1
**Estimate:** 1 ngày

### Description
Combine N asset class simulations với correlation matrix. Monthly savings split theo allocation.

### Acceptance Criteria
- [ ] `simulate_portfolio(allocation, monthly_savings, savings_split, horizon) → ndarray[paths, years]`
- [ ] Correlation matrix configurable (YAML default)
- [ ] Per-path aggregation correct
- [ ] Perf: 5 classes × 1000 paths × 10y < 1.5s
- [ ] Unit test: sum of allocation = 1.0 ± 0.001

### Dependencies
S1, S2.

---

## [Story] P4A-S4: Cone aggregator (P10/P50/P90)

**Labels:** `story`, `phase-4a`, `twin`, `engine`
**Parent:** Epic 1
**Estimate:** 0.25 ngày

### Description
Transform `ndarray[paths, years]` thành list of (year, p10, p50, p90).

### Acceptance Criteria
- [ ] `aggregate_cone(sim_result, percentiles=[10,50,90]) → list[ConePoint]`
- [ ] Year 0 deterministic (all percentiles = current NW)
- [ ] Decimal output, rounded to 1000 VND
- [ ] Monotonic assertion: p10 ≤ p50 ≤ p90 per year

### Dependencies
S3.

---

## [Story] P4A-S5: Engine integration test

**Labels:** `story`, `phase-4a`, `twin`, `engine`, `test`
**Parent:** Epic 1
**Estimate:** 0.5 ngày

### Description
End-to-end engine test với Mass Affluent fixture portfolio. Golden file pinned cho regression.

### Acceptance Criteria
- [ ] Seed=42 → exact cone values asserted
- [ ] Mass Affluent baseline: P50 year 10 ∈ [1.2 tỷ, 2.5 tỷ]
- [ ] Tests cho 4 wealth level fixtures
- [ ] No exceptions/NaN/Inf

### Dependencies
S1-S4.

---

## [Story] P4A-S6: Engine version stamp

**Labels:** `story`, `phase-4a`, `twin`, `engine`
**Parent:** Epic 1
**Estimate:** 0.1 ngày

### Description
Export `ENGINE_VERSION = "4a.1.0"` constant. Stamped on every projection row for future "predictions vs actual" filtering.

### Acceptance Criteria
- [ ] Constant defined in `backend/twin/engine/__init__.py`
- [ ] Consumed by `twin_projection_service`
- [ ] Bump rule documented in module docstring

### Dependencies
S1-S5.

---

# Epic 2: Persistence & Scheduler

**Labels:** `epic`, `phase-4a`, `twin`, `persistence`
**Estimate:** 2.5 ngày (Tuần 1 cuối + Tuần 2 đầu)
**Goal:** Wrap engine với storage + weekly cron + on-demand recompute. Lock down prediction snapshots cho future accuracy tracking.

**Stories:** S7-S11

---

## [Story] P4A-S7: Migration `twin_projections`

**Labels:** `story`, `phase-4a`, `twin`, `migration`
**Parent:** Epic 2
**Estimate:** 0.5 ngày

### Description
Alembic migration cho table `twin_projections` với multi-tenant user_id + JSONB cone data.

### Acceptance Criteria
- [ ] File: `alembic/versions/20260720_phase4a_twin_projections.py`
- [ ] Schema match `phase-4A-detailed.md` section "Database Schema"
- [ ] Indexes: `idx_twin_proj_user_latest`, `idx_twin_proj_user_scenario`
- [ ] `alembic upgrade head` clean
- [ ] `alembic downgrade -1` reversible
- [ ] No data loss on existing tables

### Dependencies
None.

---

## [Story] P4A-S8: `twin_projection_service.compute_and_store`

**Labels:** `story`, `phase-4a`, `twin`, `service`
**Parent:** Epic 2
**Estimate:** 1 ngày

### Description
Service orchestrates: load portfolio → engine → aggregate cone → INSERT (current + optimal). NO db.commit (layer contract).

### Acceptance Criteria
- [ ] Async `compute_and_store(user_id, scenario, horizon=10) → TwinProjection`
- [ ] Reads via `wealth_service` + `cashflow_service` (no raw SQL)
- [ ] Both scenarios computed in 1 call
- [ ] Engine version stamped
- [ ] NO `db.commit()` in service — caller commits
- [ ] Unit test với mocked engine + DB

### Dependencies
S6, S7, Epic 1.

---

## [Story] P4A-S9: Weekly cron updater

**Labels:** `story`, `phase-4a`, `twin`, `scheduler`
**Parent:** Epic 2
**Estimate:** 0.5 ngày

### Description
Sunday 23:00 ICT cron iterates active users (logged in 30d), computes both scenarios per user.

### Acceptance Criteria
- [ ] Scheduled via existing scheduler infra
- [ ] Concurrency limit 10 parallel
- [ ] Per-user failure isolated, logged
- [ ] Metrics emitted: total, succeeded, failed, total_time
- [ ] Perf: 100 users < 5 minutes
- [ ] Integration test với 5 fake users

### Dependencies
S8.

---

## [Story] P4A-S10: On-demand recompute trigger

**Labels:** `story`, `phase-4a`, `twin`, `service`
**Parent:** Epic 2
**Estimate:** 0.25 ngày

### Description
Asset CREATE/UPDATE/DELETE hooks → if NW delta > 5% → enqueue background recompute task.

### Acceptance Criteria
- [ ] `should_recompute(user_id, delta_net_worth) → bool`
- [ ] Background via `asyncio.create_task` (not in webhook critical path)
- [ ] Debounce: skip if last compute < 1h ago
- [ ] Test: 3 quick consecutive edits → only 1 recompute

### Dependencies
S8.

---

## [Story] P4A-S11: Daily snapshot delta (read service)

**Labels:** `story`, `phase-4a`, `twin`, `service`, `read`
**Parent:** Epic 2
**Estimate:** 0.25 ngày

### Description
Read-only service. Loads latest projection + current actual NW → returns delta vs P50.

### Acceptance Criteria
- [ ] `get_twin_snapshot(user_id) → TwinSnapshot(latest_cone, actual_nw, delta_vs_p50, cone_age_days, is_stale)`
- [ ] Stale flag if cone > 14 days old
- [ ] No DB write
- [ ] Used by morning briefing (S15)
- [ ] Unit test with fresh/stale/missing cone fixtures

### Dependencies
S8.

---

# Epic 3: Telegram Twin Surface

**Labels:** `epic`, `phase-4a`, `twin`, `telegram`
**Estimate:** 3 ngày (Tuần 2)
**Goal:** Twin menu entry, PNG chart, morning briefing line, LLM narrative.

**Stories:** S12-S16

---

## [Story] P4A-S12: Menu entry "🔮 Bé Tiền tương lai"

**Labels:** `story`, `phase-4a`, `twin`, `telegram`, `menu`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Top-level menu button. Submenu với 4 actions: view trajectory / compare optimal / open mini app / how Twin works.

### Acceptance Criteria
- [ ] Button "🔮 Bé Tiền tương lai" trong main menu
- [ ] Submenu structure per detailed.md
- [ ] Adaptive intro per 4 wealth levels
- [ ] Content qua `content/twin_copy.yaml`
- [ ] vi-localization-checker pass

### Dependencies
None (parallel with Epic 1-2).

---

## [Story] P4A-S13: PNG cone chart renderer

**Labels:** `story`, `phase-4a`, `twin`, `adapter`, `chart`
**Parent:** Epic 3
**Estimate:** 1 ngày

### Description
Matplotlib renders cone (shaded P10-P90, line P50). Watermark + Vietnamese labels.

### Acceptance Criteria
- [ ] `render_cone_chart(cone, optimal=None, width=800, height=600) → bytes`
- [ ] VND formatted (tỷ / triệu)
- [ ] Watermark "Bé Tiền — dự phóng, không phải dự đoán"
- [ ] Perf: < 500ms p95
- [ ] Golden image test for fixed fixture
- [ ] Chart adapter is ONLY layer touching matplotlib

### Dependencies
S4.

---

## [Story] P4A-S14: Twin handler — view trajectory

**Labels:** `story`, `phase-4a`, `twin`, `telegram`, `handler`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Action `(twin, view_current)` → snapshot via query service → render PNG → send photo + Vietnamese caption.

### Acceptance Criteria
- [ ] Caption: cone range "có thể nằm trong khoảng X — Y năm 2036"
- [ ] Cone age noted in caption
- [ ] Empty state for NW < 10tr
- [ ] Uses `Notifier` port (NOT direct telegram_service)
- [ ] Test with mocked notifier

### Dependencies
S11, S13.

---

## [Story] P4A-S15: Morning briefing Twin line

**Labels:** `story`, `phase-4a`, `twin`, `telegram`, `briefing`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Add 1-2 line section to morning briefing: actual vs P50 delta + emoji indicator.

### Acceptance Criteria
- [ ] Show only if projection exists
- [ ] Emoji: 🚀 ahead +5%, 🎯 ±5%, 🌱 behind (encouraging)
- [ ] Bé Tiền persona — NEVER harsh
- [ ] Copy via `content/twin_copy.yaml`
- [ ] No regression in existing briefing tests

### Dependencies
S11.

---

## [Story] P4A-S16: LLM narrative ("Bé Tiền năm 2036")

**Labels:** `story`, `phase-4a`, `twin`, `llm`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Optional Tier 2 LLM call generates 2-3 sentence narrative from cone data. Cached 7 days.

### Acceptance Criteria
- [ ] Prompt template in `content/twin_copy.yaml`
- [ ] Call via existing `llm_service` (DeepSeek)
- [ ] Cache key: user_id + cone_hash, TTL 7 days
- [ ] Output 50-200 chars, no markdown
- [ ] Template fallback if LLM fail
- [ ] `prompt-tester` agent pass

### Dependencies
S11.

---

# Epic 4: Mini App Basic Twin Dashboard

**Labels:** `epic`, `phase-4a`, `twin`, `miniapp`, `frontend`
**Estimate:** 3 ngày (Tuần 3 đầu)
**Goal:** Telegram WebApp basic — 1 view (Twin dashboard). Channel-agnostic API.

**Stories:** S17-S20

---

## [Story] P4A-S17: Mini App webview shell

**Labels:** `story`, `phase-4a`, `twin`, `miniapp`, `frontend`
**Parent:** Epic 4
**Estimate:** 1 ngày

### Description
Vite + TypeScript + (P)react. Telegram WebApp SDK integrated, theme params applied.

### Acceptance Criteria
- [ ] `miniapp/` folder với Vite config
- [ ] Bundle < 200KB gzipped
- [ ] WebApp SDK init, theme detection
- [ ] Hosted at staging URL
- [ ] Bot button launches webview

### Dependencies
None (parallel with Epic 1-3).

---

## [Story] P4A-S18: Twin dashboard layout

**Labels:** `story`, `phase-4a`, `twin`, `miniapp`, `frontend`
**Parent:** Epic 4
**Estimate:** 1 ngày

### Description
Header (NW + delta) → cone chart (Chart.js/Plotly) → scenario toggle → KPI cards (P10/P50/P90 year 5 + 10) → CTA.

### Acceptance Criteria
- [ ] Cone chart interactive (hover/tap tooltip)
- [ ] Scenario toggle smooth (no full reload)
- [ ] Responsive 320-768px
- [ ] Loading skeleton during API fetch
- [ ] Empty state mirrors Telegram

### Dependencies
S17, S19.

---

## [Story] P4A-S19: REST API endpoint `GET /api/twin`

**Labels:** `story`, `phase-4a`, `twin`, `api`, `auth`
**Parent:** Epic 4
**Estimate:** 0.5 ngày

### Description
JSON projection endpoint. Auth via Telegram WebApp initData HMAC.

### Acceptance Criteria
- [ ] `GET /api/twin?scenario=current` returns projection JSON
- [ ] initData HMAC validated với bot token
- [ ] 401 on invalid initData
- [ ] ETag based on `computed_at`, 304 on match
- [ ] No business logic in route (thin → service)
- [ ] Integration test: valid + invalid initData

### Dependencies
S11.

---

## [Story] P4A-S20: Deep-link from Telegram

**Labels:** `story`, `phase-4a`, `twin`, `telegram`, `miniapp`
**Parent:** Epic 4
**Estimate:** 0.25 ngày

### Description
Action `(twin, open_miniapp)` → inline button `web_app` payload. Also surface after morning briefing.

### Acceptance Criteria
- [ ] Button "📊 Mở Twin Dashboard" trong Twin submenu
- [ ] Button after morning briefing (optional)
- [ ] URL safe (no PII in path)
- [ ] Fallback text if user platform không support WebApp

### Dependencies
S17, S19.

---

# Epic 5: Optimal Trajectory & Allocation

**Labels:** `epic`, `phase-4a`, `twin`, `optimization`
**Estimate:** 2 ngày (Tuần 2 cuối)
**Goal:** Optimal trajectory engine + target allocation per wealth level + comparison handler.

**Stories:** S21-S23

---

## [Story] P4A-S21: Target allocation per wealth level

**Labels:** `story`, `phase-4a`, `twin`, `allocation`, `data`
**Parent:** Epic 5
**Estimate:** 0.5 ngày

### Description
Table mapping 4 wealth levels → target % per asset class. YAML externalized. Disclaimer mandatory.

### Acceptance Criteria
- [ ] `get_target_allocation(wealth_level) → dict[asset_class, float]`
- [ ] 4 levels mapped (Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa)
- [ ] Sums = 1.0 ± 0.001
- [ ] Externalizable to `content/allocation_targets.yaml`
- [ ] Disclaimer "không phải lời khuyên đầu tư" prominent

### Dependencies
None.

---

## [Story] P4A-S22: Optimal trajectory simulator

**Labels:** `story`, `phase-4a`, `twin`, `engine`
**Parent:** Epic 5
**Estimate:** 0.5 ngày

### Description
Reuse Monte Carlo engine với rebalanced allocation + 1.10x savings.

### Acceptance Criteria
- [ ] `simulate_optimal(user_portfolio, wealth_level, horizon, savings_boost=1.10) → ndarray`
- [ ] Reuses `simulate_portfolio` (S3)
- [ ] Same shape as current trajectory output
- [ ] Tax/transaction cost ignored (documented)
- [ ] Unit test với Mass Affluent fixture

### Dependencies
S3, S21.

---

## [Story] P4A-S23: Comparison handler (Telegram)

**Labels:** `story`, `phase-4a`, `twin`, `telegram`, `handler`
**Parent:** Epic 5
**Estimate:** 1 ngày

### Description
Action `(twin, compare_optimal)` → dual-cone chart + Vietnamese explainer + 2-3 actionable steps.

### Acceptance Criteria
- [ ] Dual cone with legend
- [ ] Caption: concrete numbers "tăng từ X → Y (+Z%)"
- [ ] 2-3 actionable steps (savings + rebalance)
- [ ] Bé Tiền tone: encouraging, not preachy
- [ ] CTA "Bắt đầu kế hoạch" → defer Phase 4B (informative only)

### Dependencies
S13, S22.

---

# Epic 6: Channel-Agnostic Foundation & Polish

**Labels:** `epic`, `phase-4a`, `twin`, `architecture`, `quality`
**Estimate:** 2.5 ngày (Tuần 3 cuối)
**Goal:** ContentRenderer port, trust framing, perf benchmarks, full test suite.

**Stories:** S24-S27

---

## [Story] P4A-S24: `ContentRenderer` port

**Labels:** `story`, `phase-4a`, `twin`, `architecture`, `port`
**Parent:** Epic 6
**Estimate:** 1 ngày

### Description
Protocol interface `render_twin_view` + others. Telegram impl + Zalo stub. Architecture doc.

### Acceptance Criteria
- [ ] Protocol in `backend/ports/content_renderer.py`
- [ ] `TelegramContentRenderer` impl passes Twin handler tests
- [ ] Twin handler refactored to use port (NOT direct telegram_service)
- [ ] Stub `ZaloContentRenderer` (raises NotImplementedError + TODO)
- [ ] Architecture decision doc: `docs/architecture/twin-channel-abstraction.md`

### Dependencies
S14, S23.

---

## [Story] P4A-S25: Trust framing audit

**Labels:** `story`, `phase-4a`, `twin`, `content`, `vi-localization`
**Parent:** Epic 6
**Estimate:** 0.5 ngày

### Description
Every Twin string MUST include uncertainty framing. "có thể", "dự phóng" — NEVER "sẽ", "chắc chắn".

### Acceptance Criteria
- [ ] Grep `content/twin_copy.yaml` for banned words → 0 hits
- [ ] Chart watermark verified on all cones
- [ ] FAQ entry "Tại sao Bé Tiền không cho con số chính xác?"
- [ ] vi-localization-checker pass
- [ ] Manual read-aloud test

### Dependencies
S12, S14, S16, S23.

---

## [Story] P4A-S26: Performance benchmarks

**Labels:** `story`, `phase-4a`, `twin`, `perf`, `test`
**Parent:** Epic 6
**Estimate:** 0.5 ngày

### Description
Benchmark suite for engine, cron, chart, API, bundle. Results documented.

### Acceptance Criteria
- [ ] MC single user p95 < 2s (5 assets, 1000 paths, 10y)
- [ ] Weekly cron 100 users < 5 min
- [ ] Chart PNG p95 < 500ms
- [ ] API `GET /api/twin` p95 < 200ms (cached)
- [ ] Mini App bundle gzipped < 200KB
- [ ] Results in `docs/current/phase-4A/phase-4A-benchmark.md`

### Dependencies
Epic 1-5.

---

## [Story] P4A-S27: Test suite + quality gates

**Labels:** `story`, `phase-4a`, `twin`, `test`, `quality`
**Parent:** Epic 6
**Estimate:** 0.5 ngày

### Description
Full Phase 4A test suite + quality gate agents.

### Acceptance Criteria
- [ ] All Epic 1-5 unit tests pass
- [ ] Integration test full pipeline
- [ ] `uv run pytest tests/test_phase_4a/` green
- [ ] `uv run pytest tests/` (regression) green
- [ ] `uv run ruff check .` clean
- [ ] `layer-contract-checker` agent pass
- [ ] `vi-localization-checker` agent pass
- [ ] `prompt-tester` agent pass on Twin prompts

### Dependencies
Epic 1-5 + S24-S26.

---

## Summary Table

| Epic | Stories | Estimate | Critical Path? |
|------|---------|----------|----------------|
| 1. Twin Engine | S1-S6 | 3-4 ngày | YES (blocker for all) |
| 2. Persistence | S7-S11 | 2.5 ngày | YES |
| 3. Telegram Surface | S12-S16 | 3 ngày | YES |
| 4. Mini App | S17-S20 | 3 ngày | Parallel with 3 |
| 5. Optimal Trajectory | S21-S23 | 2 ngày | After Engine |
| 6. Channel + Polish | S24-S27 | 2.5 ngày | Closes phase |

**Total:** 27 stories, ~16 ngày work + buffer = 3 tuần realistic.
