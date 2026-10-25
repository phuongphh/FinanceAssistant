# Phase 4.3 — Twin Enhancement + Habit Loop + Admin Dashboard

> **Prerequisites:** Phase 4A (Twin MVP) ✅, Phase 4B (Twin Polish + Life Events) ✅, Phase 4.1 (Pre-Launch Hardening) ✅, Phase 4.2 (CX Hardening) ✅, Phase 4.2.5 (Admin Observability Layer) ✅.
> **Thời gian:** ~3 tuần (~12 ngày work + 3 ngày buffer testing). Inserted giữa Phase 4.2.5 và Phase 5.0 (Encryption).
> **Mục tiêu:** Chuyển Twin từ "feature đã ship nhưng có thể khó hiểu với mass affluent Việt" sang "habit-forming experience mà user mở mỗi ngày để xem tương lai tài chính có đang tốt lên không". Đồng thời hardening monitoring để soft launch June 2026 đo được sức khỏe của loop này real-time.
> **"Done":** Twin comprehension rate ≥ 80% trong 5-user dogfood test, Twin loop close rate (trigger → view → action → return) ≥ 20% trong 7 ngày đầu cohort, Twin dashboard ship cùng admin dashboard hiện tại, 0 P0 regression so với current Twin behavior.
> **Convention:** Giữ numbered epic convention từ Phase 4.2 (Epic 1, 2, 3, 4).

Phase 4.3 ra đời từ **strategic review session tháng 5/2026** với 2 insight quan trọng:

1. **Twin có thể khó hiểu với mass affluent VN** — Founder tự đặt câu hỏi này khi nhìn lại UX hiện tại. Probability cone chart + P10/P50/P90 jargon là pattern xa lạ với user không phải dân finance. Founder ask: *"Tôi là một người mới hoàn toàn, đơn giản, làm sao bạn giải thích Twin để tôi hiểu?"* — câu hỏi này signal rằng simplification cần happen TRƯỚC soft launch, không phải sau khi user feedback.

2. **Simplification chỉ là điều kiện cần, không phải đủ — habit loop mới là moat** — Twin dễ hiểu chỉ giúp user **xem** Twin. Twin có habit loop mới giúp user **quay lại xem** Twin. Loop là cấu trúc: trigger → delta → causality → action → recompute → return. Đây là pattern Strava/Duolingo/Apple Health dùng — và đây mới là USP thực sự của Bé Tiền, không phải bản thân Twin viz.

Phase 4.3 đóng cả 2 gap này thành 4 Epic, 15 stories trong ~3 tuần. Đây là phase **engineering tập trung user retention**, không phải feature mới — không thêm market data, không thêm asset type, không thêm advisor capability. Mọi work đều phục vụ 1 câu hỏi: *"Làm sao user mở Bé Tiền mỗi ngày để xem tương lai tài chính của mình có đang tốt lên không?"*

---

## 📋 Changelog so với Strategy V3 Roadmap

Phase 4.3 không có trong original Strategy V3 roadmap (V3 jump từ Phase 4.2 sang Phase 5.0 Encryption). Đây là phase được **chèn vào sau strategic review May 2026** với 2 lý do mạnh:

| Quyết định ban đầu (Strategy V3) | Quyết định mới (sau review) | Lý do |
|---|---|---|
| Phase 5.0 Encryption next | Phase 4.3 Twin Enhancement next | Encryption không user-facing, không giải quyết risk lớn nhất (Twin có wow không); Twin Enhancement giải quyết trực tiếp risk |
| Twin shipped trong 4A/4B đã đủ | Twin cần simplification + habit loop trước launch | Founder dogfood phát hiện comprehension gap; loop chưa rigorous |
| Admin Dashboard generic đủ | Twin xứng đáng dedicated dashboard section | Twin là USP, monitoring generic không đủ để phát hiện sớm nếu loop fail |
| Soft launch June 2026 với Twin current | Soft launch June 2026 với Twin simplified + loop | Cần engineering done trước cohort interview để loop được test thật |

Roadmap impact: Phase 5.0 (Encryption) push back ~3 tuần. Soft launch June 2026 timeline vẫn safe với "low-key" launch strategy (20-25 founding tháng 6, 25 còn lại tháng 7). Tết 2027 launch unaffected.

---

## 🎯 Triết Lý Thiết Kế Phase 4.3

### 1. Simplification trước comprehension, comprehension trước habit

User không thể habit-form với cái mình không hiểu. Đây là sequence: **dễ hiểu → user hiểu → user thấy giá trị → habit hình thành**. Không có gì chen ngang. Phase 4.3 ship theo thứ tự này: Epic 1 (comprehension) → Epic 2 (storytelling) → Epic 3 (habit loop) → Epic 4 (dashboard để đo).

### 2. Probability vẫn là honest framing, chỉ thay clothes

Chiến lược V3 đã quyết: KHÔNG show single number predictions. Phase 4.3 giữ nguyên decision này. Monte Carlo math + P10/P50/P90 vẫn là backend truth. Phase 4.3 chỉ thay **vocabulary** mà user thấy (Khiêm tốn/Bình thường/Lạc quan + weather emoji), không thay **math**. Honesty về uncertainty được preserve, chỉ là dùng từ ngữ phù hợp văn hóa hơn.

### 3. Story before chart, chart for power users

VN mass affluent đọc story dễ hơn đọc chart. Default Twin view là 4-5 màn hình narrative (mascot + 3 weather cards + delta + causality + action). Chart bị demote thành "Xem chi tiết kỹ thuật" — opt-in cho user finance-literate. Đây là **anti-pattern dashboard culture** — accept fact rằng đa số mass affluent VN không want dashboard, họ want guidance.

### 4. Habit loop = causality vòng + reward vòng, chạy song song

Một loop có 2 vòng lồng vào nhau. Vòng 1 (Causality) dạy user "tôi làm X → Twin phản hồi Y" → xây trust + financial literacy. Vòng 2 (Reward) cho user "tôi làm điều tốt → Twin nhích lên → dopamine" → xây habit. Chỉ vòng 1 = báo cáo khô khan. Chỉ vòng 2 = magic không trust được. Cả 2 cùng chạy = sticky + trustworthy.

### 5. Honest negative feedback là moment trust thật sự xảy ra

Twin phải dám nói "tuần này anh nhích xuống vì chi tiêu vượt 30%". Đây là moment khó nhất về engineering (UX cẩn thận, không demotivate) nhưng là moment build trust mạnh nhất. Phần lớn finance app né tránh tin xấu vì sợ user churn — đây là cơ hội differentiate. Negative delta phải có cùng polish như positive delta, không phải afterthought.

