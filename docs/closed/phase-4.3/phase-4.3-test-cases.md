# Phase 4.3 — Manual Test Cases (Telegram)

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

> **Scope:** Manual test cases for Phase 4.3 features, executed **on Telegram bot only**.
> **Out of scope của file này:** Admin dashboard (Epic 4) testing — handled in separate admin test approach (operator manual smoke test on web UI).
> **Coverage:** Epic 1 (Comprehension Foundation) + Epic 2 (Storytelling) + Epic 3 (Habit Loop).
> **Total TCs:** ~55-60, organized in 3 batches.

---

## 🧪 Test Setup

**Environment:** Bé Tiền staging Telegram bot (`@betien_staging_bot` or production-mirror staging instance).

**Test personas required:**

| Persona ID | Segment | Pre-existing state | Used in TCs |
|---|---|---|---|
| P-Starter | Starter (net worth < 200tr) | Has 30 days history, 2-3 assets | 1.1.x, 1.3.x |
| P-YoungPro | Young Pro (200tr - 1tỷ) | Has 60 days history, 5 assets, 1 goal | 1.2.x, 3.x.x |
| P-MassAffluent | Mass Affluent (1tỷ - 10tỷ) | Has 90+ days history, 8 assets, 2 goals | Most TCs |
| P-HNW | High Net Worth (> 10tỷ) | Has 90+ days, 12 assets, complex portfolio | 3.4.x, 3.5.x |
| P-New | Just signed up | < 7 days history, 1 asset | 1.3.x edge cases |
| P-NegativeJourney | MassAffluent who lost income recently | 30+ days no income, delta negative | 3.4.x |

**Test data fixtures:** Available in `staging-fixtures/phase-4.3-personas.json`. Apply before test run via operator command `/load_fixture phase-4.3`.

**Tester profile:** 1 senior dev + 1 Vietnamese-native content reviewer pair-test each TC. Content reviewer responsible for tone/copy verification.

**Test execution time estimate:** ~6-8 hours for full Batch 1 (Epic 1 + 2). ~8-10 hours for Batch 2 (Epic 3 core). ~6-8 hours for Batch 3 (Epic 3 edge + integration). Total ~3-4 days of manual testing.

---

## 📊 Test Case Numbering Convention

`TC-X.Y.Z` where:
- `X.Y` = Story ID (e.g., 1.1 for Story 1.1 weather rename)
- `Z` = TC number within story (1, 2, 3...)

Cross-story integration TCs use prefix `TC-INT-X` (Batch 3).

**Priority:**
- **P0** = blocker, must pass before Phase 4.3 ship
- **P1** = should pass, can ship if known limitation documented

---

# 🧪 BATCH 1 — Epic 1 + Epic 2 (TCs 1-20)

## Epic 1 — Twin Comprehension Foundation

### TC-1.1.1 — First-time user sees weather labels (not P-code)

**Story:** #1.1 (Weather vocab rename)
**Persona:** P-MassAffluent (clean account, never opened Twin before)
**Priority:** P0

**Pre-conditions:**
- Persona has not opened Twin viewer in past 30 days
- Settings "Hiển thị thuật ngữ kỹ thuật" = OFF (default)

**Steps (Telegram):**
1. Open Bé Tiền bot, send `/twin` command (or tap "Xem Twin" in main menu)
2. Wait for Twin viewer to render
3. Observe the 3 scenario cards

**Expected:**
- 3 cards display: **🌧️ Khiêm tốn**, **⛅ Bình thường**, **☀️ Lạc quan**
- NO appearance of "P10", "P50", "P90", "percentile", "phân vị" anywhere on visible screen
- Emoji renders correctly (not as boxes/question marks)

**Pass criteria:**
- ✅ 3 weather labels visible exactly as specified
- ✅ Zero technical jargon visible
- ✅ Cards distinguishable visually

**Notes:**
- Test on Telegram iOS, Android, Web — emoji rendering varies

---

### TC-1.1.2 — Power user toggle reveals P-code tooltip

**Story:** #1.1
**Persona:** P-MassAffluent (power user)
**Priority:** P1

**Pre-conditions:**
- TC-1.1.1 passed (Twin labels weather format by default)

**Steps (Telegram):**
1. Open Bé Tiền bot, send `/settings`
2. Navigate to "Hiển thị thuật ngữ kỹ thuật"
3. Toggle ON
4. Return to Twin viewer (`/twin`)
5. Long-press or tap info icon next to weather label

**Expected:**
- Toggle exists and is OFF by default
- After toggling ON, Twin labels show small subscript or tooltip: "Bình thường = P50"
- Toggle preference persists across sessions (logout/login test)

**Pass criteria:**
- ✅ Toggle reachable in 2 taps from main menu
- ✅ Tooltip shows correct P-code mapping
- ✅ Setting persists

---

### TC-1.1.3 — Telegram cross-platform emoji rendering

**Story:** #1.1
**Persona:** Any (use P-MassAffluent for convenience)
**Priority:** P0

**Pre-conditions:** None

**Steps (Telegram):**
1. Open Twin viewer on **Telegram iOS** — screenshot 3 cards
2. Open same account on **Telegram Android** — screenshot 3 cards
3. Open same account on **Telegram Web (Chrome)** — screenshot
4. Open same account on **Telegram Desktop (Win/Mac)** — screenshot
5. Compare 4 screenshots

**Expected:**
- 🌧️ U+1F327 renders as cloud-with-rain on all 4 platforms (NOT as boxes)
- ⛅ U+26C5 renders as sun-behind-cloud on all 4 (NOT plain ☁️)
- ☀️ U+2600 renders consistently
- Variation selector FE0F may differ visually on desktop — acceptable as long as recognizable

**Pass criteria:**
- ✅ All 3 emojis visible on iOS + Android
- ✅ At minimum recognizable on Web + Desktop (color variation OK)
- ✅ No "tofu boxes" (□) anywhere

**Notes:**
- If desktop fails: file P1 bug, ship with note "Desktop users may see monochrome emoji"

---

### TC-1.1.4 — Backend data layer unchanged (regression check)

**Story:** #1.1
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:** Tester has access to backend log via operator command

**Steps (Telegram):**
1. Open Twin viewer (`/twin`)
2. Operator: run `/show_recent_twin_compute <user_id>` (admin command)
3. Observe log output

**Expected:**
- Backend log contains `p10`, `p50`, `p90` field names (unchanged)
- API response in raw form contains P-code fields
- Frontend transformation layer maps P-code → weather label correctly

**Pass criteria:**
- ✅ Backend never logs Vietnamese label as primary key
- ✅ Data layer schema unchanged
- ✅ Math output identical to pre-Phase-4.3 (numerical regression < 0.5%)

---

### TC-1.2.1 — Life outcome phrase appears for focused card

**Story:** #1.2 (Life outcome translation)
**Persona:** P-MassAffluent (location: HCMC)
**Priority:** P0

**Pre-conditions:**
- Persona's Twin P50 around 5.0-5.5 tỷ for year 2030
- LLM service operational on staging

**Steps (Telegram):**
1. Open Twin viewer (`/twin`)
2. Observe the ⛅ Bình thường card (default focused)
3. Read life outcome phrase below the amount

**Expected:**
- Phrase appears below "5.2 tỷ" (or actual amount), format: "[amount] = [tangible asset example] + [buffer description]"
- Example acceptable output: "5.2 tỷ = đủ căn hộ 2PN tại Q.7 + 1 tỷ tiết kiệm dự phòng"
- Phrase ≤ 30 từ
- Vietnamese natural-sounding (not LLM translationese)
- 🌧️ and ☀️ cards do NOT show life outcome (only focused card)

**Pass criteria:**
- ✅ Phrase visible on focused card only
- ✅ Phrase relevant to amount + user location (HCMC mentioned)
- ✅ No "chắc chắn", "đảm bảo", brand names ("Vinhomes", "MBBank")
- ✅ Vietnamese reviewer rates naturalness ≥ 4/5

