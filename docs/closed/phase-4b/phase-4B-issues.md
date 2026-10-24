# Phase 4B — GitHub Issues

**4 Epics, 24 Stories** (~18–22 dev days)

## Labels

| Label | Applied to |
|---|---|
| `phase-4b` | All stories |
| `twin-polish` | Epic 1 (S1–S5) |
| `life-events` | Epic 2 (S6–S13) |
| `cashflow-v2` | Epic 3 (S14–S20) |
| `zalo` | Epic 4 (S21–S24) |
| `db-migration` | Stories with schema changes |
| `perf` | Performance-critical stories |
| `llm` | Stories touching LLM prompts |
| `infrastructure` | Setup/config stories |

---

## Dependency Graph

```
S1──────────────────────────────────────────────────── (parallel, Epic 1)
S2──────────────────────────────────────────────────── (parallel, Epic 1)
S3──────────────────────────────────────────────────── (parallel, Epic 1)
S4──────────────────────────────────────────────────── (parallel, Epic 1)
S5──────────────────────────────────────────────────── (parallel, Epic 1)

S6 → S7 → S8 ──────────────────────────────────────── (Epic 2 critical path)
             ├─ S9 (Telegram flow)
             ├─ S11 (Mini App panel) ── (S9 ‖ S11 parallel)
             S9+S11 both done → S10 (impact chart) → S12 (narrative) → S13 (tests)

S14 → S15 → S16 → S17 ─────────────────────────────── (Epic 3 critical path)
                    ├─ S18 (chart)
                    ├─ S19 (morning briefing) ── (S18 ‖ S19 ‖ S20 parallel)
                    └─ S20 (Mini App)

S21 → S22 → S23 → S24  (Epic 4; S24 needs S17 done for alert engine)
```

---

## Epic 1: Twin Polish `[epic-twin-polish]`

**Goal:** Cải thiện chất lượng Financial Twin từ Phase 4A — accuracy tracking, narrative cá nhân hóa, UX comparison rõ ràng, và uncertainty insight.  
**Size:** 4 ngày  
**Dependencies:** Phase 4A ✅

---

### P4B-S1: Historical Accuracy Tracking

**Labels:** `phase-4b` `twin-polish` `db-migration`  
**Size:** 1 ngày  
**Depends on:** Phase 4A twin_projections table ✅

**User Story:**  
Là user đã dùng Financial Twin ≥ 2 tuần, tôi muốn biết dự báo tuần trước của Bé Tiền chính xác đến đâu so với thực tế — để tôi tin tưởng (hoặc nghi ngờ) các dự báo tương lai.

**Implementation tasks:**
- [ ] Alembic migration: `ALTER TABLE twin_projections ADD COLUMN actual_net_worth NUMERIC(20,2)`
- [ ] Cập nhật weekly cron: trước khi compute projection mới, query projection tuần trước → điền `actual_net_worth = current_net_worth`
- [ ] Thêm `accuracy_delta_pct` vào morning briefing service (hiện khi có ≥ 2 projections)
- [ ] Tone rules: actual < P10 → reassure; actual > P90 → celebrate; else → neutral

**Acceptance Criteria:**
- [ ] Migration không break existing `twin_projections` rows
- [ ] Cron điền `actual_net_worth` TRƯỚC khi tạo projection mới
- [ ] Morning briefing hiển thị: "Tuần trước Bé Tiền dự báo P50 = X, thực tế = Y (±Z%)"
- [ ] Chỉ hiển thị khi có ≥ 2 weekly projections
- [ ] Tone đúng theo 3 trường hợp (test with `prompt-tester` agent)

**Definition of Done:**
- [ ] Unit test: `test_accuracy_delta_calculation`
- [ ] Unit test: `test_cron_fills_actual_before_new_projection`
- [ ] Integration test: cron → fills actual → morning briefing shows delta

---

### P4B-S2: On-Demand Recompute Trigger

**Labels:** `phase-4b` `twin-polish`  
**Size:** 1 ngày  
**Depends on:** Phase 4A twin recompute task ✅

**User Story:**  
Khi tôi vừa thêm một khoản đầu tư lớn, tôi muốn Bé Tiền tự động cập nhật dự báo mà không cần đợi đến chủ nhật.

**Implementation tasks:**
- [ ] Thêm threshold check vào `asset_service.update_asset()` và `create_asset()`
- [ ] Implement `AssetSignificantChangeEvent` và publish khi `change_pct >= 0.05`
- [ ] Event consumer với 30-minute debounce per user_id
- [ ] Background task enqueue: `twin_recompute_task`
- [ ] Notification khi xong (qua existing Notifier port)