### 6. Threshold of noticeable change

User thêm 100k tiết kiệm mà Twin nhích thấy được = Twin fake. User thêm 5tr mà Twin im lặng = user feel powerless. Cần định nghĩa **delta threshold** (ví dụ ≥1% change ở P50 hoặc ≥2tr absolute, whichever larger). Dưới threshold = silent track. Trên threshold = proactive notify. Threshold này phải **calibrate theo wealth segment** — 1% với Starter rất khác 1% với HNW.

### 7. Latency phải gần real-time về cảm nhận

User thêm asset → bao lâu Twin update visible? Phase 4A/4B có "weekly cron + daily snapshot". Phase 4.3 add **on-demand recompute** với target P95 latency < 5s. Nếu phải đợi briefing sáng mai để thấy Twin update → loop bị đứt 12-20 tiếng → cảm xúc giảm 80%. Latency là feature, không phải nice-to-have.

### 8. Twin Dashboard là instrument để protect USP

Twin là USP của Bé Tiền. Generic admin metric (DAU, feature clicks) không đủ để phát hiện sớm nếu Twin loop fail. Cần dedicated Twin dashboard với engagement funnel + loop health + comprehension signals + delta distribution. Operator (founder) phải biết "loop close rate tuần này tăng hay giảm" sớm hơn 2 tuần — vì 2 tuần fix-cycle muộn = mất 50 founding members vĩnh viễn.

### 9. Continuity với Phase 4.1/4.2, không replace

Phase 4.3 KHÔNG sửa logic Phase 4A/4B math. KHÔNG sửa Phase 4.1 onboarding flow. KHÔNG sửa Phase 4.2 NBA matrix. Mọi work của Phase 4.3 là **extension hoặc replace user-facing layer** lên trên Twin engine sẵn có. Backend truth không đổi, presentation đổi.

---

## 📅 Phân Bổ Thời Gian

| Tuần | Trọng tâm | Output chính |
|---|---|---|
| **Tuần 1 (~5 ngày)** | Epic 1 — Twin Comprehension Foundation | Weather rename ship, life outcome translation pipeline, present anchor + delta display ship |
| **Tuần 2 (~5 ngày)** | Epic 2 — Twin Storytelling + Epic 3 phần 1 — Habit Loop Core | Mascot personification (3 versions for 2030), story narrative flow (4-5 screens swipe), on-demand recompute, causality breakdown |
| **Tuần 3 (~5 ngày)** | Epic 3 phần 2 + Epic 4 — Habit Loop Polish + Dashboard | Action suggestion embedded, negative delta handling, delta threshold, return tease, Twin admin dashboard 4 sections |

### Critical path

```
1.1 Weather rename ── 1.2 Life outcome translation ── 1.3 Present anchor
                                  │
                                  ▼
2.1 Mascot personification ── 2.2 Story narrative flow
                                  │
                                  ▼
3.1 On-demand recompute ── 3.2 Causality breakdown ── 3.3 Action suggestion
                                                              │
                                                              ▼
                                  3.4 Negative delta ── 3.5 Delta threshold ── 3.6 Return tease
                                                              │
                                                              ▼
4.1 Engagement Funnel ── 4.2 Loop Health ── 4.3 Comprehension ── 4.4 Delta Distribution
```

**Foundation:** Story 1.1 (Weather rename) phải ship đầu — vì tất cả user-facing copy trong Epic 2, 3 reference vocabulary này. Đổi vocabulary giữa chừng = rework cao.

**Parallelizable:** Epic 4 (Dashboard) có thể start song song với Epic 3 từ ngày 7 — backend metrics cần cho dashboard chính là metrics emit ra từ Epic 3 stories.

---

## 🗂️ Cấu Trúc Thay Đổi

### Files Touched

```
bot/handlers/
├── twin_handler.py                              (rewrite: 4-5 screen narrative flow, weather card view)
├── briefing_handler.py                          (extend: tease Twin delta in briefing intro)
└── asset_handler.py                             (extend: trigger on-demand recompute after save)

services/twin/
├── twin_service.py                              (extend: on-demand recompute API, delta threshold check)
├── twin_narrative_service.py                    (rewrite: replace P10/P50/P90 → weather metaphor)
├── twin_life_outcome_service.py                 (new: LLM-powered life outcome translation)
├── twin_causality_service.py                    (new: contribution attribution algorithm)
├── twin_action_suggestion_service.py            (new: contextual action suggestion engine)
├── twin_mascot_service.py                       (new: mascot personification logic for 3 versions)
├── twin_threshold_service.py                    (new: noticeable change threshold per segment)
└── twin_return_tease_service.py                 (new: return invitation cadence)

services/dashboard/
├── twin_metrics_service.py                      (new: aggregate Twin metrics for admin dashboard)
├── twin_engagement_funnel_service.py            (new: funnel computation)
├── twin_loop_health_service.py                  (new: loop close rate computation)
├── twin_comprehension_signals_service.py        (new: emoji + time-on-Twin aggregation)
└── twin_delta_distribution_service.py           (new: cohort delta distribution)

app/api/admin/
└── twin.py                                       (new: /api/admin/twin/* endpoints — extends Phase 4.2.5)

betien-admin/src/pages/
└── TwinDashboard.jsx                            (new: dedicated Twin section page)

betien-admin/src/components/
├── TwinFunnelChart.jsx                          (new)
├── TwinLoopHealthCard.jsx                       (new)
├── TwinComprehensionMatrix.jsx                  (new)
└── TwinDeltaDistribution.jsx                    (new)

content/twin/
├── weather_vocabulary.yaml                      (new: Khiêm tốn/Bình thường/Lạc quan + weather emoji)
├── life_outcome_templates.yaml                  (new: prompt templates for LLM translation)
├── mascot_personification.yaml                  (new: 3 versions copy + visual hints)
├── causality_explainer.yaml                     (new: explanation templates per attribution type)
├── action_suggestion.yaml                       (new: action library mapped to (state, delta) tuples)
├── negative_delta_copy.yaml                     (new: respectful tone for downward Twin)
└── return_tease.yaml                            (new: soft invitation phrases)

alembic/versions/
├── 4.3.01_add_twin_view_events.py               (new: twin_view_events table with trigger_source, duration, emoji)
├── 4.3.02_add_twin_action_suggestions.py        (new: twin_action_suggestions table with state, dismissed_at, completed_at)
├── 4.3.03_add_twin_recompute_log.py             (new: twin_recompute_log for latency tracking)
└── 4.3.04_add_twin_delta_threshold_config.py    (new: per-segment threshold config table)

docs/current/phase-4.3/
├── phase-4.3-detailed.md                        (this file)
├── phase-4.3-twin-habit-loop-spec.md            (technical + UX spec)
├── phase-4.3-twin-dashboard-spec.md             (admin dashboard spec)
└── phase-4.3-test-cases.md                      (test cases)
```