---

### TC-1.2.2 — User regenerates life outcome with "Đổi ví dụ khác"

**Story:** #1.2
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:**
- TC-1.2.1 passed (phrase visible)

**Steps (Telegram):**
1. From Twin viewer with life outcome visible
2. Tap "Đổi ví dụ khác →" button
3. Observe new phrase
4. Repeat tap up to 3 more times
5. Try 4th tap (should hit daily limit)

**Expected:**
- 1st tap: new phrase, semantically similar (same amount range) but different example
- 2nd, 3rd tap: more variants
- 4th tap (5th total today): button disabled or message "Anh đã thử 3 ví dụ hôm nay. Mai thử lại nhé 💚"
- Each variation logged for analytics

**Pass criteria:**
- ✅ At least 3 distinct phrases available
- ✅ Daily limit enforced (3 regenerations/day)
- ✅ Polite limit message

---

### TC-1.2.3 — Cache hit on repeat view

**Story:** #1.2
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- User has viewed Twin in past 7 days

**Steps (Telegram):**
1. Open Twin viewer (`/twin`) — note life outcome phrase A
2. Close Telegram session
3. Reopen Bé Tiền after 5 minutes
4. Open Twin viewer again
5. Observe life outcome phrase

**Expected:**
- Phrase B = Phrase A (cache hit, identical output)
- Latency < 500ms for cached render (vs ~2-3s for fresh LLM call)
- No new LLM call logged in backend during step 4

**Pass criteria:**
- ✅ Phrase consistency on repeat view within 7 days
- ✅ Backend confirms cache hit
- ✅ User experience smooth (no perceptible delay)

---

### TC-1.2.4 — LLM unavailable fallback to static phrase

**Story:** #1.2
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Operator simulates LLM outage via `/llm_circuit_break twin_outcome` command

**Steps (Telegram):**
1. Operator triggers LLM circuit break
2. Tester opens Twin viewer for new persona (no cache)
3. Observe life outcome phrase
4. Operator: `/llm_circuit_restore twin_outcome`
5. Tester re-opens Twin (after cache TTL)

**Expected:**
- Step 3: Twin viewer still renders successfully (NOT error or empty)
- Phrase shown is from static fallback YAML (less personalized but acceptable)
- Phrase still relevant to amount bucket
- Step 5 (post-restore): subsequent views use LLM again, normal phrases

**Pass criteria:**
- ✅ Twin viewer never errors out
- ✅ Fallback phrase appears within 1 second
- ✅ User cannot tell major degradation (acceptable lesser personalization)

---

### TC-1.2.5 — Edge case: very small amount (< 100tr)

**Story:** #1.2
**Persona:** P-Starter (Twin P50 ~ 50-80tr for short horizon)
**Priority:** P1

**Pre-conditions:**
- Persona's Twin P50 < 100tr

**Steps (Telegram):**
1. Open Twin viewer

**Expected:**
- Life outcome uses different framing: "đủ chi phí sinh hoạt ~ X tháng" instead of asset comparison
- Tone remains encouraging, not patronizing
- No suggestion that small amount is "không đủ" or negative framing

**Pass criteria:**
- ✅ Phrase appropriate for amount scale
- ✅ Tone respectful, motivational
- ✅ Vietnamese reviewer approves tone

---

### TC-1.3.1 — Established user sees present + delta + growth rate

**Story:** #1.3 (Present anchor)
**Persona:** P-MassAffluent (established, 90+ days history)
**Priority:** P0

**Pre-conditions:**
- Persona has full 90 days of data
- Recent positive delta in past week (+10-15tr)

**Steps (Telegram):**
1. Open Twin viewer

**Expected:** Top of viewer shows in this order:
- **Present anchor:** "Hiện tại: [actual current net worth]" (e.g., "850tr (tài sản ròng)")
- **Weekly delta:** "↑ Tăng [X] tr so với tuần trước" — green arrow visible
- **Growth rate:** "Tốc độ ~ [Y] tr/tháng"

Visual hierarchy: present anchor styled larger/bolder than 3 weather cards below.

**Pass criteria:**
- ✅ All 3 elements visible above weather cards
- ✅ Delta with correct direction arrow
- ✅ Growth rate matches 90-day rolling average
- ✅ Present anchor visually emphasized

---

### TC-1.3.2 — New user (< 7 days) sees present only, no delta/growth

**Story:** #1.3
**Persona:** P-New (signed up 3 days ago)
**Priority:** P0

**Pre-conditions:**
- Persona < 7 days since signup

**Steps (Telegram):**
1. Open Twin viewer

**Expected:**
- Present anchor visible: "Hiện tại: [amount]"
- Delta and growth rate replaced by single message: "Bé Tiền cần thêm vài ngày để hiểu nhịp tài chính của anh 💚"
- 3 weather cards still visible (Twin renders with available data)

**Pass criteria:**
- ✅ No misleading delta shown
- ✅ Friendly message about data gathering
- ✅ Twin still partially usable

---

### TC-1.3.3 — Negative net worth user (debt > assets)

**Story:** #1.3
**Persona:** Custom — debt-heavy user, NW = -50tr
**Priority:** P0

**Pre-conditions:**
- Persona has total debt > total assets

**Steps (Telegram):**
1. Open Twin viewer

**Expected:**
- Present anchor shows: "Hiện tại: -50tr" with **amber color** (NOT red — avoid alarming)
- Special copy below: "Đây là điểm xuất phát — Bé Tiền sẽ cùng anh đi lên"
- 3 weather cards still computed and shown (forward projection valid)

**Pass criteria:**
- ✅ Amber color used, not red
- ✅ Encouraging copy present
- ✅ No language inducing shame ("nợ nần", "thiếu hụt", etc.)

**Notes:**
- Edge case — tester should verify special copy with Vietnamese content reviewer

---

### TC-1.3.4 — Tap present anchor expands net worth breakdown

**Story:** #1.3
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:**
- Persona has multiple asset types (tiết kiệm + cổ phiếu + BĐS)

**Steps (Telegram):**
1. Open Twin viewer
2. Tap on present anchor "Hiện tại: 850tr"

**Expected:**
- Expands to show net worth breakdown by asset type
- Format: "Tiết kiệm: 200tr / Cổ phiếu: 350tr / BĐS: 300tr"
- Re-uses Phase 4.2 net worth view component (consistency)
- Back navigation returns to Twin viewer with state preserved

**Pass criteria:**
- ✅ Breakdown displays correctly
- ✅ Numbers sum to present anchor amount
- ✅ Back nav works smoothly

---

## Epic 2 — Twin Storytelling

### TC-2.1.1 — 3 mascot versions render in respective cards

**Story:** #2.1 (Mascot personification)
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Mascot assets deployed to CDN
- Twin viewer renders 3 weather cards

**Steps (Telegram):**
1. Open Twin viewer
2. Observe each of 3 weather cards

**Expected:**
- 🌧️ Khiêm tốn card shows Bé Tiền in raincoat (calm expression)
- ⛅ Bình thường card shows Bé Tiền with umbrella (confident-neutral expression)
- ☀️ Lạc quan card shows Bé Tiền with sunglasses (happy expression — not over-the-top)
- All 3 mascot images visible at top-right of respective cards
- Image quality crisp, no pixelation

**Pass criteria:**
- ✅ Distinct mascot per card
- ✅ Matches weather context
- ✅ Vietnamese cultural reviewer approves tone (not "cute-aggressive", not patronizing)

---

### TC-2.1.2 — Mascot image load failure fallback

**Story:** #2.1
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Operator simulates CDN outage for mascot assets via `/cdn_block mascot_*`

**Steps (Telegram):**
1. Operator blocks CDN
2. Tester opens Twin viewer (cache cleared)
3. Observe weather cards