**Acceptance Criteria:**
- [ ] Asset change ≥ 5% net worth → recompute enqueued trong vòng 1 phút
- [ ] Recompute completes trong 30 phút kể từ event
- [ ] Asset change < 5% → KHÔNG trigger
- [ ] 3 asset changes trong 5 phút → chỉ 1 recompute (debounce)
- [ ] Notification gửi SAU khi recompute xong
- [ ] Layer contract: `asset_service` publish event, không recompute trực tiếp

**Definition of Done:**
- [ ] Unit test: `test_significant_change_threshold`
- [ ] Unit test: `test_debounce_multiple_events`
- [ ] Integration test: asset update → notification received

---

### P4B-S3: LLM Narrative v2

**Labels:** `phase-4b` `twin-polish` `llm`  
**Size:** 0.5 ngày  
**Depends on:** Phase 4A LLM narrative ✅

**User Story:**  
Tôi muốn Bé Tiền nói về tương lai tài chính của TÔI, không phải câu chung chung cho bất kỳ ai.

**Implementation tasks:**
- [ ] Thêm `wealth_level` vào LLM system context
- [ ] Thêm `top_asset_changes_30d` (top 2 by % change) vào context
- [ ] Thêm `has_life_events: bool` + `life_event_summary: str` vào context
- [ ] Cập nhật few-shot examples: loại bỏ generic phrases, thêm specific-số examples
- [ ] Chạy `prompt-tester` agent trước khi merge

**Acceptance Criteria:**
- [ ] Narrative đề cập wealth level (khác nhau giữa Tiết kiệm vs Thịnh vượng)
- [ ] Nếu user có life events → narrative nhắc ≥ 1 event cụ thể với số tiền
- [ ] Không có generic phrases: "tương lai tài chính của bạn", "bạn đang đi đúng hướng"
- [ ] `prompt-tester` agent: passes persona check + quality check

**Definition of Done:**
- [ ] Prompt updated trong `services/twin/narrative_service.py` (hoặc path tương đương)
- [ ] Prompt test cases added to `tests/prompts/test_twin_narrative.py`
- [ ] Prompt-tester agent run documented

---

### P4B-S4: Scenario Comparison UX Enhancement

**Labels:** `phase-4b` `twin-polish`  
**Size:** 1 ngày  
**Depends on:** Phase 4A Mini App ✅

**User Story:**  
Tôi muốn thấy rõ tôi được lợi bao nhiêu nếu chuyển từ Current sang Optimal — với số tiền cụ thể, không chỉ "tốt hơn".

**Implementation tasks:**
- [ ] Backend: tính delta % tại 2027, 2030, 2035 (optimal_p50 vs current_p50)
- [ ] Backend: tính "monthly savings needed" = (optimal_p50_2035 - current_p50_2035) / (months * multiplier)
- [ ] Mini App: thêm delta badges tại 3 milestone years
- [ ] Mini App: thêm CTA "Cần thêm X triệu/tháng để đạt Optimal"
- [ ] Mini App: tooltip giải thích Optimal assumption (+10% savings)

**Acceptance Criteria:**
- [ ] Delta badges hiển thị tại 2027, 2030, 2035
- [ ] CTA hiển thị số tiền cụ thể (rounded 500k)
- [ ] Tooltip giải thích assumption
- [ ] Mobile responsive (375px)

**Definition of Done:**
- [ ] API endpoint trả về `comparison_data: {milestones: [{year, current_p50, optimal_p50, delta_pct}], monthly_savings_needed}`
- [ ] Mini App renders component với E2E screenshot test

---

### P4B-S5: Twin Cone Uncertainty Breakdown

**Labels:** `phase-4b` `twin-polish` `perf`  
**Size:** 0.5 ngày  
**Depends on:** Phase 4A Monte Carlo engine ✅

**User Story:**  
Tôi muốn biết tại sao cone của tôi rộng — để tôi biết tài sản nào đang tạo ra sự bất định nhất.

**Implementation tasks:**
- [ ] `twin/engine/uncertainty.py`: `compute_uncertainty_breakdown(allocation, distributions)`
- [ ] API: thêm `uncertainty_contributors: [{asset_class, contribution_pct}]` vào projection response
- [ ] Mini App: small breakdown table dưới cone chart với tooltip

**Acceptance Criteria:**
- [ ] Top 2 asset classes theo contribution % hiển thị
- [ ] Contribution % sum ≈ 100% (top 2 có thể < 100% nếu có nhiều asset classes)
- [ ] Tooltip: "asset càng volatile → cone càng rộng"

**Definition of Done:**
- [ ] Unit test: `test_uncertainty_breakdown_weighted_by_allocation`
- [ ] Mini App renders breakdown table

