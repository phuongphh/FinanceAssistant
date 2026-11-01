# Phase 4A — Manual Test Cases (Telegram Bot + Mini App)

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

> **Purpose:** Comprehensive manual test cases for Phase 4A (Financial Twin Conservative MVP).
> **Tester Profile:** No source code access. Tests via Telegram chat (premium + non-premium) và Mini App webview.
> **Reference:** [phase-4A-detailed.md](./phase-4A-detailed.md), [phase-4A-issues.md](./phase-4A-issues.md)

---

## 📋 How to Use This Document

### Test Case Structure

```
TC-XXX: [Title]
Type: Happy | Corner | Regression | Integration | Performance | Critical | Trust
Story: P4A-Sn
Persona: Test user
Preconditions: State required
Steps: Numbered actions
Expected Results: Observable outcomes
Pass Criteria: All expected met
```

### Pass / Fail

- ✅ **PASS:** All Expected Results observed
- ⚠️ **PASS WITH NOTES:** Main behavior correct, minor issues
- ❌ **FAIL:** Any Expected Result not observed
- 🚫 **BLOCKED:** Cannot execute due to dependency

---

## 🧑‍💼 Test Data Setup

Reuse 4 personas from earlier phases. Each must have ≥ 30 days of asset history for engine to produce meaningful cones.

### Persona 1: Hà (Trẻ Năng Động, ~140tr)
- Age 28, single, FPT employee
- Assets: 60tr stocks (5 mã VN), 15tr crypto (BTC, ETH), 50tr cash savings, 15tr gold (1 chỉ SJC)
- Monthly savings: ~10tr
- Telegram: **non-premium**

### Persona 2: Anh Phương (Trung Lưu Vững, ~480tr)
- Age 36, married, mid-level manager
- Assets: 250tr stocks, 80tr crypto, 100tr cash, 50tr gold
- Monthly savings: ~25tr
- Telegram: **premium**

### Persona 3: Chị Hằng (Tinh Hoa, ~2.4 tỷ)
- Age 45, business owner
- Assets: 1.2 tỷ real estate (rental), 600tr stocks, 200tr gold, 400tr cash
- Monthly savings: ~50tr
- Telegram: **premium**

### Persona 4: Em Khôi (Khởi Đầu, ~12tr)
- Age 23, fresh grad
- Assets: 8tr cash, 4tr stocks (1 mã)
- Monthly savings: ~3tr
- Telegram: **non-premium**

### Persona 5: Mới (zero portfolio)
- New user, < 5tr net worth
- For empty state testing

---

## Section 1 — Engine Correctness (TC-001 to TC-008)

### TC-001: Single-user Monte Carlo runs in time budget
**Type:** Performance
**Story:** P4A-S2, S3, S26
**Persona:** Anh Phương
**Preconditions:** Backend running, user logged in
**Steps:**
1. Trigger projection via "🔮 Bé Tiền tương lai" → "📈 Xem trajectory"
2. Measure time from button click → image render
**Expected:**
- p95 < 4s end-to-end (engine + chart)
- Engine alone < 2s server-side (check logs)
**Pass:** Both met for 5 consecutive runs

### TC-002: Deterministic with same seed
**Type:** Critical
**Story:** P4A-S5
**Persona:** Internal dev (backend access)
**Steps:** Run engine twice with seed=42, same portfolio
**Expected:** Identical cone values to last VND

### TC-003: Cone monotonicity
**Type:** Critical
**Story:** P4A-S4
**Persona:** Any
**Steps:** View cone for any user with >10tr NW
**Expected:** For every year displayed, P10 ≤ P50 ≤ P90

### TC-004: Year 0 = current net worth
**Type:** Happy
**Story:** P4A-S4
**Persona:** Hà
**Steps:** View Twin trajectory, hover year 0 (or check caption)
**Expected:** P10 = P50 = P90 = current NW (140tr ± rounding)