### New Database Tables

- **`twin_view_events`** — Log mỗi lần user xem Twin: `user_id`, `viewed_at`, `trigger_source` (briefing/voluntary/post_action/weekly_review), `duration_seconds`, `emoji_reaction`, `tapped_causality`, `tapped_chart_detail`, `session_id`
- **`twin_action_suggestions`** — Log mỗi suggestion: `user_id`, `suggested_at`, `action_type`, `context_snapshot` (user state khi suggest), `dismissed_at`, `completed_at`, `time_to_complete_minutes`
- **`twin_recompute_log`** — Track latency của on-demand recompute: `user_id`, `triggered_at`, `trigger_event`, `latency_ms`, `delta_p50`, `delta_classified_as_noticeable`
- **`twin_delta_threshold_config`** — Per-segment threshold: `wealth_segment`, `threshold_pct`, `threshold_absolute_vnd`, `updated_at` (operator-tunable)

---

## 🏗️ Epics & Stories

### Epic 1 — Twin Comprehension Foundation

**Mục tiêu:** Đổi vocabulary + viz để user mass affluent VN hiểu Twin trong 30 giây đầu mở app.

#### Story 1.1 — Rename P10/P50/P90 → Weather Vocabulary

**Mô tả:** Replace toàn bộ P10/P50/P90 labels bằng metaphor thời tiết Việt: 🌧️ Khiêm tốn / ⛅ Bình thường / ☀️ Lạc quan. Vocabulary này áp dụng cho mọi surface: Twin view, briefing tease, agent response, push notification, admin dashboard (optional — operator có thể chọn xem code name hay user-facing name).

**Why:** P10/P50/P90 là jargon thuần. User VN không phải dân finance brain auto-skip. Weather metaphor familiar (ai cũng xem dự báo thời tiết), encode được uncertainty (mưa = có khả năng nhưng không chắc), và VN-cultural (Tết "trời thương" — concept may rủi quen thuộc).

**Acceptance criteria:**
- File `content/twin/weather_vocabulary.yaml` chứa 3 entry với fields: `code` (p10/p50/p90), `vn_name`, `emoji`, `short_description`, `tone` (cautious/neutral/optimistic)
- Helper `twin_label(code) → (vn_name, emoji)` available trong `twin_narrative_service`
- Mọi callsite hiện hardcode "P10/P50/P90" được replace bằng helper (grep verify zero hardcoded reference trong code Phase 4.3+)
- Backend log/admin dashboard giữ code names (p10/p50/p90); chỉ user-facing surface dùng vn_name
- Migration không cần (chỉ content + code change)

**Edge cases:**
- Operator command/SQL query vẫn dùng code name → tránh confusion khi debug
- Briefing chỉ tease 1 weather (thường là Bình thường ⛅) — không list cả 3 để giữ briefing ngắn
- Voice channel (Phase 3.5 voice intent): pronunciation của emoji không phù hợp → text-only "Khiêm tốn/Bình thường/Lạc quan" không emoji khi qua voice channel

#### Story 1.2 — Life Outcome Translation via LLM

**Mô tả:** Cho mỗi weather card (Khiêm tốn/Bình thường/Lạc quan), generate 1 câu life outcome dạng "5.2 tỷ — Đủ căn 2PN tại Q.7 + 1 tỷ tiết kiệm" — translate abstract net worth thành life milestone concrete. LLM-powered với template prompt; cache aggressively vì input không đổi nhiều.

**Why:** "5.2 tỷ năm 2030" là abstract số. VN mass affluent think bằng life outcomes (mua nhà, cho con học, hưu trí). Brain phải tự dịch → cognitive load cao → user lazy không dịch → Twin lose meaning. Service tự dịch giúp Twin **trở thành cảm giác**, không phải con số.

**Acceptance criteria:**
- `twin_life_outcome_service.translate(amount_vnd, year, user_context)` → return string
- `user_context` include: location (city), age, family_status (single/married/with_kids), wealth_segment
- Template prompt trong `content/twin/life_outcome_templates.yaml` — không hardcode trong code
- LLM call qua `cost_tracking_adapter` (Phase 4.1 A.3) — KHÔNG bypass budget cap
- Cache key: hash(amount_bucket + year + city + age_bucket + family_status + segment). TTL 7 ngày. Cache hit ratio target ≥ 80% sau 2 tuần
- Fallback nếu LLM timeout/error: template generic ("~5 năm chi phí gia đình") — không bao giờ show raw number alone
- Latency P95 < 2s (với cache hit < 50ms)

**Edge cases:**
- User wealth_segment = Starter (Khởi Đầu): amount nhỏ (< 100tr) — life outcome khó (5tr không buy được gì meaningful). Fallback: "đủ làm quỹ dự phòng 1 tháng" thay vì compare property
- User wealth_segment = HNW (Tinh Hoa): amount lớn (>5 tỷ) — translation phải tone phù hợp, không vulgar. "Multi-asset portfolio rất ổn định" thay vì "mua được 3 căn hộ"
- Location missing: Default về so sánh chi phí gia đình thay vì property location-specific
- Family status missing: Generic "gia đình" thay vì specific số người
- LLM hallucinate giá BĐS sai (vd "căn hộ 2PN Q.7 giá 3 tỷ" trong khi thực tế 5-7 tỷ): template prompt phải có constraint + post-validate amount-to-outcome ratio

#### Story 1.3 — Present Anchor + Delta + Growth Rate Display

**Mô tả:** Mọi Twin view phải show 3 anchor số: (a) Hiện tại (net worth bây giờ), (b) Bình thường 2030 (P50 default highlight), (c) Delta + tốc độ ("Tăng 6.5 lần trong 4 năm. Tốc độ ~50%/năm"). Format text tách rõ, không chôn trong chart.

**Why:** Người không quen probabilistic thinking luôn hỏi "tăng bao nhiêu so với hiện tại?" — câu này phải được answer trước khi user hỏi. Anchor về present + tốc độ giúp user **cảm được** "tăng nhanh hay chậm" — concept gần với head hơn absolute future number.