---

## Epic 2: Life Event Simulator `[epic-life-events]`

**Goal:** Người dùng thêm mốc đời thực (mua nhà, kết hôn, con cái) và thấy impact lên Financial Twin.  
**Size:** 7 ngày  
**Dependencies:** Epic 2 requires Phase 4A Monte Carlo engine ✅

---

### P4B-S6: Life Event Data Model + Migration

**Labels:** `phase-4b` `life-events` `db-migration`  
**Size:** 0.5 ngày

**User Story:**  
Là developer, tôi cần DB schema và Pydantic models để lưu trữ life events của user.

**Implementation tasks:**
- [ ] Alembic migration: tạo bảng `life_events` (schema trong phase-4B-detailed.md)
- [ ] Pydantic: `LifeEventCreate`, `LifeEventRead`, `LifeEventUpdate`, `LifeEventImpact`
- [ ] `LifeEventType` enum (6 values)
- [ ] `life_event_service.py`: `create()`, `get_by_user()`, `update()`, `soft_delete()`
- [ ] Soft delete via `deleted_at` (never hard delete)

**Acceptance Criteria:**
- [ ] Migration runs on clean DB without errors
- [ ] Migration is reversible (downgrade works)
- [ ] `user_id` index created
- [ ] Pydantic models validate `event_type` enum
- [ ] `soft_delete()` sets `deleted_at`, không xóa row

**Definition of Done:**
- [ ] Migration file committed
- [ ] Unit tests: create, read, update, soft_delete
- [ ] `layer-contract-checker`: service không có `db.commit()`

---

### P4B-S7: Vietnamese Life Event Presets

**Labels:** `phase-4b` `life-events`  
**Size:** 0.5 ngày  
**Depends on:** S6

**User Story:**  
Khi tôi chọn "Mua nhà", tôi muốn Bé Tiền đề xuất sẵn con số phù hợp thị trường VN — tôi chỉ cần điều chỉnh nếu cần.

**Implementation tasks:**
- [ ] `life_events/presets.py`: dict per `LifeEventType` → `LifeEventPreset`
- [ ] Nghiên cứu và cite source cho mỗi preset value (comment trong code)
- [ ] Content strings (tooltip copy) → `content/vi.yaml` dưới key `life_event_presets`
- [ ] `get_preset(event_type: LifeEventType) -> LifeEventPreset`

**Acceptance Criteria:**
- [ ] 5 event types với VN-appropriate defaults (giá trị như trong phase-4B-detailed.md)
- [ ] Source cited trong comment (CBRE, VCCI, Bộ GD&ĐT)
- [ ] Tất cả copy trong `content/vi.yaml`
- [ ] `vi-localization-checker` agent passes

**Definition of Done:**
- [ ] `presets.py` với 5 presets
- [ ] Content YAML entry
- [ ] Unit test: `test_all_preset_types_have_values`

---

### P4B-S8: Monte Carlo Integration — Life Events

**Labels:** `phase-4b` `life-events` `perf`  
**Size:** 1.5 ngày  
**Depends on:** S6, S7; Phase 4A Monte Carlo engine ✅

**User Story:**  
Khi tôi thêm "Mua nhà năm 2028", tôi muốn cone chart của tôi phản ánh khoản chi đó.

**Implementation tasks:**
- [ ] `twin/engine/life_events.py`: `apply_life_events(paths, events, time_grid)`
- [ ] Handle one_time_cost: subtract from all paths at event month onwards
- [ ] Handle recurring_monthly_delta: apply cumulative from event month
- [ ] Handle `recurring_duration_months=None` → apply to end of horizon
- [ ] Floor paths at 0 (net worth không âm trong model)
- [ ] Skip events where `planned_date` > horizon end date
- [ ] Integrate vào `monte_carlo.py`: load user's active life events → call `apply_life_events()`
- [ ] Benchmark test

**Acceptance Criteria:**
- [ ] buy_house (3.5 tỷ, 2028): P50 tại Jan 2028 giảm 3.5 tỷ so với không có event
- [ ] first_child (−8tr/tháng, 216 tháng): cumulative effect tích lũy đúng
- [ ] 2 events không double-count nhau
- [ ] Event beyond horizon: silent skip (no error)
- [ ] Benchmark: 5 events × 1000 paths × 240 months < 500ms (NumPy vectorized)
- [ ] No NaN, no negative values in output

**Definition of Done:**
- [ ] `tests/twin/test_life_events_engine.py` với 5 test cases
- [ ] Benchmark result in `phase-4B-benchmark.md`

---

### P4B-S9: Telegram Interface — Life Events