**Expected:**
- Cards still render
- Mascot slot shows just the weather emoji (🌧️ / ⛅ / ☀️) — no broken image icon
- No error message visible to user
- Twin viewer remains usable

**Pass criteria:**
- ✅ Graceful degradation
- ✅ No broken image icons
- ✅ Functionality preserved

---

### TC-2.1.3 — Alt text accessibility (screen reader)

**Story:** #2.1
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:**
- Tester has Telegram with screen reader enabled (TalkBack/VoiceOver)

**Steps (Telegram):**
1. Open Twin viewer with screen reader on
2. Navigate to each mascot image
3. Listen to alt text announcement

**Expected:**
- Each mascot image has Vietnamese alt text:
  - "Bé Tiền mặc áo mưa, biểu cảm bình tĩnh, cho kịch bản Khiêm tốn"
  - "Bé Tiền cầm dù, biểu cảm tự tin, cho kịch bản Bình thường"
  - "Bé Tiền đeo kính râm, biểu cảm vui, cho kịch bản Lạc quan"
- Alt text natural Vietnamese, not literal English translation

**Pass criteria:**
- ✅ Alt text present for all 3 mascots
- ✅ Vietnamese-native and descriptive

---

### TC-2.2.1 — First-time user goes through all 5 narrative screens

**Story:** #2.2 (Story narrative flow)
**Persona:** P-New (never opened Twin)
**Priority:** P0

**Pre-conditions:**
- Persona has not opened Twin previously
- Persona has > 7 days history (for narrative to have data)

**Steps (Telegram):**
1. Send `/twin` for first time
2. Observe Screen 1 — read content, tap "Tiếp tục →"
3. Observe Screen 2 — read, tap "Tiếp tục →"
4. Observe Screen 3 — read, tap "Tiếp tục →"
5. Observe Screen 4 — read, tap "Tiếp tục →"
6. Observe Screen 5 — read

**Expected:**
- Screen 1 (Present): "Hiện tại anh có [X], tăng [Y] tuần qua. Tốc độ ~[Z]/tháng. Đây là điểm xuất phát."
- Screen 2 (Future Range): 3 weather cards with mascots + life outcome on focused card
- Screen 3 (Why): "Bé Tiền tin anh ở Bình thường vì..." + brief causality summary
- Screen 4 (What you can do): preview of action suggestion
- Screen 5 (Want details?): "📊 Xem chart kỹ thuật" + "Đặt mục tiêu ngay" buttons
- Navigation buttons "Quay lại ←" present on screens 2-5
- Each screen logs view event with time-spent

**Pass criteria:**
- ✅ All 5 screens reachable
- ✅ Content matches spec per screen
- ✅ Back navigation works
- ✅ Screen view events logged

---

### TC-2.2.2 — User skips narrative with "Bỏ qua, xem nhanh"

**Story:** #2.2
**Persona:** P-New
**Priority:** P1

**Pre-conditions:**
- First-time Twin view, on Screen 1

**Steps (Telegram):**
1. Open Twin (`/twin`) for first time
2. On Screen 1, tap "Bỏ qua, xem nhanh"

**Expected:**
- Skip directly to Screen 5 (no Screens 2-4)
- Screen 5 shows full options
- Skip event logged (analytics: skip-rate metric)
- User can still go back to Screens 1-4 if desired

**Pass criteria:**
- ✅ Skip button visible only on Screen 1
- ✅ Skip jumps to Screen 5 instantly
- ✅ User not penalized for skipping (compact view available)

---

### TC-2.2.3 — Subsequent view (2nd+) shows compact

**Story:** #2.2
**Persona:** P-MassAffluent (already completed first-time flow)
**Priority:** P0

**Pre-conditions:**
- Persona has previously completed Twin first-time flow

**Steps (Telegram):**
1. Open Twin (`/twin`)
2. Observe initial render

**Expected:**
- Compact view: condensed combination of Screen 2 (weather cards) + Screen 5 (action buttons)
- Does NOT auto-trigger full 5-screen flow
- Option "Xem chi tiết →" available if user wants full flow again

**Pass criteria:**
- ✅ Compact view default for returning users
- ✅ Re-trigger option available
- ✅ Loads in < 2s

---

### TC-2.2.4 — Tap "Xem chart kỹ thuật" reveals probability cone

**Story:** #2.2
**Persona:** P-MassAffluent (power user)
**Priority:** P0

**Pre-conditions:**
- User on Screen 5 of narrative flow OR compact view

**Steps (Telegram):**
1. Tap "📊 Xem chart kỹ thuật"
2. Wait for chart to render
3. Observe chart

**Expected:**
- Probability cone chart renders (Phase 4A renderer re-used)
- X-axis: time (now to 2030)
- Y-axis: net worth in tỷ VND
- 3 bands shown with labels combining weather + P-code: "🌧️ Khiêm tốn (P10)", "⛅ Bình thường (P50)", "☀️ Lạc quan (P90)"
- Chart latency < 3s
- Back navigation returns to compact view

**Pass criteria:**
- ✅ Chart renders correctly
- ✅ Labels combine weather + P-code (power user context)
- ✅ Numbers match weather card numbers

---

## End of Batch 1

**Batch 1 summary:** 20 TCs covering Epic 1 (4 + 5 + 4 = 13 TCs) and Epic 2 (3 + 4 = 7 TCs).

**Next batch (Batch 2):** Epic 3 stories 3.1, 3.2, 3.3 — habit loop core (recompute + causality + action suggestion).

---

# 🧪 BATCH 2 — Epic 3 Stories 3.1, 3.2, 3.3 (TCs 21-40)

## Story 3.1 — On-Demand Twin Recompute

### TC-3.1.1 — User adds asset, sees Twin update notification < 5s

**Story:** #3.1
**Persona:** P-MassAffluent (established account, threshold-crossing delta expected)
**Priority:** P0

**Pre-conditions:**
- Persona logged in
- No pending Twin notifications
- Asset amount intended ≥ threshold (e.g., +5tr tiết kiệm for mass_affluent = above threshold)

**Steps (Telegram):**
1. Send command: `/add_asset` or use main menu "Thêm tài sản"
2. Choose type "Tiết kiệm", enter 5,000,000 VND
3. Confirm save
4. **Start stopwatch immediately on save confirmation**
5. Wait for Twin update notification

**Expected:**
- Save confirmation appears within 1s
- Twin update notification arrives: "Twin của anh vừa update — xem ngay" (or similar phrase variant)
- Notification arrives in ≤ 5 seconds from save confirmation
- Notification clickable → opens Twin viewer with delta highlighted

**Pass criteria:**
- ✅ Notification arrives within 5s (P95 target — may run 3 times to verify)
- ✅ Notification text user-friendly
- ✅ Notification leads to updated Twin view
- ✅ `twin_recompute_log` shows latency breakdown (operator verify)

**Notes:**
- Run 5 times consecutively, record latencies. P95 must be < 5s. If 1/5 fails P95, log and re-test next deploy.

---

### TC-3.1.2 — Small expense (< 200k) does NOT trigger notification

**Story:** #3.1
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Same as TC-3.1.1

**Steps (Telegram):**
1. Send command: `/add_expense`
2. Enter amount 150,000 VND, category "ăn uống"
3. Confirm save
4. Wait 30 seconds

**Expected:**
- Save confirmation appears
- **NO Twin update notification** sent
- Internal logs may show silent recompute (operator can verify)

**Pass criteria:**
- ✅ Zero notification in 30s window
- ✅ Backend log confirms below-threshold filter

---

### TC-3.1.3 — Idempotency: 2 events in 60s = 1 notification

**Story:** #3.1
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Same as TC-3.1.1

**Steps (Telegram):**
1. Add asset 5tr (event 1) — confirm save
2. Within 30 seconds, edit the asset (change to 6tr) — event 2
3. Wait for notifications