**Acceptance criteria:**
- Twin view template chứa block "anchor display" trên cùng:
  ```
  Hiện tại: 800tr
  Bình thường 2030: 5.2 tỷ
  ↑ Tăng 6.5 lần · Tốc độ ~50%/năm
  ```
- Helper `compute_growth_rate(current, future, years)` → return (multiplier, annualized_pct)
- Format helper: `format_growth_text(current, future, years, weather="binh_thuong")` → return ready-to-display string
- Show delta so với **previous Twin view** (snapshot từ 7 ngày trước): "↑ Tăng 200tr so với tuần trước" — bonus info kích thích quay lại

**Edge cases:**
- User mới (chưa có snapshot 7 ngày trước): hide "so với tuần trước" line
- Negative growth (rare nhưng có thể): show "↓ Giảm X%" với neutral tone, không bi quan
- Future < current (rất rare, bug indicator): log warning, hide growth line, show only future amount

---

### Epic 2 — Twin Storytelling

**Mục tiêu:** Replace chart-first UX bằng story-first flow để user **cảm** Twin trước khi **đọc** Twin.

#### Story 2.1 — Bé Tiền Mascot Personification (3 Versions)

**Mô tả:** Cho mỗi weather card, show 1 visual của Bé Tiền mascot ở phiên bản 2030 tương ứng. Khiêm tốn: Bé Tiền giản dị, ngồi quán cà phê thường. Bình thường: Bé Tiền mặc đẹp vừa phải, ngồi balcony nhà. Lạc quan: Bé Tiền sang trọng, đứng cạnh xe đẹp. Static image MVP — không animate trong Phase 4.3.

**Why:** Người Việt cảm hình ảnh nhân vật mạnh hơn con số. Mascot personification = trick "imagined future self" mà nghiên cứu hành vi cho thấy increase savings rate 30%. Bé Tiền là mascot khả ái — tận dụng nó.

**Acceptance criteria:**
- 3 static PNG assets (256×256) cho 3 versions, designer-produced hoặc placeholder geometric variant nếu không có designer
- File `content/twin/mascot_personification.yaml` map weather code → asset URL + descriptive caption ("Bé Tiền 2030 — Khiêm tốn")
- Twin view render asset trên đầu mỗi weather card
- Tap vào mascot → expand life outcome detail (Story 1.2 output)
- Fallback nếu asset load fail: emoji-based representation (🧸 đủ)

**Edge cases:**
- Channel = Telegram nhưng user dùng app version cũ không support inline image: fallback to emoji
- Channel = Zalo (sau Phase 5.x): asset URL phải absolute (CDN-served), không relative path
- Mobile narrow screen: 3 mascot cards stack vertically thay vì horizontal — preserve readability

**Note future polish (NOT in 4.3 scope):**
- Animation (mascot wave, smile) — defer Phase 5.4 (Achievement & Badges)
- Outfit thay đổi theo season — defer
- User customize mascot — defer

#### Story 2.2 — Story Narrative Flow (Swipe-Through Screens)

**Mô tả:** Replace single-screen Twin view với **4-5 màn hình swipe** dạng Telegram inline keyboard "Tiếp →":
1. Mascot personification ("Đây là Bé Tiền của anh năm 2030")
2. 3 weather cards với tease "Có 3 khả năng..."
3. Highlight Bình thường với life outcome ("Bé Tiền tin anh ở đây...")
4. Causality preview ("Vì sao? →") — link tới Story 3.2
5. Action suggestion ("Việc nên làm tiếp →") — link tới Story 3.3

Chart full bị demote thành "📊 Xem chi tiết kỹ thuật" — opt-in button, không default.

**Why:** Dashboard-first UX assumes user wants to analyze. Mass affluent VN want **guidance + reassurance**, không phải analysis. Story narrative pacing cho user cảm trước, hiểu sau, action cuối — sequence tự nhiên của human emotion processing.

**Acceptance criteria:**
- Flow controller `twin_narrative_flow_service.py` quản lý 5-screen sequence với session state
- Mỗi screen có 1 button "Tiếp →" (forward), 1 button "Quay lại" (backward, optional screen 2+)
- Screen 4 (Causality preview) chỉ show tease 1-2 line + button "🤔 Vì sao thay đổi?" → trigger Story 3.2 full view
- Screen 5 (Action) chỉ show tease 1 line + button "🎯 Việc nên làm tiếp" → trigger Story 3.3 full view
- "📊 Xem chi tiết kỹ thuật" button available ở screen 3 — render full Monte Carlo chart (Phase 4A/4B viz)
- Skip option: command `/twin_quick` → show single-screen condensed version cho power user

**Edge cases:**
- User drop giữa flow (vd screen 2): session state expire sau 30 phút, không clutter; user gõ /twin sẽ start lại từ screen 1
- User repeat /twin sau khi đã xem trong 5 phút: skip storytelling, show "Twin của anh mới xem 5 phút trước. Có thay đổi gì không?" + link đi thẳng screen 3
- Channel voice (Phase 3.5): voice-only flow → linearize 5 screens thành 1 voice script ~30s, không có swipe

---

### Epic 3 — Twin Habit Loop

**Mục tiêu:** Implement 2 vòng causality + reward để user mở Twin mỗi ngày thay vì mỗi tuần.

#### Story 3.1 — On-Demand Twin Recompute

**Mô tả:** Sau mọi user action affecting wealth (add asset, add income, add expense ≥ 200k, complete goal milestone), trigger Twin recompute trong background; nếu delta crosses threshold, push notification "Twin của anh vừa update — xem ngay" trong < 5s. Target P95 latency < 5s end-to-end.

**Why:** Latency là feature. User thêm 5tr tiết kiệm → đợi briefing sáng mai để thấy Twin update = 12-20h gap = cảm xúc giảm 80%. < 5s feedback = causality loop close ngay khi memory còn fresh = trust + habit form.

**Acceptance criteria:**
- Worker `twin_recompute_worker` listen event bus: `asset.created`, `asset.updated`, `income.added`, `expense.added(amount >= 200000)`, `goal.milestone_reached`
- Recompute logic re-uses Phase 4A Monte Carlo engine (KHÔNG re-implement) — chỉ wrap với on-demand entry point
- Latency budget: queue → compute → threshold check → notify. Target P95 < 5s end-to-end. Log P95/P99 vào `twin_recompute_log`
- Notification chỉ push nếu delta crosses threshold (Story 3.5) — silent recompute nếu dưới
- Idempotent: cùng user action gửi 2 event không tạo 2 notification trong 60s window
- Backpressure: nếu queue > 100 pending, drop user-facing notification, vẫn compute background — không clog system khi spike