**Labels:** `phase-4b` `life-events`  
**Size:** 1.5 ngày  
**Depends on:** S6, S7, S8

**User Story:**  
Tôi muốn thêm và quản lý life events của mình ngay trong Telegram mà không cần mở Mini App.

**Implementation tasks:**
- [ ] Register `/life_events` command trong bot
- [ ] Handler: entry menu [Xem danh sách | Thêm mới | Xóa]
- [ ] `ConversationHandler` cho add flow (states: SELECT_TYPE → REVIEW_PRESET → CUSTOM_DATE → CUSTOM_COST → CONFIRM)
- [ ] Inline keyboard buttons cho event types (với VN emoji)
- [ ] Confirm screen: summary trước khi save
- [ ] View list: paginated nếu > 5 events
- [ ] Delete flow: select event → confirm → soft delete
- [ ] After save: trigger S2 on-demand recompute + gửi S10 impact chart

**Acceptance Criteria:**
- [ ] Full add flow hoạt động end-to-end via Telegram buttons
- [ ] Xem danh sách: planned_year + cost summary + event type icon
- [ ] Xóa: confirm dialog trước khi soft delete
- [ ] `planned_date < today` → friendly error: "Ngày bạn nhập đã qua rồi, bạn muốn nhập lại không?"
- [ ] Sau save: "🔮 Bé Tiền đang tính lại tương lai của bạn..." → gửi impact chart khi xong

**Definition of Done:**
- [ ] Integration test: full add flow (mocked Telegram)
- [ ] Integration test: delete flow
- [ ] Manual test theo TC-LE-01 đến TC-LE-10 trong `phase-4B-test-cases.md`

---

### P4B-S10: Life Event Impact Visualization

**Labels:** `phase-4b` `life-events` `perf`  
**Size:** 1 ngày  
**Depends on:** S8, S9

**User Story:**  
Sau khi thêm "Mua nhà", tôi muốn thấy ngay chart so sánh tương lai với và không có khoản mua đó.

**Implementation tasks:**
- [ ] `twin/charts/impact_chart.py`: `render_life_event_impact_chart(before_cone, after_cone, event_name)`
- [ ] 2 cones: Before (xanh lam, rgba(66,133,244,0.3)) + After (cam, rgba(255,152,0,0.3))
- [ ] Solid P50 lines cho mỗi cone
- [ ] Impact labels tại milestone years: delta VND formatted as "X tỷ" hoặc "X triệu"
- [ ] Watermark: "dự phóng, không phải dự đoán"
- [ ] Gửi tự động sau khi user save life event (từ S9 handler)

**Acceptance Criteria:**
- [ ] 2 cones phân biệt màu sắc rõ ràng (test với color-blind users: use pattern fill nếu cần)
- [ ] Impact labels tại 2027, 2030, 2035
- [ ] Watermark hiển thị đúng vị trí (bottom-right)
- [ ] PNG render p95 < 500ms
- [ ] Mobile readable: 1000×600px

**Definition of Done:**
- [ ] Unit test: `test_impact_chart_renders_without_error`
- [ ] Visual review: chart saved as fixture trong `tests/fixtures/charts/`

---

### P4B-S11: Mini App Life Events Panel

**Labels:** `phase-4b` `life-events`  
**Size:** 1 ngày  
**Depends on:** S6, S8

**User Story:**  
Tôi muốn quản lý tất cả life events và thử toggle từng event để xem ảnh hưởng lên cone chart — từ Mini App.

**Implementation tasks:**
- [ ] Tab "Kế hoạch" thêm vào Mini App navigation (sau tab "Tài sản")
- [ ] API: `GET /api/life-events` → list user's active events
- [ ] API: `GET /api/twin/projection?exclude_event_ids=...` → projection without specific events
- [ ] Timeline component: events sorted by `planned_date`, grouped by year
- [ ] Toggle switch per event → API call → re-render cone chart
- [ ] "Thêm sự kiện" button → deep link to Telegram `/life_events`

**Acceptance Criteria:**
- [ ] Tab loads < 1s (data pre-fetched)
- [ ] Toggle → cone chart re-render < 500ms (uses cached base projection)
- [ ] Timeline shows: event icon + title + planned_year + estimated_total_cost
- [ ] Deep link hoạt động trên Telegram mobile
- [ ] Empty state: "Chưa có kế hoạch nào. Thêm sự kiện đầu tiên →"

**Definition of Done:**
- [ ] API endpoints implemented và tested
- [ ] Mini App component renders correctly với mock data
- [ ] Performance test: toggle → re-render < 500ms

---

### P4B-S12: LLM Narrative for Life Events

**Labels:** `phase-4b` `life-events` `llm`  
**Size:** 0.5 ngày  
**Depends on:** S8, S9