**Expected:**
- Only 1 notification arrives within 60s after first event
- Notification reflects final state (6tr — last-write-wins)

**Pass criteria:**
- ✅ Single notification (not 2)
- ✅ Content reflects most recent action
- ✅ No duplicate notifications

---

### TC-3.1.4 — Debounce: 5 actions in 30s aggregated

**Story:** #3.1
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:** Same

**Steps (Telegram):**
1. In quick succession (< 30s total), execute:
   - Add 2tr tiết kiệm
   - Add 1tr tiết kiệm (separate entry)
   - Add 500k expense (food)
   - Update existing asset value
   - Add 3tr cổ phiếu
2. Wait 10 seconds after last action

**Expected:**
- Backend debounces — only computes once after burst settles
- Single aggregated notification: "Twin của anh vừa update sau loạt thay đổi vừa rồi 💚"
- Notification content reflects net effect, not per-action

**Pass criteria:**
- ✅ ≤ 2 notifications total (ideally 1)
- ✅ Aggregated message phrasing acceptable
- ✅ Math correct in summary

---

### TC-3.1.5 — Offline user: notification queued, delivered on reopen

**Story:** #3.1
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Telegram chat with bot is closed (app backgrounded)

**Steps:**
1. Operator-triggered event via `/simulate_recompute_event <user_id> --type asset_add --amount 5000000`
2. Tester does NOT open Telegram for 10 minutes
3. After 10 min, tester opens Telegram

**Expected:**
- Notification visible in Telegram notification tray (mobile) or unread badge (web)
- On open, notification message appears in chat
- Content still relevant (not stale-feeling)

**Pass criteria:**
- ✅ Notification queued not lost
- ✅ Delivered on app open
- ✅ No duplicate delivery

---

### TC-3.1.6 — Notification appends to briefing if same morning

**Story:** #3.1
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:**
- Morning briefing already delivered to user today (at 8am)
- Current time: 10am same day

**Steps (Telegram):**
1. User receives 8am briefing
2. At 10am, user adds 5tr tiết kiệm
3. Wait for Twin update behavior

**Expected:**
- Twin update message appends to existing briefing thread (Telegram reply context)
- OR appears as compact follow-up: "Cập nhật: Twin vừa nhích lên sau hành động vừa rồi 💚"
- Does NOT create standalone new message in main chat (avoid 2 separate messages)

**Pass criteria:**
- ✅ No duplicate "main" message + briefing
- ✅ User experience feels continuous

---

### TC-3.1.7 — Latency consistency: 5 repeat actions, P95 manual check

**Story:** #3.1
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Persona logged in, ready for repeat actions
- Stopwatch (phone clock OK) ready

**Steps (Telegram):**
1. Add asset 5tr — start stopwatch on save confirmation, stop when notification arrives. Record T1.
2. Wait 2 minutes (cooldown to clear debounce)
3. Add asset 3tr — record T2
4. Wait 2 minutes, add 2tr — record T3
5. Wait 2 minutes, add 4tr — record T4
6. Wait 2 minutes, add 5tr — record T5

**Expected:**
- All 5 notifications arrive
- At least 4/5 latencies (P80 sample) within 5s
- No single notification exceeds 8s (would indicate P95 fail at scale)
- All 5 notifications correctly reflect the just-completed action

**Pass criteria:**
- ✅ Sort T1-T5, take the 5th (worst) — should ≤ 8s (manual P95 proxy)
- ✅ No notification timeout / failure
- ✅ Re-run with second tester later same day to triangulate

**Notes:**
- This is a manual proxy for the backend P95 load test, which runs separately as part of CI/perf pipeline. Manual test catches obvious regressions only.

---

## Story 3.2 — Causality Breakdown

### TC-3.2.1 — User taps "Vì sao Twin thay đổi" sees weighted breakdown

**Story:** #3.2
**Persona:** P-MassAffluent with recent positive delta
**Priority:** P0

**Pre-conditions:**
- User has delta from recent actions (last 7 days)
- Has ≥ 2 contributing factors

**Steps (Telegram):**
1. Open Twin viewer
2. Tap "🤔 Vì sao Twin thay đổi?"
3. Read output

**Expected output format:**
```
Vì sao Twin nhích lên?
✓ Anh thêm 5tr tiết kiệm (80%)
✓ HPG tăng 2.3% (15%)
✓ Lãi suất TK kỳ hạn tăng 0.2% (5%)

💡 Nếu duy trì nhịp này, Bình thường 2030 có thể đạt 5.5 tỷ.
```

**Pass criteria:**
- ✅ Top 3-5 factors shown
- ✅ Percentages sum to 100%
- ✅ Forward-looking sentence present
- ✅ Latency < 1s (cached) or < 3s (fresh)
- ✅ "Việc nên làm tiếp →" button visible at bottom

---

### TC-3.2.2 — Delta near zero shows "ổn định" message

**Story:** #3.2
**Persona:** P-MassAffluent with minimal activity last 7 days
**Priority:** P0

**Pre-conditions:**
- User had < threshold delta in past 7 days

**Steps (Telegram):**
1. Open Twin viewer
2. Tap "Vì sao Twin thay đổi?"

**Expected:**
- Output: "Twin của anh ổn định tuần này. Tiếp tục giữ nhịp 💚"
- No factor breakdown shown (avoid noise)
- No "Việc nên làm tiếp" button (or shows generic "Tiếp tục giữ nhịp")

**Pass criteria:**
- ✅ Soft message, not "empty data" error
- ✅ Encouraging tone

---

### TC-3.2.3 — New user (< 7 days history) fallback to "since signup"

**Story:** #3.2
**Persona:** P-New (4 days since signup)
**Priority:** P1

**Pre-conditions:** User has 4 days history, has added at least 1 asset

**Steps (Telegram):**
1. Open Twin viewer (if available)
2. Tap "Vì sao Twin thay đổi" (if button shown)

**Expected:**
- Causality based on "since signup" window, not 7-day default
- Output includes note: "(Bé Tiền theo dõi anh từ 4 ngày trước)"
- Factors shown as accumulated from signup

**Pass criteria:**
- ✅ No "insufficient data" error
- ✅ Helpful framing about partial history
- ✅ Factors accurate to actual signup-to-now window

---

### TC-3.2.4 — Forward-looking sentence computes correctly

**Story:** #3.2
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Persona has consistent saving rate (~5tr/month)

**Steps (Telegram):**
1. Open Twin viewer
2. Tap "Vì sao Twin thay đổi"
3. Read forward-looking sentence

**Expected:**
- Format: "Nếu duy trì nhịp này ([X] tiết kiệm/tháng), Bình thường 2030 có thể đạt [Y] tỷ"
- [X] matches user's actual rate (within tolerance ~10%)
- [Y] computed via linear projection (verify with operator quick math)

**Pass criteria:**
- ✅ Numbers plausible and self-consistent
- ✅ Uses "có thể" (possibility), not "sẽ" (certainty) — epistemic humility
- ✅ Sentence ≤ 25 words

---

### TC-3.2.5 — Causality cache hit on repeat view (same date)

**Story:** #3.2
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:** User viewed causality earlier today

**Steps (Telegram):**
1. Tap "Vì sao Twin thay đổi" → note output
2. Close, reopen Telegram after 1 hour
3. Tap "Vì sao Twin thay đổi" again

**Expected:**
- Same output as first view (cache hit)
- Latency < 500ms (vs ~2s for fresh compute)
- Cache expires after 24h (next-day view will re-compute)

**Pass criteria:**
- ✅ Consistency within 24h
- ✅ Re-compute happens after 24h
- ✅ User cannot detect cache mechanism

---

### TC-3.2.6 — Negative delta routes to Story 3.4 handler (not celebrative)

**Story:** #3.2
**Persona:** P-NegativeJourney (delta negative recent)
**Priority:** P0