**Edge cases:**
- User thực hiện 5 action liên tiếp trong 30s: chỉ compute lần cuối (debounce 10s), notify 1 lần với aggregated delta
- User offline (Telegram chat đang đóng): notification queue, deliver khi user mở app lần kế
- Compute error: log Sentry, không notify, không retry hơn 3 lần
- Briefing đã gửi cùng buổi sáng đó: notification append vào briefing thread, không tạo standalone message → avoid spam

#### Story 3.2 — Causality Breakdown with Contribution Weights

**Mô tả:** Khi user tap "🤔 Vì sao Twin thay đổi?", show breakdown các factor contributing tới delta tuần này với % weight: "✓ Thêm 5tr tiết kiệm (80%) / ✓ HPG tăng 2.3% (15%) / ✓ Lãi suất TK tăng 0.2% (5%)". Plus 1-sentence forward-looking statement: "Nếu duy trì nhịp này, Bình thường 2030 có thể đạt 5.5 tỷ".

**Why:** Vòng 1 Causality của habit loop. User cần thấy "tôi làm X → kết quả Y". Breakdown với weight % giúp user prioritize tự nhiên (action có weight cao = đáng làm tiếp). Forward statement set up conditional expectation — prepare user cho next loop iteration.

**Acceptance criteria:**
- `twin_causality_service.attribute_delta(user_id, period_days=7)` → return list of (factor, contribution_pct, action_taken_at)
- Attribution algorithm (simplified MVP — không cần Shapley value):
  - Snapshot Twin P50 ở t-7 và t-now
  - Re-run Monte Carlo với each factor "rolled back" → delta gap = factor contribution
  - Normalize weights to sum 100%
  - Top 3-5 factors only, group remaining as "Khác"
- Output format trong `content/twin/causality_explainer.yaml`
- Forward-looking sentence: "Nếu duy trì nhịp này (X tiết kiệm/tháng), Bình thường 2030 có thể đạt Y tỷ" — Y computed by projecting current rate forward
- Latency < 1s với cache (cache key = user_id + date, TTL 24h)

**Edge cases:**
- Delta gần zero: hide breakdown, show "Twin của anh ổn định tuần này. Tiếp tục giữ nhịp 💚"
- Delta negative: route sang Story 3.4 (negative handling), không show celebrative weights
- Factor attribution unstable (Monte Carlo variance): apply smoothing — show factor only if confidence > 70%
- User chưa có 7 ngày history: fallback to "since signup" attribution

#### Story 3.3 — Action Suggestion Embedded in Twin Flow

**Mô tả:** Sau causality, suggest 1 action cụ thể doable trong < 5 phút. Suggestion context-aware: (user state) × (delta direction) × (existing goals) → 1 action prioritized. Card format với title + description + time estimate + 2 buttons ("Đặt mục tiêu ngay" / "Để tôi suy nghĩ thêm").

**Why:** Vòng 2 Reward + setup cho next loop. User vừa thấy delta + causality → ở moment dopamine cao. Suggest action ngay = capitalize on motivation peak. "Để tôi suy nghĩ thêm" path không phải dead-end — trigger reminder 48h sau.

**Acceptance criteria:**
- Action library trong `content/twin/action_suggestion.yaml` với tuple key (state_segment, delta_direction, has_goal):
  - State: starter/young_pro/mass_affluent/hnw
  - Delta: positive/neutral/negative
  - Has_goal: true/false
- `twin_action_suggestion_service.suggest(user_context, delta_info)` → return AciontSuggestion(type, title, description, estimated_minutes)
- Each suggestion has time_estimate (≤ 5 minutes for in-Twin actions; longer actions = "starter step in 5 min, full in 30 min")
- Logged vào `twin_action_suggestions` table với context_snapshot
- 2 buttons: "Đặt mục tiêu ngay" → execute action inline; "Để tôi suy nghĩ thêm" → set `dismissed_at`, schedule reminder 48h
- Repeat suppression: nếu cùng suggestion type dismissed 3 lần → skip suggestion đó trong 30 ngày, suggest type khác

**Edge cases:**
- User đã có goal aligned với suggestion: thay vì suggest tạo mới, suggest progress check ("Anh đang ở 30% mục tiêu — bước tiếp theo: thêm 5tr")
- User segment HNW: suggestions thiên về rebalancing, tax optimization (defer concrete tax features sang Phase 5+), không "save 5tr"
- Negative delta: suggestion thiên về review expense, không "save more" (insensitive)
- No matching suggestion: fallback generic ("Tiếp tục giữ nhịp tiết kiệm tuần này")

#### Story 3.4 — Negative Delta Handling

**Mô tả:** Khi Twin nhích xuống (P50 decrease ≥ threshold), trigger notification với tone respectful + actionable. Format: "Tuần này Twin của anh nhích xuống một chút. Lý do: [causality]. Việc nên làm: [action focused on diagnose/correct]". Tránh language guilt-inducing.

**Why:** Honest negative feedback là moment trust thật sự xảy ra. Phần lớn finance app né tránh tin xấu → user develop pattern "app này chỉ khen, không tin được". Bé Tiền dám nói tin xấu **với cách respectful + giải pháp** = differentiate massively. Đây là engineering challenge UX cẩn thận nhất Phase 4.3.

**Acceptance criteria:**
- `negative_delta_copy.yaml` với 5-7 template variant cho negative tone — không stale single template
- Causality breakdown cho negative delta: focus factor lớn nhất gây giảm, không chia weight nhỏ lẻ (overwhelm)
- Action suggestion focus correction: "Review 3 khoản chi lớn nhất tháng" (concrete) thay vì "Spend less" (vague)
- KHÔNG dùng từ: "lỗi", "sai", "không nên", "đáng tiếc" — respectful tone manual review qua `vi-localization-checker` agent + operator approve
- Frequency cap: max 1 negative notification/tuần per user (avoid notification fatigue khi user đang khó khăn)
- Visual cue: "🌧️ Twin Mưa Cuối Tuần" framing thay vì "📉 Giảm" — soften tone qua weather metaphor

**Edge cases:**
- User vừa lose job (income → 0): heuristic detect (income absence 30+ days) → skip Twin notification 4 tuần, show "Bé Tiền tạm dừng cập nhật Twin trong giai đoạn này. Anh có muốn cập nhật tình hình không?"
- Negative delta + user dismissed action suggestion 3 lần: pause negative notification 2 tuần (user clearly knows + not ready)
- Negative delta nhỏ (< 5% P50): không notify, silent track (avoid noise)
- Multiple negative deltas liên tiếp 4 tuần: trigger escalation flag cho operator → manual outreach via founding member channel