### TC-005: Mass Affluent baseline sanity
**Type:** Critical
**Story:** P4A-S5
**Persona:** Anh Phương
**Steps:** View 10-year current trajectory
**Expected:** P50 at year 10 ∈ [1.2 tỷ, 2.5 tỷ]; cone width reasonable (P90/P10 ratio < 5)

### TC-006: Empty state (NW < 10tr)
**Type:** Corner
**Story:** P4A-S14
**Persona:** Persona 5 (Mới)
**Steps:** Click "🔮 Bé Tiền tương lai" → "Xem trajectory"
**Expected:** Friendly message "Bé Tiền chưa đủ data, thêm tài sản trước nhé" + CTA to add asset, NO chart

### TC-007: All 7 asset classes computed
**Type:** Integration
**Story:** P4A-S1, S3
**Persona:** Internal dev
**Steps:** Inspect log of projection compute for diverse-portfolio user
**Expected:** All asset classes user holds get a μ/σ lookup, none default to zero

### TC-008: Engine version stamped
**Type:** Integration
**Story:** P4A-S6, S8
**Persona:** Internal dev (DB access)
**Steps:** Query `SELECT engine_version FROM twin_projections ORDER BY created_at DESC LIMIT 1`
**Expected:** Returns "4a.1.0"

---

## Section 2 — Persistence & Cron (TC-009 to TC-015)

### TC-009: Migration applies clean
**Type:** Critical
**Story:** P4A-S7
**Steps:** `alembic upgrade head` on fresh DB
**Expected:** Exit 0, table `twin_projections` exists with 2 indexes

### TC-010: Migration reversible
**Type:** Corner
**Story:** P4A-S7
**Steps:** `alembic upgrade head` then `alembic downgrade -1`
**Expected:** Table dropped, no data loss on other tables

### TC-011: Weekly cron compute for all active users
**Type:** Integration
**Story:** P4A-S9
**Persona:** Internal (5 test users active in last 30d)
**Steps:** Trigger weekly cron manually (or wait Sunday 23:00)
**Expected:**
- 5 users each get 2 rows (current + optimal) inserted
- Total time < 30s (well under 5min budget)
- Metrics logged

### TC-012: Cron isolates per-user failure
**Type:** Critical
**Story:** P4A-S9
**Persona:** Internal — inject 1 user with corrupt portfolio
**Steps:** Run cron with 5 users, 1 corrupted
**Expected:** 4 succeeded, 1 failed, batch completes, error logged with user_id

### TC-013: On-demand recompute on asset change >5%
**Type:** Integration
**Story:** P4A-S10
**Persona:** Hà
**Preconditions:** Existing projection
**Steps:** Add new asset worth > 5% of current NW (e.g. 10tr)
**Expected:** New projection row appears in DB within 1-2 min, debounce respected

### TC-014: Debounce works (no recompute spam)
**Type:** Corner
**Story:** P4A-S10
**Persona:** Hà
**Steps:** Make 3 asset edits in 5 minutes, each >5% delta
**Expected:** Only 1 recompute (last computed_at < 1h triggers skip)

### TC-015: Stale cone flagged
**Type:** Corner
**Story:** P4A-S11
**Persona:** Internal
**Preconditions:** Manually update `computed_at` to 15 days ago
**Steps:** Open Twin view
**Expected:** UI shows "Cone updated 15 days ago" + soft warning

---

## Section 3 — Telegram Surface (TC-016 to TC-024)

### TC-016: Menu entry "🔮 Bé Tiền tương lai" visible
**Type:** Happy
**Story:** P4A-S12
**Persona:** Any
**Steps:** Open main menu
**Expected:** Button visible, clickable, opens submenu with 4 actions

### TC-017: Adaptive intro per wealth level
**Type:** Integration
**Story:** P4A-S12
**Persona:** Test all 4 (Hà, Phương, Hằng, Khôi)
**Steps:** Each opens Twin submenu
**Expected:** Intro copy adapts to wealth level (different wording for Khởi Đầu vs Tinh Hoa)