**Pre-conditions:**
- Persona had negative delta past 7 days

**Steps (Telegram):**
1. Open Twin viewer
2. Tap causality button (if visible — may have different label like "Tuần này có gì?")

**Expected:**
- Output uses respectful tone copy (Story 3.4 templates)
- NO weighted breakdown ("80% / 15% / 5%") — would be insensitive
- Focus on 1 main contributing factor
- Action suggestion focused on review/diagnose

**Pass criteria:**
- ✅ Routed to negative handler correctly
- ✅ Vietnamese reviewer approves tone
- ✅ No "💚" celebrative emoji used

---

## Story 3.3 — Action Suggestion Embedded

### TC-3.3.1 — User sees action suggestion after causality

**Story:** #3.3
**Persona:** P-MassAffluent (positive delta, has < 3 goals)
**Priority:** P0

**Pre-conditions:** TC-3.2.1 setup — user has just seen causality

**Steps (Telegram):**
1. From causality view, tap "Việc nên làm tiếp →"
2. Read action suggestion card

**Expected output format:**
```
🎯 [Action title — e.g., "Quỹ dự phòng 6 tháng"]

[Description ≤ 2 câu — e.g., "Hiện anh có 5tr tiết kiệm. Tiến tới 60tr giúp Khiêm tốn của anh không quá thấp."]

⏱ ~ 2 phút để đặt mục tiêu

[✓ Đặt mục tiêu ngay] [⏰ Để tôi suy nghĩ thêm]
```

**Pass criteria:**
- ✅ Card format matches spec
- ✅ Time estimate visible (≤ 5 phút for in-Twin actions)
- ✅ Both buttons present
- ✅ Description concrete (not generic "save more")

---

### TC-3.3.2 — "Đặt mục tiêu ngay" executes inline

**Story:** #3.3
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:** TC-3.3.1 — action suggestion visible

**Steps (Telegram):**
1. Tap "✓ Đặt mục tiêu ngay"
2. Follow inline flow

**Expected:**
- Within 2-3 taps, goal created
- Confirmation: "Tuyệt vời! Mục tiêu đã đặt 🎉"
- Goal visible in user's goal list (verify via `/goals`)
- `twin_action_suggestions` table records `completed_at` timestamp
- Triggers Story 3.6 return tease

**Pass criteria:**
- ✅ Goal created within ≤ 3 taps total
- ✅ Confirmation message warm
- ✅ Database state updated
- ✅ Return tease appears (TC-3.6.x territory)

---

### TC-3.3.3 — "Để tôi suy nghĩ thêm" schedules 48h reminder

**Story:** #3.3
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:** Same as TC-3.3.1

**Steps (Telegram):**
1. Tap "⏰ Để tôi suy nghĩ thêm"
2. Note current timestamp
3. Wait 48 hours (or operator fast-forward via `/time_travel +48h`)

**Expected:**
- Immediate: friendly acknowledgement "Không sao, Bé Tiền sẽ nhắc lại sau"
- 48 hours later: reminder message arrives
- Reminder copy: "Còn nhớ ý tưởng [action] mình đã nhắc tới không? Cùng xem lại nhé"
- User can dismiss again or proceed

**Pass criteria:**
- ✅ `dismissed_at` recorded in DB
- ✅ Reminder fires at 48h ±1h
- ✅ Reminder copy soft, not pushy

---

### TC-3.3.4 — Repeat suppression after 3 dismissals

**Story:** #3.3
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:**
- User has previously dismissed same suggestion type 3 times in past 30 days

**Steps (Telegram):**
1. Tester (or operator) trigger 3 dismissals of "Quỹ dự phòng 6 tháng" suggestion across past sessions
2. Trigger conditions for 4th appearance of same suggestion
3. Open Twin viewer, navigate to action stage

**Expected:**
- Same suggestion type NOT shown
- Different action type appears (e.g., "Đầu tư định kỳ" instead of "Quỹ dự phòng")
- Variety guaranteed by system

**Pass criteria:**
- ✅ 4th time same type does NOT appear
- ✅ Alternative type shown
- ✅ User cannot tell suppression happened (no error message)

---

### TC-3.3.5 — HNW segment receives rebalance-focused suggestions

**Story:** #3.3
**Persona:** P-HNW
**Priority:** P0

**Pre-conditions:**
- Persona segment = HNW

**Steps (Telegram):**
1. Open Twin viewer, navigate to action suggestion

**Expected:**
- Suggestion type biased toward rebalancing, allocation review, tax topics
- Does NOT suggest "Save 5tr more this month" (insensitive to HNW context)
- Examples: "Review BĐS allocation vs liquidity", "Check tax efficiency of dividend portfolio"

**Pass criteria:**
- ✅ Suggestion context-appropriate for HNW
- ✅ Tone matches sophistication of user
- ✅ Vietnamese reviewer approves

---

### TC-3.3.6 — Existing aligned goal triggers progress check, not new goal

**Story:** #3.3
**Persona:** P-YoungPro (already has "Quỹ dự phòng" goal in progress at 30%)
**Priority:** P1

**Pre-conditions:**
- Persona has existing goal aligned with what would be suggested

**Steps (Telegram):**
1. Open Twin viewer, navigate to action suggestion

**Expected:**
- Instead of suggesting "create new goal", system suggests progress check:
  "Anh đang ở 30% mục tiêu Quỹ dự phòng — bước tiếp theo: thêm 5tr tuần này"
- Action button: "Cập nhật tiến độ" (not "Đặt mục tiêu")

**Pass criteria:**
- ✅ System detects existing goal
- ✅ Suggestion reframes as progress, not creation
- ✅ Direct deep-link to goal progress update

---

### TC-3.3.7 — No matching suggestion: graceful fallback

**Story:** #3.3
**Persona:** Custom — edge case (e.g., starter with no clear gap)
**Priority:** P1

**Pre-conditions:**
- User state doesn't match any specific suggestion bucket

**Steps (Telegram):**
1. Open Twin viewer, navigate to action stage

**Expected:**
- Fallback generic message: "Tiếp tục giữ nhịp tiết kiệm tuần này — Bé Tiền sẽ check lại tuần sau"
- No broken/empty card
- Optional "Cập nhật thêm thông tin về anh →" link to deepen profile

**Pass criteria:**
- ✅ No error / empty state
- ✅ Helpful next-step message
- ✅ User not left at dead-end

---

## End of Batch 2

**Batch 2 summary:** 20 TCs covering Story 3.1 (7 TCs — recompute infra) + Story 3.2 (6 TCs — causality) + Story 3.3 (7 TCs — action suggestion).

**Next batch (Batch 3):** Story 3.4 (Negative delta), 3.5 (Threshold), 3.6 (Return tease), plus cross-story integration tests.

---

# 🧪 BATCH 3 — Epic 3 Stories 3.4, 3.5, 3.6 + Integration (TCs 41-60)

## Story 3.4 — Negative Delta Handling

### TC-3.4.1 — Mild negative delta (1-5%) appropriate tone

**Story:** #3.4
**Persona:** P-MassAffluent with mild negative delta (~3% P50 down)
**Priority:** P0

**Pre-conditions:**
- Persona had moderate spending week, P50 down ~3% vs last week (set via fixture or simulated via admin command)
- Negative threshold crossed for mass_affluent segment

**Steps (Telegram):**
1. Operator: `/simulate_delta <user_id> -3pct` (sets up negative delta scenario)
2. Tester (as persona): wait for negative delta notification
3. Read notification copy in chat
4. Open Twin viewer
5. Tap causality button

**Expected (all visible in Telegram chat):**
- Notification copy uses respectful tone, e.g.:
  "Tuần này Twin của anh nhích xuống một chút — cùng xem lại nhé"