#### Story 3.5 — Delta Threshold for Noticeable Change

**Mô tả:** Define threshold để classify delta là "noticeable" (worth notify) vs "silent" (silent track). Threshold = max(1% P50 absolute, 2tr VND absolute, segment-adjusted) — calibrated per wealth segment để Starter và HNW có cảm giác cân xứng.

**Why:** Notification spam = user mute = retention chết. Silent on small delta = user feel powerless ("tôi làm gì cũng không thay đổi gì"). Threshold đúng = signal-to-noise ratio cao = user trust system.

**Acceptance criteria:**
- Table `twin_delta_threshold_config` với rows per wealth_segment:
  - starter: 1% OR 1tr (whichever larger)
  - young_pro: 1% OR 3tr
  - mass_affluent: 1% OR 10tr
  - hnw: 0.5% OR 50tr
- `twin_threshold_service.is_noticeable(user_segment, delta_pct, delta_absolute_vnd)` → bool
- Operator command `/twin_threshold_tune <segment> <pct> <absolute_vnd>` để adjust live (audit log via Phase 4.2.5)
- Default values seed migration 4.3.04
- Dashboard show histogram of deltas per segment, threshold line overlay → operator visual calibrate

**Edge cases:**
- Delta = exactly at threshold: treat as noticeable (inclusive)
- Multiple deltas in 1 day, each below threshold individually but sum above: aggregate per 24h window before notify
- Negative delta threshold: same magnitude but separate config (negative_threshold_pct could be larger to avoid alarming on small dips)

#### Story 3.6 — Return Tease + Loop Closure

**Mô tả:** Sau khi user complete action suggestion, show confirmation + soft tease "Bé Tiền sẽ cập nhật Twin theo dõi mục tiêu mới này tối nay. Sáng mai check lại xem Twin nhích thế nào nhé 💚". Plus optional continuation prompt "Trong khi chờ — anh muốn ghi nhận khoản tiết kiệm/chi tiêu nào khác?"

**Why:** Loop closure. Action done → confirmation + clear next trigger ("sáng mai") + optional momentum tap. Đây là moment habit hardens — user biết khi nào quay lại + có lý do quay lại.

**Acceptance criteria:**
- Sau khi action_suggestion.complete event fire:
  - Send confirmation message
  - Schedule briefing tag "twin_check_back_in" for next morning briefing
  - Show optional continuation prompt (if user has < 3 assets — nhắc thêm)
- Briefing sáng mai: open với "Hôm qua anh đã đặt mục tiêu X. Twin đã cập nhật — đây là kết quả..." → seamless loop
- Cadence: nếu user complete 3 actions trong 1 tuần, dial back tease frequency (user đã in habit, không cần push)
- Phrase variants trong `return_tease.yaml` (5-7 phrase rotation, avoid stale)

**Edge cases:**
- User complete action giữa đêm (23h+): schedule briefing same morning thay vì next day để feel immediate
- User has briefing OFF: send return tease as standalone next morning 8am
- Multiple actions in 1 day: bundle tease into single message ("Hôm qua anh đã có 3 quyết định — Twin đã update cả 3...")

---

### Epic 4 — Twin Admin Dashboard

**Mục tiêu:** Extend Phase 4.2.5 admin dashboard với 4 sub-section dedicated cho Twin — đo loop health real-time để phát hiện sớm nếu Twin không stick.

#### Story 4.1 — Twin Engagement Funnel Section

**Mô tả:** Dashboard section show funnel: First Twin view rate → 2nd view rate → Weekly habit threshold (≥3 views/tuần) → Abandonment rate. Per cohort + per wealth segment breakdown.

**Acceptance criteria:**
- API endpoint `GET /api/admin/twin/engagement-funnel?days=30&segment=all`
- Response include 4 funnel stages với counts + conversion rate giữa các stages
- Frontend `TwinFunnelChart.jsx` render horizontal funnel
- Drill-down: click stage → list users in that bucket
- Cache TTL 10 phút

**Edge cases:**
- Cohort size < 10: show warning "data thin, interpret carefully"
- New phase deploy (4.3 ship): reset baseline metric, mark with marker line on chart

#### Story 4.2 — Twin Loop Health Section

**Mô tả:** Track loop close rate end-to-end: trigger → view → action → return. Show: % users completing full loop in 7 days, breakdown by trigger source, time-to-complete distribution.

**Acceptance criteria:**
- API endpoint `GET /api/admin/twin/loop-health?days=14`
- Loop definition: user has at least 1 sequence within 7 days of (view → action_suggestion_completed → return_view)
- Frontend `TwinLoopHealthCard.jsx` show: loop_close_rate KPI, trigger_source pie, time-to-complete histogram
- Target line displayed: ≥20% loop close rate
- Alert if loop_close_rate drops > 30% week-over-week → highlight red

**Edge cases:**
- User completes action but doesn't return (timeout 7 days): logged as "partial loop"
- Multiple loops per user: count distinct loops, not just user-level boolean

#### Story 4.3 — Twin Comprehension Signals Section

**Mô tả:** Aggregate emoji reactions, time-on-Twin, causality button click rate, follow-up question rate via agent. Heuristic indicator "comprehension health" — operator manual review when signals diverge.

**Acceptance criteria:**
- API endpoint `GET /api/admin/twin/comprehension?days=7`
- Metrics: emoji distribution, time-on-Twin median + p25/p75, causality button CTR, agent follow-up rate
- Frontend `TwinComprehensionMatrix.jsx` show heatmap of metric × cohort
- Alert if "confused" emoji rate > 15% over 50+ views

**Edge cases:**
- Time-on-Twin < 5s on average: indicator user skim, not absorb → flag
- Time-on-Twin > 60s on average: indicator user stuck, can't proceed → flag
- Both signals same week: indicator UX broken middle ground

#### Story 4.4 — Twin Delta Distribution Section

**Mô tả:** Show cohort-level distribution of Twin P50 estimates + weekly deltas. Identify bias (e.g., all users showing optimistic delta — math calibration off) or skew (HNW deltas tiny, Starter deltas extreme — threshold miscalibrated).

**Acceptance criteria:**
- API endpoint `GET /api/admin/twin/delta-distribution?days=14&segment=all`
- Histogram of deltas (weekly) + box plot of P50 estimates per segment
- Frontend `TwinDeltaDistribution.jsx` show side-by-side: delta histogram, P50 box plot
- Predictions-vs-actual calibration chart (extends Phase 4.1 B.2 work)