**User Story:**  
Khi Bé Tiền giải thích impact của "Mua nhà" lên tài chính của tôi, tôi muốn cảm thấy được hỗ trợ — không bị phán xét hoặc hù dọa.

**Implementation tasks:**
- [ ] Extend twin narrative prompt: section về life event impacts
- [ ] Tone guidelines per event_type trong prompt (xem phase-4B-detailed.md)
- [ ] Few-shot examples: buy_house (positive framing), first_child (supportive)
- [ ] Hard rule trong prompt: KHÔNG bao giờ suggest trì hoãn kết hôn/sinh con vì tiền
- [ ] Chạy `prompt-tester` agent

**Acceptance Criteria:**
- [ ] Narrative reference impact amount cụ thể (không vague)
- [ ] buy_house framing: "đầu tư, trade-off bình thường"
- [ ] Tone test: không có từ harsh (harsh word list trong prompt-tester)
- [ ] Gợi ý hành động cụ thể và tích cực

**Definition of Done:**
- [ ] Prompt updated
- [ ] Prompt test cases: 2 per event type (5 types × 2 = 10 cases)
- [ ] Prompt-tester run documented

---

### P4B-S13: Life Events Tests + Benchmarks

**Labels:** `phase-4b` `life-events` `perf`  
**Size:** 0.5 ngày  
**Depends on:** S6–S12 all done

**Implementation tasks:**
- [ ] `tests/twin/test_life_events_engine.py`: 5 unit tests (xem S8)
- [ ] `tests/life_events/test_service.py`: CRUD + soft delete
- [ ] `tests/life_events/test_presets.py`: preset values validation
- [ ] `tests/integration/test_life_events_flow.py`: add → save → recompute triggered
- [ ] `benchmarks/bench_life_events.py`: 5 events × 1000 paths × 240 months

**Acceptance Criteria:**
- [ ] Tất cả tests pass
- [ ] No regressions in existing twin tests
- [ ] Benchmark documented: actual p95 < 500ms

**Definition of Done:**
- [ ] `phase-4B-benchmark.md` updated với life events benchmark result
- [ ] CI passes

---

## Epic 3: Cashflow Forecasting v2 `[epic-cashflow-v2]`

**Goal:** Auto-detect thu chi định kỳ, dự báo 3 tháng, cảnh báo trước khi thiếu tiền.  
**Size:** 7 ngày  
**Dependencies:** Existing transaction history (Phase 3.x ✅)

---

### P4B-S14: Recurring Transaction Detector

**Labels:** `phase-4b` `cashflow-v2` `db-migration`  
**Size:** 1.5 ngày

**User Story:**  
Tôi muốn Bé Tiền tự nhận ra lương, tiền nhà, và các khoản cố định khác — không cần tôi nhập tay.

**Implementation tasks:**
- [ ] Alembic migration: tạo bảng `recurring_patterns` (schema trong phase-4B-detailed.md)
- [ ] `cashflow/detector.py`: rule-based detection algorithm
- [ ] `amount_band(amount)`: round to nearest 50,000 VND
- [ ] `day_band(day)`: bucket into 8 bands
- [ ] Group → count unique months → compute confidence
- [ ] Cron: Monday 06:00 AM weekly re-run detection
- [ ] Only process users with ≥ 3 months transaction history

**Acceptance Criteria:**
- [ ] Salary (ngày 1, ~20tr × 3 months) detected với confidence ≥ 0.9
- [ ] Fixed rent (ngày 5, exact amount × 3 months) detected ≥ 0.85
- [ ] 3 random transactions trong 3 months → NOT detected (confidence < 0.7)
- [ ] User với < 3 months history → no detection run
- [ ] Performance: < 2s for 500 transactions

**Definition of Done:**
- [ ] Unit tests: 3 positive cases + 2 negative cases
- [ ] Cron scheduled
- [ ] Migration committed

---

### P4B-S15: User Review Flow for Detected Patterns

**Labels:** `phase-4b` `cashflow-v2`  
**Size:** 1 ngày  
**Depends on:** S14

**User Story:**  
Trước khi Bé Tiền dùng recurring patterns vào dự báo, tôi muốn xem và xác nhận chúng — đề phòng nhận diện sai.

**Implementation tasks:**
- [ ] Sau detection cron: query unconfirmed patterns không bị dismiss
- [ ] Nếu có patterns mới: gửi Telegram review message
- [ ] Inline buttons per pattern: [✅ Đúng | ❌ Không phải | ✏️ Sửa]
- [ ] ✅ → `is_confirmed = true`
- [ ] ❌ → `dismissed_until = now() + 30 days`
- [ ] ✏️ → ask amount → update → confirm
- [ ] Max 5 patterns per message