### TC-018: View trajectory renders PNG chart
**Type:** Happy
**Story:** P4A-S14
**Persona:** Anh Phương
**Steps:** Twin submenu → "Xem trajectory"
**Expected:**
- Photo arrives with cone chart
- Caption Vietnamese, includes cone range "X — Y tỷ năm 2036"
- Caption notes "Cập nhật N ngày trước"
- Watermark visible

### TC-019: Chart Vietnamese formatting
**Type:** Trust
**Story:** P4A-S13
**Persona:** Chị Hằng
**Steps:** View cone chart
**Expected:** Y-axis VND formatted "1 tỷ", "500tr" — NOT "1,000,000,000"

### TC-020: Watermark "dự phóng, không phải dự đoán"
**Type:** Trust
**Story:** P4A-S13, S25
**Persona:** Any
**Steps:** View any cone chart
**Expected:** Watermark visible in corner, text "Bé Tiền — dự phóng, không phải dự đoán"

### TC-021: Morning briefing Twin line — on-track
**Type:** Integration
**Story:** P4A-S15
**Persona:** Anh Phương (actual NW within ±5% of P50)
**Steps:** Trigger morning briefing
**Expected:** 1-2 lines about Twin, emoji 🎯, encouraging tone

### TC-022: Morning briefing Twin line — behind (gentle)
**Type:** Trust
**Story:** P4A-S15
**Persona:** Inject test user where actual < P50 - 5%
**Steps:** Trigger morning briefing
**Expected:** Emoji 🌱, copy encouraging — NEVER harsh ("bạn đang chậm", "fail")

### TC-023: LLM narrative generated
**Type:** Happy
**Story:** P4A-S16
**Persona:** Hà
**Steps:** First Twin view of the week
**Expected:** Caption includes 2-3 sentence narrative, 50-200 chars, Bé Tiền persona, no markdown

### TC-024: LLM fallback if API fails
**Type:** Corner
**Story:** P4A-S16
**Persona:** Internal (mock LLM failure)
**Steps:** View Twin with LLM offline
**Expected:** Template-based narrative shown, no error to user, log records fallback

---

## Section 4 — Mini App (TC-025 to TC-032)

### TC-025: Mini App opens from Telegram
**Type:** Happy
**Story:** P4A-S17, S20
**Persona:** Anh Phương (premium)
**Steps:** Twin submenu → "📊 Mở Twin Dashboard"
**Expected:** Webview opens, theme matches Telegram

### TC-026: Mini App auth via initData
**Type:** Critical
**Story:** P4A-S19
**Persona:** Anh Phương
**Steps:** Open Mini App normally
**Expected:** Data loads (HMAC valid). Inspect network: no 401

### TC-027: Mini App auth rejects forged initData
**Type:** Critical
**Story:** P4A-S19
**Persona:** Internal — modify initData manually
**Steps:** Call API with bad initData
**Expected:** 401 Unauthorized, no data leaked

### TC-028: Cone chart interactive
**Type:** Happy
**Story:** P4A-S18
**Persona:** Anh Phương
**Steps:** Hover/tap chart years
**Expected:** Tooltip shows year + P10/P50/P90 range in VND

### TC-029: Scenario toggle Current ↔ Optimal
**Type:** Happy
**Story:** P4A-S18
**Persona:** Anh Phương
**Steps:** Tap toggle
**Expected:** Chart smoothly updates to Optimal (different cone), no full reload, KPI cards update

### TC-030: Responsive on small phone
**Type:** Corner
**Story:** P4A-S18
**Persona:** Hà
**Steps:** Open Mini App on iPhone SE (320px)
**Expected:** Layout intact, chart fits, no horizontal scroll

### TC-031: Loading skeleton
**Type:** Happy
**Story:** P4A-S18
**Persona:** Any with slow network
**Steps:** Throttle network to 3G, open Mini App
**Expected:** Skeleton shown before data, no blank screen