**Edge cases:**
- Cohort too small for distribution: switch to scatter plot showing individual users (anonymized)
- Outliers (single HNW user dragging mean): show median + IQR, not just mean

---

## 📐 Layer Mapping

| Story | Routers | Workers | Handlers | Services | Adapters |
|---|---|---|---|---|---|
| 1.1 Weather rename | — | — | — | `twin_narrative_service` (extend) | — |
| 1.2 Life outcome | — | — | — | `twin_life_outcome_service` (new) | `cost_tracking_adapter` (existing) |
| 1.3 Present anchor | — | — | — | `twin_narrative_service` (extend) | — |
| 2.1 Mascot personification | — | — | `twin_handler` (extend) | `twin_mascot_service` (new) | — |
| 2.2 Story narrative flow | — | — | `twin_handler` (rewrite) | `twin_narrative_flow_service` (new) | Notifier |
| 3.1 On-demand recompute | — | `twin_recompute_worker` (new) | — | `twin_service` (extend) | Event bus, Notifier |
| 3.2 Causality | — | — | — | `twin_causality_service` (new) | — |
| 3.3 Action suggestion | — | — | — | `twin_action_suggestion_service` (new) | — |
| 3.4 Negative delta | — | — | — | (uses 3.2 + 3.3 with content variant) | — |
| 3.5 Delta threshold | — | — | — | `twin_threshold_service` (new) | — |
| 3.6 Return tease | — | `briefing_worker` (extend) | — | `twin_return_tease_service` (new) | Notifier |
| 4.1 Engagement funnel | `/api/admin/twin/engagement-funnel` | — | — | `twin_engagement_funnel_service` (new) | — |
| 4.2 Loop health | `/api/admin/twin/loop-health` | — | — | `twin_loop_health_service` (new) | — |
| 4.3 Comprehension | `/api/admin/twin/comprehension` | — | — | `twin_comprehension_signals_service` (new) | — |
| 4.4 Delta distribution | `/api/admin/twin/delta-distribution` | — | — | `twin_delta_distribution_service` (new) | — |

**Contract checks:**
- `twin_life_outcome_service` PHẢI gọi qua `cost_tracking_adapter` — KHÔNG bypass budget cap
- `twin_recompute_worker` raise domain exception (`TwinComputeError`) — không gọi Telegram trực tiếp
- `twin_threshold_service.is_noticeable()` là pure function — no DB write
- `twin_causality_service.attribute_delta()` no LLM call — pure math
- `twin_action_suggestion_service.suggest()` no LLM call — content yaml lookup
- Toàn bộ Vietnamese string trong `content/*.yaml`. `vi-localization-checker` agent pass mới merge
- Admin dashboard endpoints follow Phase 4.2.5 convention: `/api/admin/twin/*`, JWT auth, audit log

---

## ⚠️ Risk & Rollback

| Risk | Severity | Mitigation | Rollback |
|---|---|---|---|
| Weather metaphor không resonate với user (cảm thấy childish) | Medium | Pre-test với 3-5 friends; A/B với feature flag `WEATHER_VOCABULARY_ENABLED` | Revert to P10/P50/P90 via flag |
| Life outcome translation hallucinate (giá BĐS sai, family status wrong) | High | Template prompt strict + post-validation regex; operator review 10 outputs first week; fallback generic | Disable via flag `LIFE_OUTCOME_ENABLED`; revert to "5.2 tỷ" only |
| LLM cost for life outcome runaway | Medium | Cache key tight (TTL 7 ngày), hit ratio monitor; budget cap via `cost_tracking_adapter` | Throttle: increase cache TTL to 30 ngày, disable real-time translation |
| Mascot personification asset không có designer | Medium | Geometric placeholder variant ship-ready (emoji-based fallback); designer Q3 polish | Disable mascot, weather emoji-only |
| Story narrative flow drop-off ở screen 3-4 (user impatient) | Medium | Measure per-screen drop-off; quick swipe alt via `/twin_quick` command | A/B with feature flag, default to old single-screen if drop > 40% |
| On-demand recompute latency > 5s P95 (Monte Carlo slow) | High | Async + cache user state delta; precompute base case, only delta-compute on demand; queue backpressure | Disable on-demand, fallback to daily snapshot |
| Recompute notification spam (user nhập 5 asset liên tiếp) | Medium | Debounce 10s window, aggregate notification | Increase debounce to 60s |
| Causality breakdown unstable (Monte Carlo variance high) | Medium | Smoothing via 3-week rolling average; confidence threshold 70% | Hide breakdown, show generic "Twin update tích cực/tiêu cực" |
| Action suggestion irrelevant (user already has goal aligned) | Low | Goal-existence check in suggest(); fallback to progress-check variant | Operator manual review suggestions, content yaml fast iteration |
| Negative delta tone hurt user feelings | High | Manual content review 100% of negative templates; operator audit first 20 sends; frequency cap 1/tuần | Disable negative notification entirely, silent track only |
| Negative delta cluster with real-world bad news (lay-off detection wrong) | High | Heuristic detect income absence + manual operator escalation flag; never auto-judge "user lost job" | Disable income-absence heuristic, manual review only |
| Threshold miscalibrated (Starter feel spam, HNW feel silent) | Medium | Default values educated guess; operator command `/twin_threshold_tune` to adjust live; dashboard histogram visual | Reset to single global threshold |
| Return tease feel pushy | Low | Soft language, frequency cap, opt-out via /notify_settings (existing) | Disable tease, only briefing-embedded mention |
| Loop close rate metric inaccurate (definition gaps) | Medium | Definition documented in dashboard spec; operator review 10 sample loops first week | Manual SQL query backup, dashboard metric advisory only |
| Comprehension signals (time-on-Twin) bias by channel (Telegram vs Zalo) | Low | Segment metric by channel; document caveat | N/A (caveat in dashboard) |
| Twin dashboard adds load on backend | Low | Aggregate cache (5-10 min TTL); Redis-backed; query optimization with proper indexes | Disable dashboard endpoints temporarily via Caddy block |
| Migration 4.3.01–04 backfill heavy (twin_view_events seed from past data) | Medium | Backfill optional, run as background job; new events flow into table real-time post-deploy | Skip backfill, accept "data starts from Phase 4.3 ship" |

---

## ✅ Definition of Done