**Acceptance Criteria:**
- [ ] Hiển thị max 5 patterns per message
- [ ] ✅ → confirmed, used in forecast immediately
- [ ] ❌ → dismissed 30 ngày, không hiện lại
- [ ] ✏️ Sửa → full edit flow hoạt động
- [ ] Duplicate prevention: cùng pattern không nhận 2 review messages

**Definition of Done:**
- [ ] Integration test: detect → review message sent → user confirms → forecast updated
- [ ] Manual test: TC-CF-04 đến TC-CF-08

---

### P4B-S16: 3-Month Cashflow Forecast Model

**Labels:** `phase-4b` `cashflow-v2` `db-migration`  
**Size:** 1 ngày  
**Depends on:** S14, S15

**User Story:**  
Tôi muốn biết tháng tới và 2 tháng nữa dự kiến tôi có bao nhiêu tiền — dựa trên thu chi định kỳ đã xác nhận.

**Implementation tasks:**
- [ ] Alembic migration: tạo bảng `cashflow_forecasts`
- [ ] `cashflow/forecast.py`: `compute_cashflow_forecast()` function
- [ ] Adjust for actuals in current month (avoid double-counting)
- [ ] Low-balance threshold: default = avg monthly expense (computed from patterns)
- [ ] Cron: daily 01:00 AM recompute
- [ ] `cashflow_service.get_current_forecast(user_id)`: return latest

**Acceptance Criteria:**
- [ ] Chỉ dùng `is_confirmed = true` patterns
- [ ] Current month actuals giảm projected amount đúng
- [ ] `balance_eom` tích lũy từ `current_balance` đúng
- [ ] p95 compute time < 200ms
- [ ] Engine version stored

**Definition of Done:**
- [ ] Unit tests: happy path + edge cases (no patterns, only income, only expense)
- [ ] Cron scheduled
- [ ] Migration committed

---

### P4B-S17: Low-Balance Alert Engine

**Labels:** `phase-4b` `cashflow-v2`  
**Size:** 1 ngày  
**Depends on:** S16

**User Story:**  
Tôi muốn Bé Tiền cảnh báo tôi trước ít nhất 1 tháng nếu tháng đó có thể thiếu tiền — để tôi có thời gian chuẩn bị.

**Implementation tasks:**
- [ ] `cashflow/alert.py`: `check_and_send_cashflow_alerts(user_id, forecast)`
- [ ] Redis dedup key: `cashflow_alert:{user_id}:{low_balance_month}` (TTL 7 ngày)
- [ ] Alert message template trong `content/vi.yaml` key `cashflow_alert`
- [ ] User setting: `/settings cashflow_threshold {amount}` (persist vào `users.cashflow_alert_threshold`)
- [ ] Default threshold: `avg(confirmed_expense_patterns.amount)`
- [ ] Use `get_notifiers()` → multi-channel (Telegram + Zalo nếu linked)

**Acceptance Criteria:**
- [ ] Alert trigger khi bất kỳ tháng nào trong horizon có `balance_eom < threshold`
- [ ] Không lặp alert cho cùng `low_balance_month` trong 7 ngày (Redis dedup)
- [ ] Alert gửi lại nếu balance worsens sau khi đã recover
- [ ] Tone: "có thể", "dự báo" — không alarming
- [ ] `/settings cashflow_threshold` hoạt động

**Definition of Done:**
- [ ] Unit tests: trigger, dedup, recovery re-trigger
- [ ] Content YAML entry
- [ ] `vi-localization-checker` passes

---

### P4B-S18: Cashflow Waterfall Chart

**Labels:** `phase-4b` `cashflow-v2` `perf`  
**Size:** 1 ngày  
**Depends on:** S16

**User Story:**  
Tôi muốn thấy 3 tháng tới dưới dạng chart trực quan — thu nhập, chi tiêu, và số dư mỗi tháng.