- NO words: "lỗi", "sai", "không nên", "đáng tiếc", "rủi ro", "nguy cơ"
- Visual cue in chat: "🌧️ Tuần Mưa Của Twin" framing (NOT "📉 Giảm")
- Twin viewer focuses 1 main factor (not weighted breakdown)
- Action suggestion: review-focused (e.g., "Review 3 khoản chi lớn nhất")

**Pass criteria:**
- ✅ Vietnamese reviewer reads message in Telegram, confirms no banned words
- ✅ Concrete review action, not vague "spend less"
- ✅ Vietnamese reviewer rates tone respectfulness ≥ 4/5

---

### TC-3.4.2 — Moderate negative (5-10%) with cautious framing

**Story:** #3.4
**Persona:** Custom — P50 down 7% over past week
**Priority:** P0

**Pre-conditions:** Same shape as TC-3.4.1 but larger delta

**Steps (Telegram):**
1. Operator: `/simulate_delta <user_id> -7pct`
2. Tester: receive notification
3. Read notification + open Twin viewer

**Expected:**
- Copy variant escalates slightly: "Twin của anh tuần này đi xuống đáng kể. Cùng xem nguyên nhân và cách điều chỉnh."
- Action suggestion proportionate to magnitude (e.g., suggest reviewing past month's spending pattern)
- Still NO guilt-inducing language

**Pass criteria:**
- ✅ Tone scales with magnitude (mild → moderate phrasing differs from TC-3.4.1)
- ✅ Suggestion proportionate
- ✅ Vietnamese reviewer approves all copy

---

### TC-3.4.3 — Tone check by Vietnamese reviewer across all variants

**Story:** #3.4
**Persona:** N/A — Vietnamese content reviewer as tester
**Priority:** P0

**Pre-conditions:**
- 5-7 negative delta scenarios prepared in fixture data (mild, moderate, by segment)

**Steps (Telegram):**
1. Operator triggers each negative scenario one by one for test personas
2. Reviewer opens each persona's Telegram chat
3. Reviewer reads each notification + Twin viewer + causality + action suggestion in Telegram
4. Reviewer records: tone rating (1-5), any banned words spotted, any tone concerns

**Expected:**
- All 5-7 variants visible in Telegram chat
- Reviewer can read each message naturally as a Vietnamese-native user would
- No banned words detected in any variant
- Required phrases present where appropriate: "Bé Tiền cùng anh xem lại", "Việc nên làm tiếp"

**Pass criteria:**
- ✅ Reviewer rates ≥ 4/5 on all variants
- ✅ Reviewer signs off in writing before production deploy
- ✅ Any flagged variant rewritten and re-tested

**Notes:**
- This is the most critical content quality gate of Phase 4.3 — extra care.

---

### TC-3.4.4 — Frequency cap: max 1 negative notification/week

**Story:** #3.4
**Persona:** P-MassAffluent with multiple negative deltas same week
**Priority:** P0

**Pre-conditions:**
- Persona has just received 1 negative notification this week (TC-3.4.1 or 3.4.2 setup)

**Steps (Telegram):**
1. Within same 7-day window, trigger another negative-delta-causing action: add 30tr unexpected expense
2. Wait 10 minutes

**Expected:**
- Save confirmation in chat normally
- **NO second negative notification** appears in chat
- Subsequent positive delta (if any) can still notify normally

**Pass criteria:**
- ✅ Zero additional negative notification visible in chat within the 7-day window
- ✅ User does not experience notification fatigue
- ✅ Wait 7 days, re-test: cap resets, next negative does trigger

---

### TC-3.4.5 — Lost-job heuristic: pause Twin notifications 4 weeks

**Story:** #3.4
**Persona:** P-NegativeJourney (income absent 35 days — set via fixture)
**Priority:** P0

**Pre-conditions:**
- Persona's income source absent ≥ 30 days

**Steps (Telegram):**
1. Tester (as persona) adds an expense or asset that would normally trigger Twin update
2. Wait 10 minutes for any notification

**Expected:**
- Save confirmation appears in chat normally
- **NO Twin update notification** during pause period
- Single one-time message appears (if first action since heuristic triggered):
  "Bé Tiền tạm dừng cập nhật Twin trong giai đoạn này. Anh có muốn cập nhật tình hình không?"
- Buttons in chat: "Tôi muốn tiếp tục theo dõi" / "Để Bé Tiền tạm dừng giúp tôi"

**Pass criteria:**
- ✅ Compassionate framing visible in Telegram
- ✅ User has visible agency to opt back in
- ✅ Tester taps "Tôi muốn tiếp tục theo dõi" → confirmation + Twin notifications resume

---

### TC-3.4.6 — User-visible behavior during multi-week negative pattern

**Story:** #3.4
**Persona:** Custom — 4 consecutive weeks negative delta (set via fixture)
**Priority:** P0

**Pre-conditions:**
- Persona has had 4 consecutive weekly negative deltas

**Steps (Telegram):**
1. Tester opens Telegram, navigates Bé Tiền chat
2. Trigger another negative-delta action (small expense)
3. Observe what tester sees in Telegram

**Expected (Telegram-visible only):**
- Tester receives at most 1 negative notification per week (frequency cap honored, TC-3.4.4 behavior)
- Notification copy NOT amplified or alarming despite multi-week pattern
- User experience identical to first negative — system doesn't shame for continued pattern
- May see (optional, depending on implementation): warm check-in message in chat from operator (manual outreach via founding member channel)

**Pass criteria:**
- ✅ No alarming "auto-escalation" message visible to user
- ✅ Cap still honored
- ✅ If operator outreach happened: message is human, warm, not auto-templated
- (Operator-side escalation flag verification is OUT of scope — handled in Admin Dashboard testing)

---

## Story 3.5 — Delta Threshold

### TC-3.5.1 — Above-threshold delta triggers notification

**Story:** #3.5
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Threshold for mass_affluent: 1% OR 10tr absolute (positive)
- User's current P50 ≈ 500tr → 1% = 5tr

**Steps (Telegram):**
1. Add asset worth 15tr (delta P50 likely > 10tr — well above absolute threshold)
2. Wait up to 5 minutes

**Expected:**
- Twin update notification arrives in chat
- Notification content reflects the action (mention of saving / asset addition)

**Pass criteria:**
- ✅ Notification visible in Telegram chat
- ✅ Latency < 5s (overlaps with TC-3.1.1)

---

### TC-3.5.2 — Below-threshold delta: no user-visible notification

**Story:** #3.5
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:** Same setup, threshold 1% OR 10tr

**Steps (Telegram):**
1. Add expense 300k (small impact on P50, below 1% and below 10tr absolute)
2. Wait 10 minutes

**Expected:**
- Save confirmation in chat
- **No Twin update notification** in chat
- (If user manually opens Twin viewer, the small delta may show as silent "Ổn định" — TC-1.3.x edge)

**Pass criteria:**
- ✅ Zero notification in Telegram within 10 minutes
- ✅ Twin viewer behavior consistent (TC-1.3.2 spirit)

---

### TC-3.5.3 — Multiple small deltas in 24h cumulative crosses threshold

**Story:** #3.5
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:** Threshold not yet crossed today

**Steps (Telegram):**
1. Over 6 hours, make 5 small adds: 2tr + 2tr + 2tr + 2tr + 3tr (each below 10tr threshold individually)
2. Each individual add: confirm no notification fired (verify by checking chat after 5 min each)
3. After 5th add (cumulative = 11tr, crosses threshold), wait up to 10 minutes

**Expected:**
- Individual events: no notifications appear in chat
- After cumulative threshold cross (5th event or daily aggregation window close): single aggregate notification in chat:
  "Trong 24h qua, Twin của anh đã nhích lên đáng kể nhờ nhiều khoản tiết kiệm nhỏ — xem chi tiết"

**Pass criteria:**
- ✅ Aggregate notification fires exactly once at threshold cross
- ✅ Content reflects accumulated effect, not per-event
- ✅ No per-event spam in chat

---

### TC-3.5.4 — Operator tunes threshold via Telegram admin command

**Story:** #3.5
**Persona:** Operator (using Telegram admin commands)
**Priority:** P1

**Pre-conditions:**
- Operator has admin Telegram access
- Test persona ready for follow-up verification

**Steps (Telegram):**
1. Operator sends admin command in Telegram: `/twin_threshold_tune mass_affluent positive_pct 1.5`
2. Read bot's response in chat
3. Switch to test persona's chat
4. Trigger an action that would have crossed old 1% threshold but is below new 1.5% (e.g., delta ≈ 1.2%)
5. Wait 5 minutes for notification

**Expected:**
- Step 2 (operator chat): Confirmation in chat: "Threshold updated. Segment: mass_affluent, field: positive_pct, new value: 1.5%, by operator @[name] at HH:MM"
- Step 5 (test persona chat): **NO notification** (action delta below new tuned threshold)
- Try misconfig: `/twin_threshold_tune mass_affluent positive_pct -1` → bot replies with clear error in chat: "Invalid threshold value — must be positive percentage"

**Pass criteria:**
- ✅ Operator command response visible in Telegram chat
- ✅ New threshold value takes effect immediately (verified via follow-up trigger test)
- ✅ Misconfig rejected with clear error message in chat

---

## Story 3.6 — Return Tease + Loop Closure

### TC-3.6.1 — Action completion triggers confirmation + tease

**Story:** #3.6
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:** TC-3.3.2 — user just completed action via "Đặt mục tiêu ngay"

**Steps (Telegram):**
1. Complete an action suggestion (e.g., tap "Đặt mục tiêu ngay" for "Quỹ dự phòng 6 tháng")
2. Read immediate response in chat

**Expected (visible in chat):**
- Immediate message: "Tuyệt vời! Mục tiêu đã đặt 🎉"
- Follow-up tease: "Bé Tiền sẽ cập nhật Twin theo dõi mục tiêu mới này tối nay. Sáng mai check lại xem Twin nhích thế nào nhé 💚"
- Optional continuation prompt (if user has < 3 assets): "Trong khi chờ — anh muốn ghi nhận khoản tiết kiệm/chi tiêu khác?"

**Pass criteria:**
- ✅ Confirmation + tease both visible in chat
- ✅ Tease mentions specific timing ("sáng mai", "tối nay")
- ✅ Tone soft, not pushy CTA — Vietnamese reviewer approves

---

### TC-3.6.2 — Next morning briefing continues loop seamlessly

**Story:** #3.6
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:** TC-3.6.1 happened yesterday (or operator fast-forward time)

**Steps (Telegram):**
1. Wait for next morning briefing (8am) or use operator command `/time_travel +14h` to simulate
2. Read briefing in chat

**Expected:**
- Briefing opens with reference to yesterday's action:
  "Hôm qua anh đã đặt mục tiêu [Quỹ dự phòng]. Twin đã cập nhật — đây là kết quả..."
- Twin status reflects the new goal in briefing summary
- User experience feels continuous (not 2 disconnected days)

**Pass criteria:**
- ✅ Briefing references yesterday's action in opening line
- ✅ Loop feels closed from user perspective
- ✅ No duplicate "main message" + briefing — single coherent message

---

### TC-3.6.3 — Cadence dial-back after 3+ actions in week

**Story:** #3.6
**Persona:** P-MassAffluent (high-engagement user)
**Priority:** P1

**Pre-conditions:**
- User has completed 3 actions in past 7 days (use fixture or live setup)

**Steps (Telegram):**
1. Complete 4th action via Twin flow
2. Read messages that follow in chat

**Expected:**
- Confirmation still appears: "Tuyệt vời! Mục tiêu đã đặt 🎉"
- Tease becomes lighter — e.g., short version "Sáng mai check Twin nhé 💚" without the longer descriptive sentence
- Skip "Trong khi chờ" continuation prompt (user clearly habituated)

**Pass criteria:**
- ✅ Confirmation always present (positive feedback never disappears)
- ✅ Tease visibly shorter than first-time TC-3.6.1
- ✅ User doesn't feel notification fatigue

---

### TC-3.6.4 — Late-night action: schedule same-morning briefing

**Story:** #3.6
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:**
- Current time is 23:30 or later (use operator `/time_travel` if testing daytime)

**Steps (Telegram):**
1. At 23:30, complete an action via Twin flow
2. Read tease message
3. Wait for next briefing (8am same morning — about 8.5 hours later)

**Expected:**
- Tease at 23:30: "Sáng mai check Twin nhé" (NOT "ngày kia")
- 8am briefing arrives same morning (not skipped to next day)
- Briefing references the late-night action

**Pass criteria:**
- ✅ Tease timing wording matches reality ("sáng mai" = within next 12h)
- ✅ Briefing arrives on schedule, not delayed
- ✅ No 30+ hour gap between action and feedback

---

### TC-3.6.5 — Multiple actions in 1 day bundled in tease

**Story:** #3.6
**Persona:** P-MassAffluent
**Priority:** P1

**Pre-conditions:**
- User intends to complete 3 actions same day

**Steps (Telegram):**
1. Complete action 1 at 10am — read tease in chat
2. Complete action 2 at 14:00 — read tease in chat
3. Complete action 3 at 18:00 — read tease in chat
4. Wait for next morning briefing

**Expected:**
- Each individual completion shows confirmation
- Teases either de-duplicate (subsequent teases shorter or skipped) OR bundled into single message at end of day
- Next morning briefing opens with bundled message:
  "Hôm qua anh đã có 3 quyết định — Twin đã update cả 3..."
- Math correct in summary (reflects net effect of all 3 actions)

**Pass criteria:**
- ✅ Chat not cluttered with 3 separate "Sáng mai check" messages
- ✅ Single consolidated tease or briefing acknowledgment
- ✅ All 3 actions visible in summary

---

## Cross-Epic Integration Tests (Telegram End-to-End)

### TC-INT-1 — Full happy path loop (trigger → view → action → return)

**Coverage:** Stories #3.1, #3.2, #3.3, #3.6 (full habit loop in single tester session)
**Persona:** P-MassAffluent
**Priority:** P0

**Pre-conditions:**
- Clean state, persona ready, no recent Twin notifications

**Steps (Telegram — single tester session, ~15 minutes):**
1. **Trigger:** Add 5tr tiết kiệm
2. **Recompute:** Wait for Twin update notification in chat (≤ 5s)
3. **View:** Tap notification → Twin viewer opens
4. **Causality:** Tap "Vì sao Twin thay đổi?" → see weighted breakdown
5. **Action:** Tap "Việc nên làm tiếp →" → see suggestion → tap "Đặt mục tiêu ngay"
6. **Confirmation:** Read confirmation + tease
7. **Return next day:** Operator `/time_travel +14h` to next morning
8. **Continuation:** Read next briefing in chat — verify references yesterday's loop

**Expected:** Full loop closes successfully end-to-end, entirely within Telegram chat. Each step's expected output visible to tester.

**Pass criteria:**
- ✅ All 8 steps complete in chat without error or dead-end
- ✅ User experience feels continuous, not disjointed
- ✅ Latency at each step acceptable (no > 10s wait anywhere)
- ✅ Tester writes 3-sentence summary of experience — positive

**Notes:**
- This is the master test. If this fails, Phase 4.3 is NOT ship-ready.

---

### TC-INT-2 — First-time user complete full flow

**Coverage:** Stories #1.1, #1.2, #1.3, #2.1, #2.2, #3.1, #3.2, #3.3 (everything that touches first impression)
**Persona:** P-New (brand new, just signed up, 1 asset added during onboarding)
**Priority:** P0

**Pre-conditions:**
- Persona is fresh, no Twin views ever
- Onboarding completed (Phase 4.1 flow done)

**Steps (Telegram):**
1. Send `/twin` first time
2. Go through full 5-screen narrative flow (Screen 1 → 5)
3. On Screen 5, tap "Đặt mục tiêu ngay" via embedded action suggestion
4. Complete goal creation flow
5. Read confirmation + tease

**Expected (all visible in chat):**
- Weather labels visible (Story 1.1 confirmed in screen 2)
- Life outcome shown on focused card (Story 1.2)
- Present anchor visible (Story 1.3, even if delta hidden due to < 7 days)
- 3 mascot versions render correctly (Story 2.1)
- 5 narrative screens flow correctly (Story 2.2)
- Action suggestion appropriate for new user (Story 3.3)
- Return tease activates loop expectation (Story 3.6)

**Pass criteria:**
- ✅ No friction or confusion observable in tester
- ✅ Tester reaches "first goal created" within < 10 minutes of opening Twin
- ✅ All visual elements render correctly in chat
- ✅ Tester (asked post-test): "Could you explain what Twin is to someone now?" — answer demonstrates correct understanding

---

### TC-INT-3 — Negative delta end-to-end Telegram experience

**Coverage:** Stories #3.1, #3.2, #3.4, #3.5 (negative path full experience)
**Persona:** P-NegativeJourney
**Priority:** P0

**Pre-conditions:**
- Persona set up with tough financial period context

**Steps (Telegram):**
1. Tester adds larger-than-usual expense (e.g., 30tr unexpected medical) OR operator `/simulate_delta <user_id> -7pct`
2. Wait for negative Twin notification in chat
3. Open Twin viewer via tap
4. View causality (should route to Story 3.4 respectful handler)
5. View action suggestion (should be review-focused, not save-focused)
6. Choose one of action options ("Cùng xem lại" or similar)
7. Read follow-up in chat

**Expected:**
- Notification copy respectful, not alarming (Vietnamese reviewer confirms)
- Visual cue weather "rainy" framing
- Causality emphasizes 1 main factor, not weighted percentages
- Action focuses on review/diagnose, not "save more"
- Subsequent week: no second negative notification (frequency cap)

**Pass criteria:**
- ✅ Tone passes Vietnamese reviewer rating ≥ 4/5
- ✅ No banned words anywhere in chat output
- ✅ Action concrete and helpful
- ✅ Cap honored: re-trigger small negative — no notification in same week

---

### TC-INT-4 — Briefing → Twin → Action chain entry point

**Coverage:** Briefing entry + Stories #1.x, #3.2, #3.3
**Persona:** P-MassAffluent (returning user)
**Priority:** P1

**Pre-conditions:**
- Morning briefing scheduled (8am)
- User had recent delta worth mentioning

**Steps (Telegram):**
1. Receive 8am morning briefing in chat
2. Briefing contains: "Twin của anh nhích lên sau khi anh thêm tiết kiệm 5tr tuần trước 💚 [👀 Xem Twin →]"
3. Tap "Xem Twin →" button
4. Land in Twin viewer (compact view for returning user — TC-2.2.3 behavior)
5. Tap "Vì sao Twin thay đổi?" → causality
6. Continue to action suggestion → execute

**Expected:**
- Briefing → Twin → Causality → Action chain seamless
- Each transition in chat < 2s
- User reaches action stage in < 4 taps from briefing

**Pass criteria:**
- ✅ Briefing CTA tap goes directly to Twin viewer (no extra menu)
- ✅ Compact view shown (not full 5-screen flow for returning user)
- ✅ Full loop completable within 5 minutes from briefing receipt

---

### TC-INT-5 — Power user with technical toggle ON

**Coverage:** Story #1.1 toggle + verify all other features still work
**Persona:** P-MassAffluent (power user with finance background)
**Priority:** P1

**Pre-conditions:**
- User has toggled "Hiển thị thuật ngữ kỹ thuật" = ON (TC-1.1.2)

**Steps (Telegram):**
1. Open Twin viewer
2. Observe 3 weather cards
3. View causality
4. View chart via "Xem chart kỹ thuật" button
5. Trigger an action that fires Twin update (add 5tr)
6. Read notification

**Expected (all in chat):**
- Weather labels still primary visible
- Small subscript or tooltip with P10/P50/P90 alongside each card
- Causality output unchanged (P-code internal only)
- Chart shows both weather emoji + P-code labels combined: "🌧️ Khiêm tốn (P10)"
- All other features (life outcome, action, recompute) work identically to non-power-user
- Twin update notification arrives normally

**Pass criteria:**
- ✅ Toggle works without breaking other features
- ✅ Power user gets technical info without losing simplicity
- ✅ Toggle reversible — toggling OFF returns to clean weather-only view

---

## End of Batch 3

**Batch 3 summary:** 20 TCs covering Story 3.4 (6 TCs), Story 3.5 (4 TCs), Story 3.6 (5 TCs), and Cross-Epic Integration (5 TCs).

---

# 📋 Test Execution Tracking

| Batch | TCs | Stories Covered | Est. Hours | Status |
|---|---|---|---|---|
| Batch 1 | 1-20 | Epic 1 (1.1, 1.2, 1.3) + Epic 2 (2.1, 2.2) | 6-8h | _Pending_ |
| Batch 2 | 21-40 | Epic 3 (3.1, 3.2, 3.3) | 8-10h | _Pending_ |
| Batch 3 | 41-60 | Epic 3 (3.4, 3.5, 3.6) + Cross-Epic INT | 6-8h | _Pending_ |
| **Total** | **60** | **All Phase 4.3 Telegram features** | **20-26h** | |

**Test execution plan:**
- Day 1: Batch 1 (Epic 1 + 2 — UI/comprehension features)
- Day 2: Batch 2 (Epic 3 core — habit loop infra triggers + flow)
- Day 3: Batch 3 (Epic 3 edge cases + integration)
- Day 4: Re-test failed cases + regression on Phase 4.1/4.2 features

**Pass threshold to ship Phase 4.3:**
- All P0 TCs pass: 100%
- All P1 TCs pass: ≥ 90%
- Cross-Epic INT TCs all pass (these are master tests)
- 0 P0 regression on Phase 4.1/4.2 features

---

# ⚠️ Out of Scope: Admin Dashboard (Epic 4) Testing

**Epic 4 (Twin Admin Dashboard) is NOT covered in this file** because admin dashboard is a web UI, not Telegram.

Epic 4 testing handled separately via:
- **Operator manual smoke test** on staging admin web URL (4 sub-section visual + functional verification)
- Funnel chart, loop health KPIs, comprehension widgets, delta distribution charts
- API response correctness via standard web-dev tooling
- Alert trigger verification (loop close rate < 15% → operator notification)
- Refer to Phase 4.2.5 admin testing convention as template

Recommended owner: same operator who manages Phase 4.2.5 dashboard.
Estimated effort: ~3-4 hours for full smoke test.

Also out of scope for this file (handled in separate test approach):
- Backend perf/load tests (CI pipeline)
- Automated content YAML linting (vi-localization-checker as part of build)
- Database integrity checks
- Operator escalation flag verification on admin dashboard

---

# 🛡️ Regression Test Requirements

After Phase 4.3 deploy, **must re-run these Telegram manual flows** to ensure no regression on existing features:

| Phase | Critical Telegram Flow | Re-test Effort |
|---|---|---|
| Phase 4.1 | Onboarding flow (signup → first asset → first briefing) | 2h |
| Phase 4.2 | NBA matrix suggestions, briefing quality | 3h |
| Phase 4.2.5 | Admin commands via Telegram (audit log, generic dashboards) | 1h |

**Regression pass criteria:**
- All previously-passing Telegram flows still work
- No new errors visible in user chat
- Latency for non-Phase-4.3 features unchanged (within ±10% per tester subjective sense)

---

*Last updated: 2026-05-18 — Phuong + Claude*
