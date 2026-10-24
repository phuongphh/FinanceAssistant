# Phase 4.3 — Issues Breakdown

> **Mục đích:** Document này break Phase 4.3 thành **issues có thể copy-paste vào GitHub Issues / Jira / Linear**. Cấu trúc parent-child: 4 Epic là parent issues (#E1 → #E4), 15 Story là child issues (#1.1 → #4.4). Mỗi issue có acceptance criteria *testable*, dependencies rõ ràng, estimate cụ thể.
>
> **Cách dùng:**
> - Tạo 4 parent issues trước, label `epic` + `phase-4.3`
> - Tạo 15 child issues, link tới parent qua "Sub-issue of #E[X]" hoặc Jira parent field
> - Assign theo thứ tự dependency (Epic 1 → Epic 2 → Epic 3 → Epic 4, trong mỗi Epic theo story number)
> - Mỗi child issue copy nguyên block "Acceptance criteria" sang issue tracker — đây là DoD cho dev

---

## 📊 Tổng Quan

| ID | Loại | Title | Estimate | Priority | Dependencies |
|---|---|---|---|---|---|
| #E1 | Epic | Twin Comprehension Foundation | 5 days | P0 | None |
| #1.1 | Story | Rename P10/P50/P90 → Weather Vocabulary | 1d | P0 | None |
| #1.2 | Story | Life Outcome Translation via LLM | 2d | P0 | #1.1 |
| #1.3 | Story | Present Anchor + Delta + Growth Rate Display | 2d | P0 | #1.1 |
| #E2 | Epic | Twin Storytelling | 3 days | P0 | #E1 |
| #2.1 | Story | Bé Tiền Mascot Personification (3 Versions) | 1.5d | P0 | #1.1 |
| #2.2 | Story | Story Narrative Flow (Swipe-Through Screens) | 1.5d | P0 | #1.1, #1.2, #2.1 |
| #E3 | Epic | Twin Habit Loop | 6 days | P0 | #E1, #E2 |
| #3.1 | Story | On-Demand Twin Recompute | 1.5d | P0 | None (independent infra) |
| #3.2 | Story | Causality Breakdown with Contribution Weights | 1d | P0 | #3.1 |
| #3.3 | Story | Action Suggestion Embedded in Twin Flow | 1d | P0 | #3.2 |
| #3.4 | Story | Negative Delta Handling | 1d | P0 | #3.2, #3.5 |
| #3.5 | Story | Delta Threshold for Noticeable Change | 0.5d | P0 | #3.1 |
| #3.6 | Story | Return Tease + Loop Closure | 1d | P1 | #3.3 |
| #E4 | Epic | Twin Admin Dashboard | 3 days | P0 | Phase 4.2.5 stable |
| #4.1 | Story | Twin Engagement Funnel Section | 0.75d | P0 | #3.1 (data flowing) |
| #4.2 | Story | Twin Loop Health Section | 1d | P0 | #3.3, #3.6 |
| #4.3 | Story | Twin Comprehension Signals Section | 0.5d | P1 | #1.1, #1.2 |
| #4.4 | Story | Twin Delta Distribution Section | 0.75d | P0 | #3.5 |

**Tổng:** ~17 days work + ~3 days buffer = ~3 tuần lịch.

**Critical path:** #1.1 → #1.2 → #2.2 → #3.1 → #3.2 → #3.3 → #4.2. Bottleneck là #2.2 (story narrative flow) vì depend nhiều story và là user-facing surface phức tạp nhất.

---

## 🏷️ Label Conventions

Mỗi issue nên gắn các label sau (chuẩn hóa filter trong issue tracker):

| Label category | Values |
|---|---|
| Phase | `phase-4.3` |
| Type | `epic` / `story` / `bug` / `tech-debt` |
| Area | `twin-ux` / `habit-loop` / `admin-dashboard` / `infra` / `content` / `vi-localization` |
| Priority | `p0` (blocking soft launch) / `p1` (nice-to-have) / `p2` (defer) |
| Surface | `telegram` / `admin-web` / `backend-only` |
| Risk | `risk:ux` / `risk:performance` / `risk:content` / `risk:tone` |

---

## 🅰️ Epic #E1 — Twin Comprehension Foundation

**Type:** Epic
**Labels:** `epic`, `phase-4.3`, `twin-ux`, `vi-localization`, `p0`, `telegram`
**Estimate:** 5 days
**Owner:** TBD (suggest senior dev + content reviewer pair)
**Goal:** User tap vào Twin lần đầu hiểu được "đây là điều gì" trong < 30 giây, không cần đọc giải thích dài.

### Description

Mass affluent VN không có background statistics → P10/P50/P90 = jargon. Epic này thay clothing của Twin: từ probability cone → weather metaphor; từ raw number tỷ VND → life outcome dễ hình dung; từ "future projection" → "present + đang đi đâu". Không thay compute layer (Phase 4A Monte Carlo giữ nguyên).

### Success criteria (Epic-level)

- [ ] 5/5 dogfood tester (non-finance background) giải thích đúng Twin trong < 2 phút sau khi xem lần đầu
- [ ] Twin first-view → 2nd-view conversion ≥ 50% trong cohort 14 ngày đầu
- [ ] 0 P0 regression: math output Twin viz vẫn match Phase 4A Monte Carlo within tolerance 0.5%

### Child issues
- #1.1 Rename P10/P50/P90 → Weather Vocabulary
- #1.2 Life Outcome Translation via LLM
- #1.3 Present Anchor + Delta + Growth Rate Display

---

### Issue #1.1 — Rename P10/P50/P90 → Weather Vocabulary

**Type:** Story
**Parent:** #E1
**Labels:** `story`, `phase-4.3`, `twin-ux`, `vi-localization`, `content`, `p0`, `telegram`
**Estimate:** 1 day
**Dependencies:** None
**Surface:** Telegram bot, Twin viewer screens

#### User story

> Là một mass affluent user mới dùng Bé Tiền lần đầu, tôi muốn thấy 3 kịch bản tương lai của mình bằng từ ngữ thân thuộc (thời tiết) thay vì jargon kỹ thuật, để tôi hiểu Twin trong vài giây mà không cần học khái niệm mới.

#### Acceptance criteria

- [ ] P10 trong UI text/UX hiển thị là **"🌧️ Khiêm tốn"** (kịch bản thận trọng nhất)
- [ ] P50 hiển thị là **"⛅ Bình thường"** (kịch bản trung tính, được Bé Tiền tin tưởng nhất)
- [ ] P90 hiển thị là **"☀️ Lạc quan"** (kịch bản tốt nhất)
- [ ] Mapping table `twin_label_mapping.yaml` chứa cả Vietnamese label, emoji, English fallback, internal P-code
- [ ] **Power user toggle:** Settings có option "Hiển thị thuật ngữ kỹ thuật (P10/P50/P90)" — OFF by default. Khi ON, tooltip "Bình thường = P50" xuất hiện cạnh label
- [ ] Backend response/log vẫn dùng P10/P50/P90 (chỉ presentation layer thay) — đảm bảo data layer không bị rename ảnh hưởng
- [ ] Migration 4.3.01: tạo `twin_label_mapping` table (id, p_code, vi_label, emoji, description_short, description_long)
- [ ] Content reviewer (Vietnamese-native) approve 3 labels + 3 description_long câu trước khi merge
- [ ] Mascot version key (Story 2.1 dependency) khớp với p_code

#### Out of scope

- Renaming chart axes (chart vẫn dùng P-code vì power user feature — handled Story 2.2 swipe-to-chart)
- Translation cho other percentiles ngoài 10/50/90

#### Files touched

- `content/twin/twin_label_mapping.yaml` (new)
- `apps/twin_renderer/label_resolver.py` (new module)
- `apps/twin_renderer/views/scenario_card.py` (modify)
- `db/migrations/4.3.01_twin_label_mapping.sql` (new)
- `tests/twin/test_label_resolver.py` (new)

#### Notes for implementer

- Emoji UNICODE codepoints: 🌧️ U+1F327, ⛅ U+26C5, ☀️ U+2600. Verify render trên Telegram iOS + Android + Telegram Web (3 platforms minimum).
- Telegram desktop có thể không render variation selector (FE0F) → test trên ít nhất 1 Win/Mac client.
- Phòng case user complain "tôi prefer P50" → toggle là respect, không argue.

---

### Issue #1.2 — Life Outcome Translation via LLM

**Type:** Story
**Parent:** #E1
**Labels:** `story`, `phase-4.3`, `twin-ux`, `vi-localization`, `content`, `llm`, `p0`, `telegram`
**Estimate:** 2 days
**Dependencies:** #1.1
**Surface:** Telegram bot, Twin viewer screens

#### User story

> Là một mass affluent user, khi tôi thấy "5.2 tỷ năm 2030", con số đó không gợi cho tôi cảm xúc gì cụ thể. Tôi muốn thấy "5.2 tỷ = đủ căn 2PN tại Q.7 + 1 tỷ tiết kiệm" để hình dung được tương lai của mình.

#### Acceptance criteria

- [ ] LLM service `life_outcome_translator.translate(amount_vnd, target_year, user_context)` → return Vietnamese phrase ≤ 30 từ
- [ ] User context include: location (city), known goals (nếu user đã set), age, dependents — để output có cá nhân hóa
- [ ] Prompt template trong `prompts/life_outcome_v1.txt` với explicit guardrails:
  - KHÔNG promise certainty ("chắc chắn", "đảm bảo")
  - KHÔNG dùng specific brand (no "Vinhomes", "MBBank")
  - KHÔNG suggest specific actions (đó là Story 3.3 work)
  - Format: "X tỷ = [tài sản hữu hình ví dụ] + [buffer description]"
- [ ] Cache strategy: cache key = hash(amount_bucket, year, user_segment, location). TTL 7 ngày. Cache hit target ≥ 80% sau 1 tuần
- [ ] Amount bucketing: round amount to nearest 200tr để boost cache hit rate (5.1tr/5.2tr/5.3tr → same bucket 5.2tr)
- [ ] Fallback nếu LLM unavailable: static lookup `life_outcome_fallback.yaml` với 5-8 generic phrases per amount bucket
- [ ] Render only cho focused card (Bình thường mặc định), không render cả 3 — giảm visual load + LLM cost
- [ ] User có thể tap "Đổi ví dụ khác →" để regenerate (max 3 lần/ngày, log để analytics)
- [ ] Content QA: 50-sample audit cho first cohort, operator review tone + accuracy

#### Edge cases

- Amount cực nhỏ (< 100tr): show "đủ chi phí sinh hoạt ~ X tháng" thay vì asset comparison
- Amount cực lớn (> 50 tỷ): show "tài sản thoải mái cho 2 thế hệ + dư cho quỹ giáo dục"
- User chưa set location: dùng "thành phố lớn" generic
- User là expat (location ngoài VN): defer — Phase 5+

#### Out of scope

- Đa ngôn ngữ (chỉ Vietnamese)
- Real-time BĐS pricing (dùng static reference table, update quarterly)

#### Files touched

- `apps/twin_renderer/life_outcome_translator.py` (new)
- `prompts/life_outcome_v1.txt` (new)
- `content/twin/life_outcome_fallback.yaml` (new)
- `content/reference/vn_housing_price_q2_2026.yaml` (new — static reference)
- `infra/cache/life_outcome_cache.py` (new, Redis-backed)
- `tests/twin/test_life_outcome_translator.py` (new)

#### Notes for implementer

- LLM choice: dùng cùng provider Phase 4.2 advisor (chi phí đã trong budget). Token target < 200 input + 60 output per call.
- Logging: log every LLM call với (input, output, latency) vào `llm_audit_log` table (Phase 4.1 infra) để content review batch hàng tuần.
- Operator command `/twin_outcome_review <user_id>` để inspect generated phrases per user.

---

### Issue #1.3 — Present Anchor + Delta + Growth Rate Display

**Type:** Story
**Parent:** #E1
**Labels:** `story`, `phase-4.3`, `twin-ux`, `p0`, `telegram`
**Estimate:** 2 days
**Dependencies:** #1.1
**Surface:** Telegram bot, Twin viewer screens

#### User story

> Là một mass affluent user, tôi không chỉ muốn biết "tôi sẽ có gì năm 2030", tôi cần thấy "tôi đang có gì BÂY GIỜ và tốc độ đang đi như thế nào" để judge xem tương lai có khả thi không.

#### Acceptance criteria

- [ ] Twin viewer screen có 3 element bắt buộc ở top:
  - **Present anchor:** "Hiện tại: 850tr (tài sản ròng)" — current net worth tính real-time
  - **Weekly delta:** "↑ Tăng 12tr so với tuần trước" hoặc "↓ Giảm 8tr so với tuần trước" — với visual arrow (↑ green, ↓ amber)
  - **Growth rate:** "Tốc độ ~ 50tr/tháng" — rolling 90-day average projected monthly rate
- [ ] Delta zero/very small (< threshold Story 3.5): hiển thị "Ổn định" thay vì show 0
- [ ] Growth rate chưa đủ data (< 30 ngày history): hiển thị "Đang theo dõi nhịp" thay vì giả số
- [ ] Tap vào present anchor → expand show net worth breakdown (tiết kiệm/đầu tư/BĐS) — re-use Phase 4.2 net worth view component
- [ ] Tap vào delta → trigger Story 3.2 causality breakdown
- [ ] Tap vào growth rate → expand show "Nếu duy trì tốc độ này, năm 2030 anh có thể đạt ⛅ X tỷ" — bridge tới future projection
- [ ] Visual: present anchor styled bigger/bolder so với 3 weather cards — visual hierarchy "present > future"
- [ ] Cache: present anchor refresh real-time (mỗi request), delta cache 1h, growth rate cache 24h

#### Edge cases

- New user (< 7 ngày): show present anchor only, hide delta + growth rate với message "Bé Tiền cần thêm vài ngày để hiểu nhịp tài chính của anh 💚"
- Net worth negative (debt > assets): show "-X tr" với amber color (không red — tránh alarming), special copy "Đây là điểm xuất phát — Bé Tiền sẽ cùng anh đi lên"
- Net worth biến động lớn (>30% trong 1 ngày): flag operator review (có thể data error)

#### Out of scope

- Custom growth rate window (always 90-day rolling — Phase 5+ có thể customize)
- Compare growth rate với peer cohort — Phase 5+ (privacy concern)

#### Files touched

- `apps/twin_renderer/views/present_anchor.py` (new)
- `apps/twin_renderer/services/growth_rate_calculator.py` (new)
- `apps/twin_renderer/views/twin_viewer.py` (modify — add anchor section)
- `tests/twin/test_growth_rate_calculator.py` (new)

---

## 🅱️ Epic #E2 — Twin Storytelling

**Type:** Epic
**Labels:** `epic`, `phase-4.3`, `twin-ux`, `content`, `p0`, `telegram`
**Estimate:** 3 days
**Owner:** TBD (suggest senior dev + illustrator/designer pair if available)
**Goal:** User cảm thấy Twin có "hồn", có cảm xúc — không phải dashboard khô khan. Mascot personification + narrative flow giúp user nhớ trạng thái cụ thể (3 versions of "Bé Tiền 2030").

### Description

Sau khi Epic 1 làm cho Twin *hiểu được*, Epic 2 làm cho Twin *cảm được*. Đây là Ý 3 (mascot personification) và Ý 4 (story narrative flow trước chart) trong simplification strategy. Mục tiêu: emotion attachment → memory anchor → habit foundation.

### Success criteria (Epic-level)

- [ ] User recall mascot version sau 7 ngày (ask trong founding interview): ≥ 60%
- [ ] Story narrative completion rate (swipe qua đủ 4-5 screens): ≥ 70%
- [ ] Chart view rate (sau khi swipe xong): ≤ 30% — confirm chart là power-user only, không phải mainstream

### Child issues
- #2.1 Bé Tiền Mascot Personification (3 Versions)
- #2.2 Story Narrative Flow (Swipe-Through Screens)

---

### Issue #2.1 — Bé Tiền Mascot Personification (3 Versions)

**Type:** Story
**Parent:** #E2
**Labels:** `story`, `phase-4.3`, `twin-ux`, `content`, `design`, `p0`, `telegram`
**Estimate:** 1.5 days (0.5d design + 1d integration)
**Dependencies:** #1.1
**Surface:** Telegram bot, Twin viewer screens

#### User story

> Là một mass affluent user, khi tôi nhìn 3 kịch bản tương lai, tôi muốn thấy Bé Tiền mascot phản ánh trạng thái của mỗi kịch bản (mặc áo mưa cho Khiêm tốn, cầm dù cho Bình thường, đeo kính râm cho Lạc quan) — để tôi có visual cue cảm xúc, không chỉ con số.

#### Acceptance criteria

- [ ] 3 sticker/image version Bé Tiền 2030:
  - **🌧️ Khiêm tốn version:** Bé Tiền mặc áo mưa giản dị, biểu cảm bình tĩnh — không sad, không lo lắng
  - **⛅ Bình thường version:** Bé Tiền cầm dù, biểu cảm tự tin nhẹ — neutral-positive
  - **☀️ Lạc quan version:** Bé Tiền đeo kính râm, biểu cảm vui — không over-the-top
- [ ] 3 image asset publish lên Telegram CDN, file size ≤ 100KB mỗi version (sticker-grade)
- [ ] Mapping `mascot_version_map.yaml` link p_code → asset URL
- [ ] Render trong scenario card (Story 1.1 output) ở vị trí top-right của mỗi weather card
- [ ] Fallback nếu image fail load: emoji weather only (🌧️/⛅/☀️) — không broken image icon
- [ ] **Tone guard:** Mascot KHÔNG: cute-aggressive ("UwU"), trẻ con quá ("baby talk"), patronizing. Founder + Vietnamese cultural reviewer approve mỗi version trước khi production
- [ ] Versioning: asset file naming `betien_2030_p10_v1.png` để có thể swap version mà không break cache

#### Edge cases

- Negative delta context: dùng mascot version Khiêm tốn nhưng KHÔNG dùng sad expression — tone respectful trong Story 3.4 đã cover
- A11y: alt text Vietnamese đầy đủ cho mỗi mascot version (Telegram screen reader support)

#### Out of scope

- Animated mascot (GIF/Lottie) — Phase 5+
- Seasonal variation (Tết, summer...) — Phase 5+
- User-customizable mascot — không scope

#### Files touched

- `content/mascot/mascot_version_map.yaml` (new)
- `assets/mascot/betien_2030_p10_v1.png`, `_p50_v1.png`, `_p90_v1.png` (new asset files)
- `apps/twin_renderer/views/scenario_card.py` (modify — add mascot slot)

#### Notes for implementer

- Nếu chưa có illustrator: use AI image generation (Midjourney/Flux) với 1 ngày iteration. Founder + vợ marketing review.
- Sticker pack potential: 3 mascot version có thể publish thành Telegram sticker pack cho founding member — viral surface bonus.

---

### Issue #2.2 — Story Narrative Flow (Swipe-Through Screens)

**Type:** Story
**Parent:** #E2
**Labels:** `story`, `phase-4.3`, `twin-ux`, `content`, `p0`, `telegram`
**Estimate:** 1.5 days
**Dependencies:** #1.1, #1.2, #2.1
**Surface:** Telegram bot, Twin viewer flow

#### User story

> Là một mass affluent user xem Twin lần đầu, tôi không muốn bị throw vào một chart ngay. Tôi muốn được dẫn dắt qua một câu chuyện 4-5 màn hình: "đây là hiện tại của anh → đây là tương lai có thể → vì sao → anh có thể làm gì". Sau đó nếu muốn, tôi mới xem chart.

#### Acceptance criteria

- [ ] Twin first-time-view flow gồm 5 screens (Telegram inline keyboard navigate forward/back):
  - **Screen 1 — Present:** "Hiện tại anh có 850tr, tăng 12tr tuần qua. Tốc độ ~50tr/tháng. Đây là điểm xuất phát."
  - **Screen 2 — Future Range:** 3 weather cards (mascot version) + life outcome cho card focus
  - **Screen 3 — Why this range:** "Bé Tiền tin anh ở Bình thường vì..." (causality summary — re-use Story 3.2 brief output)
  - **Screen 4 — What you can do:** Action suggestion preview (Story 3.3 entry point)
  - **Screen 5 — Want details?:** "📊 Xem chart kỹ thuật" button + "Đặt mục tiêu ngay" button
- [ ] Forward navigation: Telegram inline button "Tiếp tục →" / "Quay lại ←"
- [ ] User có thể skip flow bằng "Bỏ qua, xem nhanh" button on screen 1 → jump straight to Screen 5
- [ ] Sau lần xem đầu tiên: subsequent Twin views default to compact view (Screen 2 + 5 condensed) — re-show full flow chỉ nếu user request "Xem chi tiết" hoặc sau 30 ngày
- [ ] Analytics: log mỗi screen view với time-spent → tính narrative completion rate per cohort
- [ ] Tap "Xem chart kỹ thuật" → show probability cone chart (re-use Phase 4A renderer) với label P10/P50/P90 cùng weather emoji bên cạnh

#### Edge cases

- User start flow nhưng abandon mid-way: track abandon-screen index để optimize content
- User repeat first-time-view (cleared cache hoặc reset): respect — show full flow lại
- Narrow Telegram client: ensure all 5 screens render OK trên Telegram mobile narrow viewport (< 360px)

#### Out of scope

- Custom narrative paths per user segment (Phase 5+ A/B test)
- Skippable individual screen mid-flow

#### Files touched

- `apps/twin_renderer/flows/first_time_view.py` (new)
- `apps/twin_renderer/views/narrative_screen_*.py` (new — 5 screen views)
- `apps/twin_renderer/views/twin_viewer.py` (modify — branch first-time vs returning)
- `db/migrations/4.3.02_twin_view_events.sql` (new — track screen-level events)
- `tests/twin/test_first_time_view_flow.py` (new)

---

## 🅲 Epic #E3 — Twin Habit Loop

**Type:** Epic
**Labels:** `epic`, `phase-4.3`, `habit-loop`, `infra`, `content`, `p0`, `telegram`
**Estimate:** 6 days
**Owner:** TBD (senior dev — này có infra component nặng nhất)
**Goal:** Convert Twin từ static viewer thành habit loop: user action → Twin recompute < 5s → causality explanation → action suggestion → user execute → Twin update → user return next day. Loop close rate ≥ 20% trong 7 ngày là DoD chính.

### Description

Đây là Epic dài nhất và risk nhất Phase 4.3. 6 stories implement đầy đủ loop:
- 3.1 Recompute infra (loop trigger)
- 3.2 Causality (vòng 1 — trust)
- 3.3 Action (vòng 2 — reward + setup next loop)
- 3.4 Negative handling (honest moment)
- 3.5 Threshold (signal vs noise)
- 3.6 Return tease (loop closure)

### Success criteria (Epic-level)

- [ ] On-demand recompute P95 latency < 5s end-to-end
- [ ] Causality breakdown user-tested: ≥ 70% user trả lời đúng "tại sao Twin của bạn thay đổi" sau khi xem
- [ ] Action suggestion completion rate ≥ 30% trong 48h
- [ ] Negative delta notification: 0 user complaint về tone trong founding cohort
- [ ] Loop close rate (trigger → view → action → return) ≥ 20% trong 7 ngày — đây là metric quan trọng nhất Phase 4.3

### Child issues
- #3.1 On-Demand Twin Recompute
- #3.2 Causality Breakdown with Contribution Weights
- #3.3 Action Suggestion Embedded in Twin Flow
- #3.4 Negative Delta Handling
- #3.5 Delta Threshold for Noticeable Change
- #3.6 Return Tease + Loop Closure

---

### Issue #3.1 — On-Demand Twin Recompute

**Type:** Story
**Parent:** #E3
**Labels:** `story`, `phase-4.3`, `habit-loop`, `infra`, `performance`, `p0`, `backend-only`
**Estimate:** 1.5 days
**Dependencies:** None (uses existing Phase 4A Monte Carlo engine)
**Surface:** Backend + Telegram notification

#### User story

> Là một mass affluent user vừa thêm 5tr tiết kiệm, tôi muốn thấy Twin của mình phản ứng ngay (trong vài giây), không đợi đến briefing sáng mai — để cảm giác "tôi tác động được" còn fresh.

#### Acceptance criteria

- [ ] Worker `twin_recompute_worker` listen event bus với events:
  - `asset.created`, `asset.updated`
  - `income.added`
  - `expense.added` chỉ khi `amount >= 200000`
  - `goal.milestone_reached`
- [ ] Recompute path re-uses Phase 4A Monte Carlo engine (KHÔNG re-implement) — chỉ wrap với on-demand entry point
- [ ] **P95 latency target < 5s** end-to-end (event publish → notification delivered to Telegram)
- [ ] Latency breakdown logged vào `twin_recompute_log` (event_id, user_id, queue_ms, compute_ms, notify_ms, total_ms, delta_pct, notified_bool)
- [ ] Notification chỉ push nếu delta crosses threshold (Story 3.5) — silent recompute nếu dưới
- [ ] **Idempotent:** cùng user gửi 2 event trong 60s window → 1 notification (debounce với last-write-wins compute)
- [ ] **Debounce:** 5 actions liên tiếp trong 30s → compute lần cuối, notify 1 lần với aggregated delta
- [ ] **Backpressure:** nếu queue > 100 pending, drop user-facing notification, vẫn compute background — không clog system khi spike
- [ ] **Retry:** compute error retry 3 lần với exponential backoff, sau đó log Sentry và skip notification
- [ ] Migration 4.3.03: tạo `twin_recompute_log` table

#### Edge cases

- User offline (Telegram session closed): notification queue, deliver khi user mở app lần kế (Telegram already handles this)
- Briefing đã gửi cùng buổi sáng đó: notification append vào briefing thread, không tạo standalone message → avoid spam
- Monte Carlo timeout (> 10s): treat as error, retry 1 lần, log Sentry nếu fail tiếp
- Concurrent events từ cùng user (race condition): use Redis lock per user_id, 30s TTL

#### Out of scope

- Real-time market data refresh (still daily snapshot — Phase 5+)
- Push to non-Telegram channels (Zalo, email) — Phase 5+

#### Files touched

- `apps/workers/twin_recompute_worker.py` (new)
- `apps/twin_renderer/services/on_demand_recompute.py` (new)
- `infra/event_bus/twin_events.py` (modify — add subscribers)
- `db/migrations/4.3.03_twin_recompute_log.sql` (new)
- `tests/twin/test_recompute_worker.py` (new — include latency assertion test)

---

### Issue #3.2 — Causality Breakdown with Contribution Weights

**Type:** Story
**Parent:** #E3
**Labels:** `story`, `phase-4.3`, `habit-loop`, `content`, `p0`, `telegram`
**Estimate:** 1 day
**Dependencies:** #3.1
**Surface:** Telegram bot

#### User story

> Là một mass affluent user vừa thấy Twin update, tôi muốn hiểu CHÍNH XÁC điều gì đã đẩy Twin thay đổi — không phải chung chung "thị trường biến động". Tôi muốn biết "5tr tôi tiết kiệm tuần trước đóng góp 80%" để tôi học cách action nào quan trọng nhất.

#### Acceptance criteria

- [ ] Service `twin_causality_service.attribute_delta(user_id, period_days=7)` → return list of (factor, contribution_pct, action_taken_at, factor_type)
- [ ] Attribution algorithm (simplified MVP):
  - Snapshot Twin P50 tại t-7 và t-now
  - Re-run Monte Carlo với each factor "rolled back" individually → delta gap = factor contribution
  - Normalize weights to sum 100%
  - Top 3-5 factors only, group remaining as "Khác"
- [ ] Output trong chat format:
  ```
  Vì sao Twin nhích lên?
  ✓ Anh thêm 5tr tiết kiệm (80%)
  ✓ HPG tăng 2.3% (15%)
  ✓ Lãi suất TK kỳ hạn tăng 0.2% (5%)
  
  💡 Nếu duy trì nhịp này, Bình thường 2030 có thể đạt 5.5 tỷ.
  ```
- [ ] Forward-looking sentence computed by projecting current rate forward (linear projection cho MVP, không Monte Carlo nested)
- [ ] Copy template trong `content/twin/causality_explainer.yaml` — 5-7 variant để tránh stale
- [ ] Latency < 1s với cache (cache key = `causality:{user_id}:{date_iso}`, TTL 24h)
- [ ] Tap "Vì sao Twin thay đổi?" trong Twin viewer trigger này
- [ ] Sau breakdown: button "Việc nên làm tiếp →" link sang Story 3.3

#### Edge cases

- Delta gần zero: hide breakdown, show "Twin của anh ổn định tuần này. Tiếp tục giữ nhịp 💚"
- Delta negative: route sang Story 3.4 (negative handling), không show celebrative weights
- Factor attribution unstable (Monte Carlo variance): apply smoothing — show factor only if confidence > 70%, gộp uncertainty vào "Khác"
- User chưa có 7 ngày history: fallback to "since signup" attribution với note "(Bé Tiền theo dõi anh từ X ngày trước)"

#### Out of scope

- Shapley value full attribution — overkill, MVP simplified version đủ
- Causality cho cross-user comparison

#### Files touched

- `apps/twin_renderer/services/causality_service.py` (new)
- `content/twin/causality_explainer.yaml` (new)
- `infra/cache/causality_cache.py` (new)
- `tests/twin/test_causality_service.py` (new)

---

### Issue #3.3 — Action Suggestion Embedded in Twin Flow

**Type:** Story
**Parent:** #E3
**Labels:** `story`, `phase-4.3`, `habit-loop`, `content`, `p0`, `telegram`
**Estimate:** 1 day
**Dependencies:** #3.2
**Surface:** Telegram bot

#### User story

> Là một mass affluent user vừa hiểu vì sao Twin thay đổi, tôi muốn 1 gợi ý cụ thể, doable trong 5 phút — không phải lời khuyên chung chung "hãy tiết kiệm nhiều hơn".

#### Acceptance criteria

- [ ] Action library `content/twin/action_suggestion.yaml` với key tuple (state_segment, delta_direction, has_goal):
  - State: `starter` / `young_pro` / `mass_affluent` / `hnw`
  - Delta: `positive` / `neutral` / `negative`
  - Has_goal: `true` / `false`
- [ ] Service `twin_action_suggestion_service.suggest(user_context, delta_info)` → return `ActionSuggestion(type, title, description, estimated_minutes, deep_link)`
- [ ] Each suggestion has `time_estimate` ≤ 5 minutes for in-Twin actions
- [ ] Card format:
  ```
  🎯 [Action title]
  
  [Description ≤ 2 câu, concrete]
  
  ⏱ ~ [X] phút để hoàn thành
  
  [Button: ✓ Đặt mục tiêu ngay] [Button: ⏰ Để tôi suy nghĩ thêm]
  ```
- [ ] Logged vào `twin_action_suggestions` (Migration 4.3.04 — context_snapshot, suggested_at, user_response, completed_at)
- [ ] "Đặt mục tiêu ngay" → execute action inline (e.g., create goal record)
- [ ] "Để tôi suy nghĩ thêm" → set `dismissed_at`, schedule reminder 48h (re-attempt)
- [ ] **Repeat suppression:** cùng suggestion type dismissed 3 lần → skip 30 ngày, suggest type khác
- [ ] **Variety:** không suggest cùng type 2 lần liên tiếp trong 7 ngày

#### Edge cases

- User đã có goal aligned với suggestion: suggest progress check ("Anh đang ở 30% mục tiêu — bước tiếp theo: thêm 5tr") thay vì tạo mới
- User segment HNW: suggestions thiên về rebalancing, tax topics (defer concrete tax sang Phase 5+), KHÔNG "save 5tr"
- Negative delta: suggestions thiên về diagnose/review (Story 3.4), KHÔNG "save more" (insensitive)
- No matching suggestion: fallback generic ("Tiếp tục giữ nhịp tiết kiệm tuần này — Bé Tiền sẽ check lại tuần sau")

#### Out of scope

- AI-generated novel actions (chỉ library lookup, không LLM generate)
- Multi-step action chains (Phase 5+)

#### Files touched

- `apps/twin_renderer/services/action_suggestion_service.py` (new)
- `content/twin/action_suggestion.yaml` (new — ~30-50 action templates initial)
- `db/migrations/4.3.04_twin_action_suggestions.sql` (new)
- `tests/twin/test_action_suggestion_service.py` (new)

---

### Issue #3.4 — Negative Delta Handling

**Type:** Story
**Parent:** #E3
**Labels:** `story`, `phase-4.3`, `habit-loop`, `content`, `risk:tone`, `p0`, `telegram`
**Estimate:** 1 day
**Dependencies:** #3.2, #3.5
**Surface:** Telegram bot

#### User story

> Là một mass affluent user vừa có tuần xấu (chi tiêu lớn, mất việc, market rớt), tôi cần Twin nói tin xấu với tôi một cách tôn trọng + có giải pháp — không né tránh, không khen giả, không guilt-inducing.

#### Acceptance criteria

- [ ] Copy file `content/twin/negative_delta_copy.yaml` với 5-7 variant cho different negative scenarios:
  - Mild dip (1-5% P50 down): "ổn định nhẹ, tuần tới cùng xem lại"
  - Moderate (5-10% down): respectful framing + concrete review action
  - Significant (10-20% down): cautious framing + suggest professional consult (Phase 5+ advisor)
  - Severe (>20% down) OR Multi-week consecutive: trigger operator escalation
- [ ] Causality breakdown cho negative delta: focus 1 factor lớn nhất, KHÔNG chia weight nhỏ lẻ (avoid overwhelm)
- [ ] Action suggestion focus correction: "Review 3 khoản chi lớn nhất tháng" (concrete) thay vì "Spend less" (vague)
- [ ] **Banned words list** check via `vi-localization-checker` agent: "lỗi", "sai", "không nên", "đáng tiếc", "tiếc rằng", "rủi ro", "nguy cơ" — BLOCKED in negative copy
- [ ] **Required phrases** include: "Bé Tiền cùng anh xem lại", "Việc nên làm tiếp" — anchor at concrete + collaborative
- [ ] **Frequency cap:** max 1 negative notification/tuần per user
- [ ] Visual cue: "🌧️ Tuần Mưa Của Twin" framing thay vì "📉 Giảm" — soften tone qua weather metaphor
- [ ] Operator approval required: 5 sample negative messages reviewed before production deploy

#### Edge cases

- User vừa lose job (income absence 30+ days detected): skip Twin notification 4 tuần, send single message "Bé Tiền tạm dừng cập nhật Twin trong giai đoạn này. Anh có muốn cập nhật tình hình không?"
- Negative delta + user đã dismiss action suggestion 3 lần liên tiếp: pause negative notification 2 tuần
- Multiple negative deltas 4 tuần liên tiếp: trigger escalation flag → operator manual outreach via founding member channel
- Negative delta nhỏ (< 5% P50): không notify, silent track only

#### Out of scope

- Crisis mental health detection — defer Phase 5+ (huge scope, requires care)
- Public peer comparison — never (privacy + harmful)

#### Files touched

- `content/twin/negative_delta_copy.yaml` (new)
- `apps/twin_renderer/services/negative_delta_handler.py` (new)
- `apps/twin_renderer/guards/banned_words_check.py` (new)
- `tests/twin/test_negative_delta_handler.py` (new)

#### Notes for implementer

- Operator review este file cần ngắn nhất 30 phút trước production. Mọi update copy này = re-review.
- Founder cá nhân test 3 negative scenario trên staging trước khi merge.

---

### Issue #3.5 — Delta Threshold for Noticeable Change

**Type:** Story
**Parent:** #E3
**Labels:** `story`, `phase-4.3`, `habit-loop`, `infra`, `p0`, `backend-only`
**Estimate:** 0.5 day
**Dependencies:** #3.1
**Surface:** Backend config + operator command

#### User story

> Là một operator, tôi cần config threshold để Twin chỉ notify khi delta đủ noticeable — tránh spam khi small actions không thay đổi gì, tránh silent khi user đang chờ feedback.

#### Acceptance criteria

- [ ] Table `twin_delta_threshold_config` (migration 4.3.05):
  - `wealth_segment` (PK): starter / young_pro / mass_affluent / hnw
  - `threshold_pct_positive` (default: 1%)
  - `threshold_absolute_vnd_positive` (segment-specific, see below)
  - `threshold_pct_negative` (default: 0.5% — more sensitive)
  - `threshold_absolute_vnd_negative` (segment-specific)
  - `updated_by`, `updated_at`
- [ ] Default seed values:
  - starter: 1% OR 1tr (positive), 0.5% OR 500k (negative)
  - young_pro: 1% OR 3tr, 0.5% OR 1.5tr
  - mass_affluent: 1% OR 10tr, 0.5% OR 5tr
  - hnw: 0.5% OR 50tr, 0.3% OR 25tr
- [ ] Service `twin_threshold_service.is_noticeable(user_segment, delta_pct, delta_absolute_vnd, direction)` → bool
- [ ] **Inclusive at threshold:** delta == threshold → treat as noticeable
- [ ] **Aggregation:** Multiple deltas in 24h window, each individually below threshold, sum above → aggregate then notify once
- [ ] Operator command `/twin_threshold_tune <segment> <field> <value>` — adjust live with audit log via Phase 4.2.5 audit infrastructure
- [ ] Dashboard (Story 4.4) show histogram of deltas per segment, threshold line overlay → visual calibrate

#### Edge cases

- Threshold update mid-day: existing pending notifications use old threshold, new notifications use new
- Misconfig (threshold = 0 hoặc negative): reject command với clear error
- Segment unset (legacy user): fallback to mass_affluent default

#### Out of scope

- Per-user custom threshold (Phase 5+ premium feature?)
- ML-derived adaptive threshold — overkill

#### Files touched

- `apps/twin_renderer/services/threshold_service.py` (new)
- `db/migrations/4.3.05_twin_delta_threshold_config.sql` (new)
- `apps/operator/commands/twin_threshold_tune.py` (new)
- `tests/twin/test_threshold_service.py` (new)

---

### Issue #3.6 — Return Tease + Loop Closure

**Type:** Story
**Parent:** #E3
**Labels:** `story`, `phase-4.3`, `habit-loop`, `content`, `p1`, `telegram`
**Estimate:** 1 day
**Dependencies:** #3.3
**Surface:** Telegram bot

#### User story

> Là một mass affluent user vừa execute một action gợi ý, tôi muốn biết khi nào quay lại có ý nghĩa — "sáng mai check Twin" — không phải mơ hồ "lúc nào đó". Tôi cũng muốn được nhắc subtle, không pushy.

#### Acceptance criteria

- [ ] Sau khi `action_suggestion.complete` event fire:
  - Send confirmation message: "Tuyệt vời! Mục tiêu đã đặt 🎉"
  - Schedule briefing tag `twin_check_back_in` for next morning briefing
  - Show optional continuation prompt: "Trong khi chờ — anh muốn ghi nhận khoản tiết kiệm/chi tiêu khác?" (only if user has < 3 assets — beginner nudge)
- [ ] Briefing sáng hôm sau: open với "Hôm qua anh đã đặt mục tiêu [X]. Twin đã cập nhật — đây là kết quả..." → seamless loop continuation
- [ ] **Cadence dial-back:** nếu user complete 3+ actions trong 1 tuần, reduce tease frequency 50% (đã hình thành habit, không cần push)
- [ ] **Phrase rotation:** `content/twin/return_tease.yaml` với 5-7 phrase variants để tránh stale
- [ ] Tease format mềm, không CTA mạnh: "Sáng mai check lại nhé 💚" thay vì "Đừng quên mở Bé Tiền sáng mai!"

#### Edge cases

- User complete action giữa đêm (23h+): schedule briefing same morning thay vì next day để feel immediate
- User has briefing OFF: send return tease as standalone next morning 8am
- Multiple actions in 1 day: bundle tease vào single message ("Hôm qua anh đã có 3 quyết định — Twin đã update cả 3...")
- User uninstalled/inactive 7+ days: skip tease, defer to Phase 4.1 re-engagement flow

#### Out of scope

- Custom return time per user (Phase 5+ if requested)
- Multi-channel tease (only Telegram briefing path for now)

#### Files touched

- `apps/twin_renderer/services/return_tease_service.py` (new)
- `content/twin/return_tease.yaml` (new)
- `apps/briefing/morning_briefing.py` (modify — add twin_check_back_in section)
- `tests/twin/test_return_tease.py` (new)

---

## 🅳 Epic #E4 — Twin Admin Dashboard

**Type:** Epic
**Labels:** `epic`, `phase-4.3`, `admin-dashboard`, `observability`, `p0`, `admin-web`
**Estimate:** 3 days
**Owner:** TBD (full-stack dev — extend Phase 4.2.5 React+Vite+FastAPI stack)
**Goal:** Cho operator visibility real-time vào Twin loop health — phát hiện sớm trong soft launch nếu loop fail (low engagement, low action completion, high abandonment).

### Description

Phase 4.2.5 admin dashboard có generic KPI (DAU/MAU/cost). Twin là USP nên xứng đáng dedicated section. 4 sub-section: Engagement Funnel, Loop Health, Comprehension Signals, Delta Distribution. Tất cả extend pattern Phase 4.2.5, không tạo new infra.

### Success criteria (Epic-level)

- [ ] Dashboard ship cùng Twin features (ngày 1 soft launch operator có visibility)
- [ ] Latency dashboard load < 3s với caching
- [ ] Operator có thể identify Twin engagement drop trong 1 ngày (không phải 1 tuần)

### Child issues
- #4.1 Twin Engagement Funnel Section
- #4.2 Twin Loop Health Section
- #4.3 Twin Comprehension Signals Section
- #4.4 Twin Delta Distribution Section

---

### Issue #4.1 — Twin Engagement Funnel Section

**Type:** Story
**Parent:** #E4
**Labels:** `story`, `phase-4.3`, `admin-dashboard`, `p0`, `admin-web`
**Estimate:** 0.75 day
**Dependencies:** #3.1 (data flowing into twin_view_events)
**Surface:** Admin web dashboard

#### User story

> Là một operator, tôi cần thấy funnel: bao nhiêu user xem Twin lần đầu → bao nhiêu xem lần 2 → bao nhiêu thành habit (≥3 lần/tuần) → bao nhiêu abandon — để biết loop có forming hay không.

#### Acceptance criteria

- [ ] Section "Twin Engagement" trong admin dashboard với 4 funnel stages:
  - First Twin view (7-day cohort)
  - 2nd Twin view (within 7 days of first)
  - Habit threshold (≥3 views/week sustained)
  - Abandonment (no view 14+ days after first)
- [ ] Visualization: funnel chart + conversion % between stages
- [ ] Date range selector: 7d / 14d / 30d / custom
- [ ] Cohort filter: by signup week, by user segment
- [ ] Drill-down: click each stage → list of user_ids (anonymized but exportable cho operator)
- [ ] Refresh cadence: every 15 minutes (cached)

#### Edge cases

- Empty cohort: show "Chưa đủ data" placeholder
- Mid-day view: include partial day data với "as of HH:MM" timestamp

#### Out of scope

- Real-time (sub-15-minute) refresh
- A/B cohort comparison — Phase 5+

#### Files touched

- `admin-dashboard/src/pages/TwinDashboard/EngagementFunnel.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (new endpoints)
- `apps/admin_api/queries/twin_engagement_funnel.sql` (new)

---

### Issue #4.2 — Twin Loop Health Section

**Type:** Story
**Parent:** #E4
**Labels:** `story`, `phase-4.3`, `admin-dashboard`, `p0`, `admin-web`
**Estimate:** 1 day
**Dependencies:** #3.3, #3.6 (action + return data flowing)
**Surface:** Admin web dashboard

#### User story

> Là một operator, tôi cần đo chính xác loop close rate: bao nhiêu user đi qua trigger → view → action → return trong 7 ngày. Đây là metric quan trọng nhất Phase 4.3.

#### Acceptance criteria

- [ ] Section "Twin Loop Health" với 4 KPIs:
  - Trigger source breakdown (voluntary check / briefing tap / action-triggered) — pie chart
  - Action completion rate (suggested → completed in 48h) — line chart over time
  - Return rate after action (acted → returned within 24h) — line chart
  - Full loop close rate (trigger → view → action → return in 7d) — KPI card + trend
- [ ] **Alert thresholds** (configurable):
  - Loop close rate < 15% for 3 consecutive days → operator notification
  - Action completion < 20% for 7 days → alert
- [ ] Filter: by user segment, by cohort week
- [ ] Refresh: every 15 minutes

#### Edge cases

- New cohort (< 7 days): show "Đang thu thập" với progress bar to 7d mark
- Loop incomplete tracking (user returns at day 8): include in extended window analysis

#### Out of scope

- Per-loop-step latency analytics (Phase 5+ if needed)

#### Files touched

- `admin-dashboard/src/pages/TwinDashboard/LoopHealth.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (modify — add loop health endpoints)
- `apps/admin_api/queries/twin_loop_health.sql` (new)
- `apps/admin_api/services/twin_alerts.py` (new)

---

### Issue #4.3 — Twin Comprehension Signals Section

**Type:** Story
**Parent:** #E4
**Labels:** `story`, `phase-4.3`, `admin-dashboard`, `p1`, `admin-web`
**Estimate:** 0.5 day
**Dependencies:** #1.1, #1.2
**Surface:** Admin web dashboard

#### User story

> Là một operator, tôi cần signal user *có hiểu* Twin không — qua emoji reactions, time-on-Twin, "Vì sao thay đổi" tap rate. Đặc biệt quan trọng tuần 1-4 sau simplification ship để confirm Epic 1 thành công.

#### Acceptance criteria

- [ ] Section "Twin Comprehension" với 4 widgets:
  - Emoji reaction breakdown (💚 hài lòng / 😐 confused / 🤷 khác) — stacked bar over time
  - Time-on-Twin median (target: 30-120s for first view, < 30s for return view) — line chart
  - "Vì sao Twin thay đổi" tap rate (% users tapping after seeing delta) — KPI
  - Follow-up question rate (% users asking advisor about Twin within 24h of view) — KPI
- [ ] Cohort filter
- [ ] Refresh: every 15 minutes

#### Edge cases

- Emoji reaction count low: show absolute counts not %, avoid misleading %s
- Time-on-Twin extreme outliers (> 30 min — likely user idle): trim P99

#### Out of scope

- Sentiment analysis of follow-up questions (Phase 5+)

#### Files touched

- `admin-dashboard/src/pages/TwinDashboard/ComprehensionSignals.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (modify)
- `apps/admin_api/queries/twin_comprehension.sql` (new)

---

### Issue #4.4 — Twin Delta Distribution Section

**Type:** Story
**Parent:** #E4
**Labels:** `story`, `phase-4.3`, `admin-dashboard`, `p0`, `admin-web`
**Estimate:** 0.75 day
**Dependencies:** #3.5
**Surface:** Admin web dashboard

#### User story

> Là một operator, tôi cần thấy phân bố delta hằng tuần per segment để (a) calibrate threshold đúng, (b) phát hiện sớm nếu Twin math có bias (ví dụ toàn cohort đều positive — math sai).

#### Acceptance criteria

- [ ] Section "Twin Delta Distribution" với 3 widgets:
  - Delta histogram per wealth segment — overlay threshold line
  - P50 estimate distribution per cohort — snapshot wealth trajectory
  - Calibration tracking (predictions vs actuals khi có actuals) — scatter plot (Phase 5+ enrich)
- [ ] Filter: segment, time window
- [ ] Export CSV cho deeper analysis
- [ ] Refresh: every 15 minutes

#### Edge cases

- Segment small N: show note "N=X — sample size warning"
- Distribution skew detected (>80% positive cohort-wide): operator alert "Twin math possibly biased — review"

#### Out of scope

- Real-time delta streaming (15-min refresh đủ)

#### Files touched

- `admin-dashboard/src/pages/TwinDashboard/DeltaDistribution.tsx` (new)
- `apps/admin_api/routes/twin_metrics.py` (modify)
- `apps/admin_api/queries/twin_delta_distribution.sql` (new)

---

## 🔗 Cross-Epic Dependencies Map

```
Epic 1 (Comprehension Foundation)
   ├─ #1.1 (Weather labels) ─────────┬──→ #2.1 (Mascot)
   │                                  ├──→ #2.2 (Narrative flow)
   │                                  └──→ #4.3 (Comprehension dashboard)
   ├─ #1.2 (Life outcome) ────────────┼──→ #2.2
   │                                  └──→ #4.3
   └─ #1.3 (Present anchor) ──────────┘

Epic 2 (Storytelling)
   ├─ #2.1 (Mascot) ──────────────────→ #2.2
   └─ #2.2 (Narrative flow)            ↓
                                    [Twin viewer integration point]

Epic 3 (Habit Loop)
   ├─ #3.1 (Recompute) ──────────┬──→ #3.2 (Causality)
   │                              ├──→ #3.5 (Threshold)
   │                              └──→ #4.1 (Engagement dashboard data)
   ├─ #3.2 ──────────────────────┬──→ #3.3 (Action suggestion)
   │                              └──→ #3.4 (Negative)
   ├─ #3.3 ──────────────────────┬──→ #3.6 (Return tease)
   │                              └──→ #4.2 (Loop health dashboard)
   ├─ #3.4 ──────────────────────────→ [Standalone, careful tone QA]
   ├─ #3.5 ──────────────────────────→ #4.4 (Delta dashboard)
   └─ #3.6 ──────────────────────────→ #4.2

Epic 4 (Dashboard)
   ├─ #4.1 ←── #3.1
   ├─ #4.2 ←── #3.3, #3.6
   ├─ #4.3 ←── #1.1, #1.2
   └─ #4.4 ←── #3.5
```

---

## 📦 Migration Order

| # | Migration | Description | Issue |
|---|---|---|---|
| 4.3.01 | `twin_label_mapping` | Weather vocab mapping table | #1.1 |
| 4.3.02 | `twin_view_events` | Track screen-level Twin views | #2.2 |
| 4.3.03 | `twin_recompute_log` | Log every on-demand recompute | #3.1 |
| 4.3.04 | `twin_action_suggestions` | Track suggestions + responses | #3.3 |
| 4.3.05 | `twin_delta_threshold_config` | Per-segment thresholds | #3.5 |

All migrations: rollback-safe (forward-only schema change, không destructive). Test rollback trên staging trước khi production.

---

## ✅ Pre-Implementation Checklist

Trước khi dev start work bất kỳ issue nào, confirm:

- [ ] Phase 4.2.5 admin dashboard stable trên production (vì Epic 4 extend)
- [ ] Phase 4A Monte Carlo engine vẫn callable on-demand (verify với #3.1 dev)
- [ ] Vietnamese content reviewer xác nhận available trong 3 tuần (mỗi Epic cần review)
- [ ] Mascot illustrator/AI gen plan confirmed cho #2.1
- [ ] Operator schedule cho founding interview week 1 — feedback Twin comprehension
- [ ] LLM budget tăng ~20% để cover #1.2 life outcome translation calls
- [ ] Staging environment có realistic test data với 4 wealth segments

---

## 🎯 Definition of "Phase 4.3 Done"

**Engineering DoD:**
- [ ] All 15 stories merged + deployed
- [ ] All 5 migrations applied production
- [ ] No P0 regression vs current Twin behavior (math validation)
- [ ] Manual test cases pass (xem `phase-4.3-test-cases.md`)
- [ ] Admin dashboard 4 sub-sections operational

**Product DoD:**
- [ ] ≥ 80% founding tester (5/5 dogfood) hiểu Twin sau 2 phút
- [ ] Twin first-view → 2nd-view ≥ 50% trong 14 ngày
- [ ] Loop close rate ≥ 20% trong 7 ngày cohort
- [ ] Twin abandonment ≤ 30% sau 14 ngày
- [ ] 0 P0 complaint về negative delta tone trong founding cohort

**Communication DoD:**
- [ ] Deploy announcement gửi (`phase-4.3-deploy-announcement.md`)
- [ ] Founding members briefed về what's new
- [ ] Internal team handoff doc updated

---

*Last updated: 2026-05-18 — Phuong + Claude strategic review*