### TC-032: ETag 304 caching
**Type:** Performance
**Story:** P4A-S19
**Persona:** Internal
**Steps:** Call `GET /api/twin` twice in 5 min
**Expected:** 2nd returns 304 Not Modified

---

## Section 5 — Optimal Trajectory (TC-033 to TC-038)

### TC-033: Target allocation per wealth level correct
**Type:** Integration
**Story:** P4A-S21
**Persona:** All 4 wealth levels
**Steps:** For each, view Optimal trajectory → check allocation displayed
**Expected:** Matches table in detailed.md (Khởi Đầu 20/0/5/10/65/0, etc.)

### TC-034: Allocation sums to 100%
**Type:** Critical
**Story:** P4A-S21
**Persona:** Any
**Steps:** View Optimal allocation
**Expected:** Sum = 100% (or 1.0 ± 0.001)

### TC-035: Optimal cone > Current cone (P50)
**Type:** Happy
**Story:** P4A-S22
**Persona:** Hà (suboptimal allocation)
**Steps:** Compare current vs optimal at year 10
**Expected:** Optimal P50 > Current P50 by meaningful margin (>10%)

### TC-036: Comparison handler dual-cone chart
**Type:** Happy
**Story:** P4A-S23
**Persona:** Anh Phương
**Steps:** Twin submenu → "So sánh Optimal"
**Expected:** Chart with 2 cones overlaid, distinct colors, legend, caption with concrete delta numbers

### TC-037: Actionable steps in comparison caption
**Type:** Happy
**Story:** P4A-S23
**Persona:** Hà
**Steps:** View comparison
**Expected:** Caption lists 2-3 concrete actions ("Tăng tiết kiệm 10%", "Rebalance crypto 20% → 10%")

### TC-038: Investment-advice disclaimer present
**Type:** Trust / Compliance
**Story:** P4A-S21, S25
**Persona:** Any
**Steps:** View Optimal trajectory
**Expected:** Disclaimer "Đây là gợi ý chung, không phải lời khuyên đầu tư" visible

---

## Section 6 — Trust & Persona (TC-039 to TC-044)

### TC-039: No banned forecasting words
**Type:** Trust
**Story:** P4A-S25
**Persona:** Any
**Steps:** Review all Twin copy (menu, caption, narrative, briefing line)
**Expected:** 0 instances of "sẽ là", "chắc chắn", "đảm bảo", "dự đoán chính xác" — only "có thể", "dự phóng", "khả năng"

### TC-040: FAQ entry "Tại sao Bé Tiền không cho con số chính xác?"
**Type:** Trust
**Story:** P4A-S25
**Persona:** Any
**Steps:** Twin submenu → "ℹ️ Twin hoạt động ra sao"
**Expected:** Educational FAQ explains probability framework, uncertainty, why cones

### TC-041: Bé Tiền persona consistency
**Type:** Trust
**Story:** P4A-S15, S16
**Persona:** Test user behind P50 by 20%
**Steps:** Read morning briefing + narrative
**Expected:** Tone encouraging, supportive — never blame/harsh. Read aloud test passes

### TC-042: Vietnamese fluency
**Type:** Trust
**Story:** P4A-S25
**Persona:** Native VN reader
**Steps:** Read all Twin copy aloud
**Expected:** Natural Vietnamese, no robotic phrasing, no anglicism

### TC-043: Probability cones not single numbers
**Type:** Trust
**Story:** P4A-S25
**Persona:** Any
**Steps:** Review every Twin user-facing number
**Expected:** Always presented as range (X — Y) or with percentile context, NEVER single number presented as "the prediction"

### TC-044: Watermark on all chart images
**Type:** Trust
**Story:** P4A-S13, S25
**Persona:** Any
**Steps:** Generate Current + Optimal + Comparison charts
**Expected:** All 3 chart types have watermark visible

---

## Section 7 — Regression (TC-045 to TC-050)