**Implementation tasks:**
- [ ] `cashflow/chart.py`: `render_cashflow_waterfall(forecast: CashflowForecast) -> bytes`
- [ ] Grouped bars: income (#4CAF50) + expense (#F44336)
- [ ] Balance EOM line (#7C4DFF)
- [ ] Net badges trên mỗi tháng
- [ ] Vietnamese axis labels ("Tháng 8/2026", "tr" abbreviation)
- [ ] Watermark: "dự báo dựa trên thu chi định kỳ"
- [ ] Output: PNG 1000×600px

**Acceptance Criteria:**
- [ ] Render p95 < 500ms
- [ ] Income/expense bars clearly distinguishable (different colors)
- [ ] Balance line visible kể cả khi bars cao
- [ ] Mobile readable
- [ ] Watermark present

**Definition of Done:**
- [ ] Unit test: renders without error
- [ ] Visual fixture saved trong `tests/fixtures/charts/cashflow_waterfall_sample.png`

---

### P4B-S19: Morning Briefing Cashflow Summary

**Labels:** `phase-4b` `cashflow-v2`  
**Size:** 0.5 ngày  
**Depends on:** S16, S17

**User Story:**  
Tôi muốn thấy một dòng tóm tắt cashflow tháng tới trong morning briefing hàng ngày.

**Implementation tasks:**
- [ ] Extend `morning_briefing_service.py`: call `cashflow_service.get_monthly_summary(user_id)`
- [ ] Condition: chỉ thêm vào briefing khi `len(confirmed_patterns) >= 2`
- [ ] Format: net cashflow next month + ⚠️ warning nếu `low_balance_risk`
- [ ] Không thêm nếu user chưa có forecast

**Acceptance Criteria:**
- [ ] Không hiển thị khi < 2 confirmed patterns
- [ ] Hiển thị net (+/-), không chỉ income/expense riêng
- [ ] ⚠️ prefix khi `low_balance_risk = True`
- [ ] No regression: existing morning briefing format không thay đổi

**Definition of Done:**
- [ ] Unit test: briefing với/không có cashflow section
- [ ] No regressions trong existing morning briefing tests

---

### P4B-S20: Cashflow Tab in Mini App

**Labels:** `phase-4b` `cashflow-v2`  
**Size:** 1 ngày  
**Depends on:** S16, S17, S18

**User Story:**  
Tôi muốn xem và chỉnh sửa recurring patterns của mình từ Mini App — không cần chat Telegram.

**Implementation tasks:**
- [ ] Tab "Dòng tiền" thêm vào Mini App navigation
- [ ] API: `GET /api/cashflow/forecast` → CashflowForecast
- [ ] API: `GET /api/cashflow/patterns` → List[RecurringPattern] (confirmed)
- [ ] API: `POST /api/cashflow/patterns` → add manual pattern
- [ ] API: `PATCH /api/cashflow/patterns/{id}` → update amount/day
- [ ] Waterfall chart component (pre-rendered PNG hoặc Chart.js)
- [ ] Lists: income patterns + expense patterns (editable inline)
- [ ] Alert banner nếu `low_balance_risk = True`
- [ ] "Thêm thủ công" FAB

**Acceptance Criteria:**
- [ ] Tab loads < 1s
- [ ] Patterns editable: tap → edit amount/day → save
- [ ] Alert banner có CTA link đến explanation
- [ ] "Thêm thủ công" hoạt động
- [ ] Responsive mobile (375px)

**Definition of Done:**
- [ ] API endpoints implemented và tested
- [ ] Mini App renders correctly
- [ ] Manual test: TC-CF-20 đến TC-CF-24

---

## Epic 4: Zalo Adapter Foundation `[epic-zalo]`

**Goal:** Prove Zalo channel với cashflow alert là feature đầu tiên.  
**Size:** 4 ngày  
**Dependencies:** Notifier port (Phase 4A ✅), S17 cashflow alert engine, Zalo OA account approved (operator task)

---

### P4B-S21: Zalo Official Account Setup + SDK

**Labels:** `phase-4b` `zalo` `infrastructure`  
**Size:** 1 ngày

**User Story:**  
Là developer, tôi cần một Zalo OA client async để gửi messages từ backend.

**Implementation tasks:**
- [ ] `adapters/zalo_oa.py`: `ZaloOAClient` class với aiohttp
- [ ] `send_message(recipient_id, text)` method
- [ ] `send_image_message(recipient_id, image_url, caption)` method
- [ ] Retry: 429 → exponential backoff 2s/4s/8s (max 3 retries)
- [ ] Other errors: log WARNING + return False (fail-open, không raise)
- [ ] Env vars: `ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_SECRET_KEY`, `ZALO_APP_ID`
- [ ] `.env.example` updated với placeholder values

**Acceptance Criteria:**
- [ ] Client gửi được test message tới Zalo OA follower (E2E test với real OA)
- [ ] All credentials từ env, KHÔNG hardcode
- [ ] 429 retry logic works (unit test với mock 429 response)
- [ ] Non-retry errors: return False, không raise exception
- [ ] `.env.example` có 3 new vars

**Definition of Done:**
- [ ] Unit tests với mocked aiohttp session
- [ ] E2E smoke test documented (manual)

---

### P4B-S22: ZaloNotifier implementing Notifier Port

**Labels:** `phase-4b` `zalo`  
**Size:** 1 ngày  
**Depends on:** S21; Phase 4A Notifier port ✅

**User Story:**  
Là developer, tôi muốn `ZaloNotifier` hoạt động đúng như `TelegramNotifier` — cùng interface, chỉ khác kênh.

**Implementation tasks:**
- [ ] `adapters/zalo_notifier.py`: `class ZaloNotifier(Notifier)`
- [ ] `strip_markdown(text)`: loại bỏ `*`, `_`, `` ` ``, `[...]()` formatting
- [ ] Truncate at 300 chars (Zalo display limit)
- [ ] `send(message: Message) -> bool`
- [ ] `send_image(image_bytes: bytes, caption: str) -> bool`: upload → send
- [ ] `channel` property returns `"zalo"`

**Acceptance Criteria:**
- [ ] Passes `ports/notifier_test_suite.py` (shared test suite)
- [ ] Markdown stripped: `**bold**` → `bold`
- [ ] Text truncated tại 300 chars
- [ ] Returns `False` (không raise) khi Zalo API fail
- [ ] `channel == "zalo"`

**Definition of Done:**
- [ ] All shared notifier test suite cases pass
- [ ] Additional ZaloNotifier-specific unit tests

---

### P4B-S23: User Zalo Linking Flow

**Labels:** `phase-4b` `zalo` `db-migration`  
**Size:** 1 ngày  
**Depends on:** S21, S22

**User Story:**  
Tôi muốn liên kết tài khoản Zalo của mình với Bé Tiền để nhận thông báo cashflow qua Zalo.

**Implementation tasks:**
- [ ] Alembic migration: `ALTER TABLE users ADD COLUMN zalo_user_id VARCHAR(50)` + `ADD COLUMN cashflow_alert_threshold NUMERIC(20,2)`
- [ ] Migration: tạo bảng `zalo_link_tokens`
- [ ] `/link_zalo` Telegram command handler
- [ ] Generate 6-char alphanumeric token (format `BT-XXXXXX`), expires 10 phút
- [ ] Zalo webhook endpoint: `POST /webhook/zalo` → receive token → match → link user
- [ ] Confirmation: gửi cả Telegram + Zalo
- [ ] `/unlink_zalo` command → clear `zalo_user_id`
- [ ] `/profile` hiển thị "Zalo: đã liên kết ✅" nếu linked

**Acceptance Criteria:**
- [ ] Token expires after 10 phút
- [ ] Token single-use: second attempt → "Mã đã được dùng rồi"
- [ ] Confirmation sent to both channels
- [ ] `/unlink_zalo`: clears `zalo_user_id`, confirms in Telegram
- [ ] `/profile` shows Zalo link status

**Definition of Done:**
- [ ] Migration committed
- [ ] Unit tests: token generation, expiry, single-use
- [ ] Integration test: link flow end-to-end

---

### P4B-S24: Cashflow Alert via Zalo

**Labels:** `phase-4b` `zalo` `cashflow-v2`  
**Size:** 1 ngày  
**Depends on:** S17, S22, S23

**User Story:**  
Khi tôi đã liên kết Zalo, tôi muốn nhận cashflow alert qua cả Zalo lẫn Telegram.

**Implementation tasks:**
- [ ] Extend `get_notifiers(user_id)`: nếu `user.zalo_user_id is not None` → append `ZaloNotifier`
- [ ] Zalo message format: plain text, ≤ 300 chars, 2 emojis max
- [ ] `format_cashflow_alert(forecast, channel="zalo")` → shorter format
- [ ] Fail-open: nếu `ZaloNotifier.send()` returns False → log + continue (Telegram vẫn gửi)
- [ ] Idempotency: không gửi duplicate trong cùng kênh

**Acceptance Criteria:**
- [ ] Linked user nhận alert cả Telegram + Zalo
- [ ] Unlinked user chỉ nhận Telegram
- [ ] Zalo fail → Telegram vẫn gửi (fail-open verified by test)
- [ ] Zalo message ≤ 300 chars
- [ ] No duplicate messages

**Definition of Done:**
- [ ] Unit test: `test_alert_sends_to_both_channels_when_linked`
- [ ] Unit test: `test_zalo_failure_does_not_block_telegram`
- [ ] Manual E2E test documented

---

## Story Summary

| Epic | Stories | Size |
|---|---|---|
| Epic 1: Twin Polish | S1–S5 | 4 ngày |
| Epic 2: Life Events | S6–S13 | 7 ngày |
| Epic 3: Cashflow v2 | S14–S20 | 7 ngày |
| Epic 4: Zalo | S21–S24 | 4 ngày |
| **Total** | **24 stories** | **~22 ngày** |