- [ ] Tất cả 15 story (1.1, 1.2, 1.3, 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4) acceptance criteria pass
- [ ] Migration `4.3.01`, `4.3.02`, `4.3.03`, `4.3.04` applied dev + staging
- [ ] Test cases `phase-4.3-test-cases.md` pass với ≥ 95% P0 signed
- [ ] `vi-localization-checker` agent pass — không hardcoded Vietnamese trong code Phase 4.3
- [ ] `layer-contract-checker` agent pass — service không có DB commit, adapter không có business logic
- [ ] **Comprehension test:** 5 non-finance friends/family thử Twin simplified → ≥ 4/5 hiểu "3 weather là gì" trong 60s
- [ ] **Latency test:** 100 on-demand recompute calls trên staging → P95 < 5s, P99 < 8s
- [ ] **Loop close rate test (synthetic):** Trigger 10 fake user actions → measure loop close rate, manual verify ≥ 50% close trong 24h (sẽ thấp hơn với real user nhưng test pipeline)
- [ ] **Negative delta tone review:** Operator + 1 trusted reviewer (não tài chính) approve 5 sample negative messages
- [ ] **Threshold calibration check:** Histogram delta distribution show threshold reasonable cho mỗi segment
- [ ] **Admin dashboard Twin section** load < 3s, 4 charts render correctly với data thực tế
- [ ] **Operator command `/twin_threshold_tune`** test trên staging — value persist + audit log entry
- [ ] **Predictions-vs-actual** chart (extends 4.1 B.2) integrated into Twin dashboard
- [ ] **Story flow drop-off test:** 5 dogfood session through story flow → drop-off per screen logged + acceptable
- [ ] **Life outcome translation cache** hit ratio ≥ 60% sau 1 tuần dogfood
- [ ] **Feature flag `TWIN_V2_ENABLED`** verified in deploy config; default ON for new users post-launch, OFF for users created before phase 4.3 (test với A/B subset)
- [ ] **`docs/current/phase-4.3/`** committed: 4 docs (this file + habit-loop-spec + dashboard-spec + test-cases)
- [ ] **Cost tracking review:** LLM cost from Twin features (life outcome) tracked + below threshold

---

## 🚧 Out of Scope

Phase 4.3 cố tình **không** làm:

- ❌ **Mascot animation** → defer Phase 5.4 (Achievement & Badges). Phase 4.3 static images only
- ❌ **Twin sharing/social viral images** → Phase 4.1 B.1 shipped basic; Twin v2 sharing defer Phase 5+
- ❌ **Twin compare with peer cohort** → defer Phase 5.5 (Behavioral Engine, synthetic cohort)
- ❌ **Twin History Replay** (predictions-vs-actual time-travel UI) → defer Phase 5+; current 4.1 B.2 calibration is read-only
- ❌ **Twin Yearly Review** (Tết feature) → Phase 6 (Tết Special Features)
- ❌ **Twin Conversation** (chat directly with future Twin) → research spike Phase 5+
- ❌ **OCR pipeline for asset entry** → defer Phase 5.x (already deferred Phase 4.2)
- ❌ **Multi-tier admin RBAC** (Phase 4.2.5 already deferred to v2)
- ❌ **Real-time dashboard WebSocket** (Phase 4.2.5 already deferred)
- ❌ **Export Twin data to CSV** → defer Phase 5+
- ❌ **A/B testing framework** → manual feature flag enough for Phase 4.3 cohort (~50 users)
- ❌ **Twin localization other than VN** → only VN in scope
- ❌ **Household Mode Twin** (Couple Twin) → Phase 5.6
- ❌ **Encryption end-to-end** → Phase 5.0 (immediately after Phase 4.3)
- ❌ **Zalo channel activation** → Phase 5.1-5.3
- ❌ **Performance optimization beyond P95 < 5s recompute** → acceptable for cohort 50, optimize later if scale demand

---

## 🧭 Recommendations

1. **Ship Story 1.1 (Weather rename) Day 1.** Đây là foundation cho mọi story sau. Đổi vocabulary giữa chừng = rework cao. Day 1 = `content/twin/weather_vocabulary.yaml` + helper + grep+replace callsites. < 4h work.

2. **Story 1.2 (Life outcome) prompt template phải iterate trước ship.** LLM translation rủi ro hallucinate cao. Dogfood với 20 input variants (different segment × age × city × family) trước ship → tune prompt + post-validation rules. Đầu tư 1 ngày extra ở đây tiết kiệm 1 tuần fix sau.

3. **Story 2.1 (Mascot) — không có designer thì dùng emoji + tone variation.** 3 emoji variant kết hợp text tone đủ MVP. Không block Phase 4.3 vì asset. Polish Phase 5+.

4. **Story 2.2 (Story flow) — measure drop-off per screen.** Add `twin_view_events.current_screen` field. Nếu screen 3-4 drop > 30%, condense flow ngay (kill 1 screen).

5. **Story 3.1 (Recompute) — viết test latency trước implement.** Setup load test với 100 concurrent recompute → measure baseline → optimize until P95 < 5s. Đừng để latency issue lộ ra trong soft launch.

6. **Story 3.2 (Causality) — attribution algorithm là pure math, viết test trước.** 8-10 test case synthetic với expected weights → verify implementation. Bug ở đây = silent wrong attribution → user trust giảm dài hạn.

7. **Story 3.3 (Action suggestion) — content yaml seed 30-40 suggestion variants.** Cohort 50 user × 3 segments × 3 delta directions = 9 buckets cần coverage. Don't skimp on content library.

8. **Story 3.4 (Negative delta) — manual review tone before ship.** Anh + 1 trusted reviewer (không phải dev) đọc tất cả negative templates. Goal: respectful, actionable, no guilt. Bị insensitive ở đây = user churn ngay.

9. **Story 3.5 (Threshold) — default values educated guess, tune sau.** Don't try to find perfect threshold pre-launch. Ship reasonable defaults, expose tuning command, iterate khi có data.

10. **Story 4.1-4.4 (Dashboard) — ship parallel với Epic 3 từ ngày 7.** Backend metrics emit ra từ Epic 3 = dashboard input. Don't block Epic 4 until Epic 3 100% done.

11. **Comprehension test pre-launch là MANDATORY.** Trước ship Phase 4.3, 5 non-finance friends/family test Twin simplified. Không pass = không ship. Đây là Twin's first real test trước cohort.

12. **Feature flag aggressive use.** Mỗi story = 1 flag. Cho phép selective rollout + quick rollback nếu signal xấu sau ship.

---

**Phase 4.3 = ship Twin để user thật sự muốn quay lại, không chỉ thật sự muốn xem lần đầu. Đây là transition từ "có feature" sang "có habit". 💚**