### TC-045: Phase 3.9.5 menu intact
**Type:** Regression
**Story:** —
**Persona:** Any
**Steps:** Navigate Tài sản / Dòng tiền / Thị trường / Mục tiêu
**Expected:** All Phase 3.9.5 fixes still working (no regression from Twin add)

### TC-046: Morning briefing without Twin (new user)
**Type:** Regression
**Story:** P4A-S15
**Persona:** Persona 5
**Steps:** Trigger morning briefing
**Expected:** Briefing renders normally, Twin section absent (no error)

### TC-047: Asset CRUD still works
**Type:** Regression
**Story:** P4A-S10 (hooks)
**Persona:** Hà
**Steps:** Add / edit / delete asset
**Expected:** CRUD succeeds, projection trigger fires async (background, not blocking)

### TC-048: Existing intents not broken
**Type:** Regression
**Story:** —
**Persona:** Anh Phương
**Steps:** Send free-text queries: "tài sản của tôi", "chi tiêu tháng này", "VNM giá bao nhiêu"
**Expected:** All respond correctly, no Twin intrusion

### TC-049: Goals system intact
**Type:** Regression
**Story:** —
**Persona:** Hà
**Steps:** View / create goal
**Expected:** Phase 3.8 goals system unaffected

### TC-050: Full pytest suite green
**Type:** Regression
**Story:** P4A-S27
**Persona:** Internal CI
**Steps:** `uv run pytest tests/`
**Expected:** All tests pass, no new flakes

---

## Section 8 — Performance (TC-051 to TC-055)

### TC-051: Engine perf single user
**Type:** Performance
**Story:** P4A-S26
**Steps:** Benchmark MC: 5 assets, 1000 paths, 10y, 20 iterations
**Expected:** p95 < 2s

### TC-052: Chart render perf
**Type:** Performance
**Story:** P4A-S26
**Steps:** Benchmark cone PNG render 20x
**Expected:** p95 < 500ms

### TC-053: API endpoint perf (cached)
**Type:** Performance
**Story:** P4A-S26
**Steps:** Hit `/api/twin` 20x same user
**Expected:** p95 < 200ms (DB hit only, no recompute)

### TC-054: Weekly cron full batch
**Type:** Performance
**Story:** P4A-S26
**Steps:** Run cron with 100 fake active users
**Expected:** Complete < 5 min

### TC-055: Mini App bundle size
**Type:** Performance
**Story:** P4A-S17, S26
**Steps:** Build production, check gzipped output
**Expected:** Bundle < 200KB gzipped

---

## Section 9 — Channel Abstraction (TC-056 to TC-058)

### TC-056: Twin handler uses Notifier port
**Type:** Critical / Layer Contract
**Story:** P4A-S24
**Steps:** Code review: grep `telegram_service` in `twin_handler.py`
**Expected:** 0 hits. Only Notifier port used

### TC-057: ContentRenderer port exists
**Type:** Critical
**Story:** P4A-S24
**Steps:** Verify `backend/ports/content_renderer.py` exists, Protocol defined
**Expected:** Protocol with `render_twin_view`, Telegram impl present, Zalo stub raises NotImplementedError

### TC-058: Architecture doc committed
**Type:** Critical
**Story:** P4A-S24
**Steps:** `docs/architecture/twin-channel-abstraction.md` exists
**Expected:** Doc explains port pattern + Zalo expansion path

---

## ✅ Sign-Off

| Tester | Date | Total TCs | Passed | Failed | Notes |
|--------|------|-----------|--------|--------|-------|
| | | 58 | | | |

**Phase 4A is signed off when:**
- [ ] ≥ 95% TCs PASS
- [ ] 0 FAIL on Critical or Trust TCs
- [ ] All 6 Epic Issues closed
- [ ] Performance benchmarks documented
- [ ] Weekly cron observed 2 Sundays successfully
- [ ] Sign-off marker switched to `signed`
