# Phase 4.6 — Onboarding Reset cho segment mới

> Onboarding đổi khán giả: từ "quản lý tài sản" (nói với người đã có tài sản) → "lo cho xong chuyện tiền đầu đời" (nói với 22-35, Level 0→1). Sửa đường rơi "chưa từng kích hoạt", đưa decision moment đầu tiên vào ngay trong onboarding, và bắt đầu đo cohort mới trên admin dashboard.

**Status:** 📝 Planning
**Duration:** ~2 tuần (target: August 2026)
**Branch:** `claude/phase-4-6-implementation-eg0g1a`
**Strategy:** [`docs/current/strategy.md`](../strategy.md) — Strategy V4 §Roadmap Phase 4.6 (§138-142) + §Success Metrics/Gates (G1/G2)
**Issues:** [`phase-4.6-issues.md`](phase-4.6-issues.md)

---

## 📋 Changelog vs Strategy V4

| Strategy V4 nói | Phase doc này cụ thể hoá | Ghi chú |
|---|---|---|
| Onboarding viết lại cho 22-35: goal đầu đời (quỹ khẩn cấp, cưới, mua nhà đầu tiên) thay vì "quản lý tài sản" | Epic E1: goal question mới `step_1_goal_reset` với 3 goal code first-life (`emergency_fund`/`first_home`/`wedding`), keyboard build data-driven từ `order` list, flag `ONBOARDING_RESET_ENABLED` | Legacy `step_1_goal` giữ nguyên; flag off → byte-identical hành vi cũ |
| Sửa đường rơi "chưa từng kích hoạt" (nhiều user 0 tin nhắn trong cohort 6/2026) | Epic E2: first message tự nổ ra sau khi user bấm start / mở bot lần đầu — không cần user gõ lời trước; tái dùng proactive companion (Phase 4.4 E3) làm nền | Không xây scheduler mới; hook vào trigger empathy có sẵn |
| Decision moment đầu tiên xảy ra **trong onboarding** (một câu hỏi quyết định thật, trả lời được ngay với data tối thiểu + độ nét thành thật) | Epic E3: sau khi có 1 con số tài sản, hỏi 1 câu quyết định gắn với goal đã chọn; tái dùng `plan_feasibility_service` + `clarity_service` (Phase 4.5) | KHÔNG viết engine mới — layer onboarding trên decision service 4.5 |
| Instrumentation: decision interactions/user/tuần + độ nét trung bình + D28 theo cohort → admin dashboard | Epic E4: chart từ `decision_query_log` (Phase 4.5 đã ghi) + cohort tag onboarding; lên admin dashboard (Phase 4.2.5) | 4.5 ghi log; 4.6 vẽ — đúng như 4.5 out-of-scope đã hẹn |

---

## 🧠 Design Philosophy

1. **Đổi khán giả bằng content + flag, không rẽ nhánh trong code.** Goal set là một `order` list trong content YAML; handler build keyboard từ list đó. Thêm/bớt goal = sửa YAML, không sửa handler. Flag `ONBOARDING_RESET_ENABLED` off → render `step_1_goal` cũ nguyên trạng.
2. **Không bao giờ bỏ rơi user giữa chừng.** `_goal_step_copy()` fallback về `step_1_goal` nếu block reset thiếu — flag không thể làm user kẹt. Mọi goal code mới đều backward-safe: `next_action_service.compute()` fallback về ô `understand_wealth` cho goal lạ.
3. **First message phải tự nổ.** Đường rơi lớn nhất của cohort 6/2026 là "0 tin nhắn" — user vào bot rồi im. E2 đảm bảo Bé Tiền chủ động mở lời, không chờ user gõ trước.
4. **Decision moment ≠ thêm bước nhập liệu.** Câu hỏi quyết định trong onboarding trả lời được với đúng 1 con số + goal — độ nét thành thật (~thấp) là feature, không phải lỗi. "Ảnh còn mờ, nhưng đây là hướng" tốt hơn ép nhập 5 trường rồi mới trả lời.
5. **Đo cohort mới từ ngày đầu.** Mọi user đi qua onboarding reset được tag cohort; dashboard tách segment mới khỏi cohort cũ để gate G2 (D28 ≥ 25%) có số sạch.
6. **User-facing không bao giờ nói "Decision Engine"/"CFO"/"GPS tài chính".** Copy dùng *người đồng hành* / *quản lý tài sản*; goal đầu đời nói bằng ngôn ngữ đời sống (quỹ khẩn cấp, mua nhà, cưới), không jargon tài chính.

---

## 🎬 Choreography — flow onboarding reset

| Bước | Surface | Nội dung |
|---|---|---|
| 1 | User bấm start | Intro + hỏi tên → salutation (nguyên trạng Phase 4.4) |
| 2 | Bé Tiền | **Goal question mới:** "Điều gì bạn muốn lo cho xong trước nhất về chuyện tiền?" → 3 nút first-life (quỹ khẩn cấp / mua nhà đầu tiên / cưới) |
| 3 | Bé Tiền | Ack ấm theo goal ("Có một khoản phòng thân là bước vững vàng đầu tiên…") → trust card / first asset prompt |
| 4 | User | Nhập 1 con số tài sản (hoặc demo) → Twin reveal (nguyên trạng) |
| 5 | Bé Tiền | **Decision moment (E3):** 1 câu hỏi quyết định gắn goal đã chọn, trả lời ngay bằng `plan_feasibility_service` + **độ nét thành thật** + gợi ý làm nét thêm |
| 6 | Nền (E2) | Nếu user im lặng sau khi mở bot → first message tự nổ qua proactive companion (không chờ user gõ) |
| — | Admin (E4) | Mọi decision interaction + độ nét + cohort onboarding chảy vào `decision_query_log` → chart trên admin dashboard |

---

## 📁 Files Touched

| File | Loại | Ghi chú |
|---|---|---|
| `backend/models/onboarding_session.py` | ✏️ Sửa | +goal code `emergency_fund`/`first_home`/`wedding`; `LEGACY_GOALS`/`RESET_GOALS`/`ALL_GOALS` tuples; `understand_wealth` giữ đầu tiên để `next(iter(ALL_GOALS))` + fallback ổn định |
| `backend/models/__init__.py` | ✏️ Sửa | Re-export goal code + tuple mới |
| `content/onboarding/welcome_v2.yaml` | ✏️ Sửa | Block `step_1_goal_reset` (order + buttons + goal_acks), cùng `callback_prefix`; legacy `step_1_goal` thêm `order` list |
| `content/onboarding/next_action.yaml` | ✏️ Sửa | Ô CTA cho 3 goal reset × 3 asset state (additive; fallback về `understand_wealth`) |
| `backend/bot/handlers/onboarding_v2.py` | ✏️ Sửa | Flag `ONBOARDING_RESET_ENABLED` + `is_onboarding_reset_enabled()`; `_goal_step_copy()`; `_send_goal_question()` build keyboard từ `order`; `_on_goal_picked()` |
| `backend/services/onboarding/onboarding_service.py` | ♻️ Tái dùng | `set_goal()` validate qua `ALL_GOALS` — nhận goal reset không đổi code |
| `backend/services/onboarding/next_action_service.py` | ♻️ Tái dùng | `compute()` fallback `understand_wealth` cho goal lạ — backward-safe |
| `backend/services/decision/plan_feasibility_service.py` | ♻️ Tái dùng | Decision moment onboarding (Phase 4.5) |
| `backend/services/decision/clarity_service.py` | ♻️ Tái dùng | Độ nét thành thật cho decision moment (Phase 4.5) |
| `backend/services/empathy/*` (proactive companion) | ✏️ Sửa | E2: first-message-tự-nổ hook (nền Phase 4.4 E3) |
| `backend/models/decision_query_log.py` | ♻️ Tái dùng | E4: cohort tag onboarding cho log (Phase 4.5) |
| `admin dashboard (frontend + api)` | ✏️ Sửa | E4: chart decision interactions/user/tuần + độ nét avg + D28 theo cohort |
| `tests/test_phase_4_6/*` | ✨ Mới | Unit + content + handler; persona + vi-localization gate |

**Số tiền:** mọi amount hiển thị/lưu DB dùng `Decimal` + `format_money_short/full` (nguyên tắc chung, không đổi).

---

## 🗄️ New DB Columns / Tables

| Đối tượng | Cột | Kiểu | Ghi chú |
|---|---|---|---|
| `onboarding_session` | `goal_choice` | `VARCHAR(32)` (đã có) | Chứa được goal code reset dài nhất (`emergency_fund` = 14 ký tự); không cần migration mới cho E1 |
| `decision_query_log` | `cohort` (E4) | `VARCHAR` NULL | Tag cohort onboarding để tách segment mới — chi tiết chốt ở issue E4 |

> Epic E1 (goal reset) **không cần migration**: `goal_choice` đã là `String(32)`, dài hơn mọi goal code mới. E2/E3/E4 migration (nếu có) chốt trong issue tương ứng.

---

## 📦 Epics & Stories

### Epic E1 — Onboarding Goal Reset ⭐ *(cột sống — ship trước, đã implement)*

- **1.1** Goal code first-life trong model: `GOAL_EMERGENCY_FUND`/`GOAL_FIRST_HOME`/`GOAL_WEDDING`; `LEGACY_GOALS`/`RESET_GOALS`/`ALL_GOALS`; giữ `understand_wealth` đầu `ALL_GOALS` cho fallback ổn định. Re-export ở `models/__init__.py`.
- **1.2** Content `step_1_goal_reset` (order + buttons + goal_acks) cùng `callback_prefix` với legacy; legacy `step_1_goal` thêm `order` list để keyboard data-driven.
- **1.3** `next_action.yaml`: ô CTA cho 3 goal reset × 3 asset state (additive — `compute()` fallback `understand_wealth` cho goal lạ nên không bắt buộc về mặt an toàn).
- **1.4** Handler: flag `ONBOARDING_RESET_ENABLED` (`is_onboarding_reset_enabled()`), `_goal_step_copy()` chọn reset/legacy + fallback nếu thiếu block, `_send_goal_question()` build keyboard từ `order`, `_on_goal_picked()` render ack + route.
- **1.5** Test + persona QA: reset goals resolve đủ 3 asset state; flag on/off byte-identical legacy khi off; 0 chuỗi "Decision Engine/CFO/GPS"; vi-localization-checker pass.

### Epic E2 — Sửa Đường Rơi "Chưa Từng Kích Hoạt"

- **2.1** First message tự nổ: sau khi user mở bot / bấm start mà im lặng, Bé Tiền chủ động mở lời — không chờ user gõ trước. Tái dùng proactive companion (Phase 4.4 E3) + cooldown + quiet hours có sẵn.
- **2.2** Đo hiệu quả: tag event "first-message-fired" vs "user-first-reply" để dashboard thấy tỉ lệ kích hoạt cohort mới. Flag `ACTIVATION_NUDGE_ENABLED` default `false`.

### Epic E3 — Decision Moment Trong Onboarding

- **3.1** Sau Twin reveal, hỏi 1 câu quyết định gắn goal đã chọn (vd goal `first_home` → "Với nhịp hiện tại, bao lâu nữa bạn đủ cọc nhà đầu tiên?"). Trả lời ngay bằng `plan_feasibility_service` (Phase 4.5) với đúng 1 con số + goal.
- **3.2** Độ nét thành thật: kèm `clarity_service` score (thường thấp ở onboarding) + gợi ý làm nét — "ảnh còn mờ, nhưng đây là hướng". KHÔNG ép nhập thêm trường để mới trả lời. Flag `ONBOARDING_DECISION_MOMENT_ENABLED` default `false`.
- **3.3** Copy + persona QA `persona-critical`: honest-not-harsh; goal-specific; 0 jargon.

### Epic E4 — Instrumentation Cohort Mới → Admin Dashboard

- **4.1** Cohort tag: gắn cohort onboarding vào `decision_query_log` (Phase 4.5 đã ghi log) để tách segment mới.
- **4.2** Chart admin dashboard (Phase 4.2.5): decision interactions/user/tuần + độ nét trung bình active users + D28 theo cohort. Feeds gate G1 (~mid-Sept) + G2 (late Oct).

---

## 🏗️ Layer Mapping

| Layer | Thành phần Phase 4.6 |
|---|---|
| `routers/` / `workers/` | Đọc feature flags (`ONBOARDING_RESET_ENABLED`, …); không đổi gì khác |
| `bot/handlers/` | `onboarding_v2.py` — route goal pick + decision moment, format response, KHÔNG business logic, KHÔNG `db.commit()`; flag đọc ở edge |
| `services/` | `onboarding_service.set_goal()` (validate qua `ALL_GOALS`), `decision/*` (tái dùng), empathy proactive — flush-only |
| `content/` | `welcome_v2.yaml`, `next_action.yaml` — 0 chuỗi tiếng Việt hardcode trong code |
| `admin (frontend + api)` | E4 chart — read-only từ `decision_query_log` |

---

## ⚠️ Risk & Rollback

| Flag (env) | Default | Đọc ở | Tắt thì |
|---|---|---|---|
| `ONBOARDING_RESET_ENABLED` | `false` | handler | Render `step_1_goal` legacy — byte-identical hành vi cũ |
| `ACTIVATION_NUDGE_ENABLED` | `false` | worker/handler | Không có first-message-tự-nổ (như hiện tại) |
| `ONBOARDING_DECISION_MOMENT_ENABLED` | `false` | handler | Onboarding kết ở Twin reveal, không hỏi decision (như hiện tại) |

- Mỗi flag có test on/off (convention từ 4.4/4.5). Flag đọc ở handler/router/worker, KHÔNG trong service.
- **Rollback E1:** goal reset chỉ là content + flag; tắt flag là sạch. Goal code lạ đã backward-safe (`compute()` fallback `understand_wealth`) nên user đã pick goal reset không lỗi kể cả sau khi tắt flag.
- **Rollback E2:** tắt flag → không gửi nudge; không data cần dọn.
- **Rollback E3:** decision moment không persist gì đặc biệt (chỉ ghi `decision_query_log` append-only); tắt flag là sạch.
- **Risk positioning:** copy goal đầu đời phải nói ngôn ngữ 22-35, không jargon — persona QA gate bắt buộc (prompt-tester + vi-localization-checker) cho mọi issue chạm copy.

---

## ✅ Definition of Done

- [ ] Goal question reset hiện 3 goal đầu đời khi flag on; flag off → `step_1_goal` legacy byte-identical.
- [ ] Goal code reset resolve đủ 3 asset state trong next-action matrix; goal lạ fallback `understand_wealth` không lỗi.
- [ ] First message tự nổ cho user im lặng sau khi mở bot (E2); đo được tỉ lệ kích hoạt cohort mới.
- [ ] Decision moment trong onboarding trả lời được với đúng 1 con số + goal, kèm độ nét thành thật + gợi ý làm nét (E3).
- [ ] Admin dashboard tách cohort mới: decision interactions/user/tuần + độ nét avg + D28 (E4).
- [ ] 3 flags có test on/off; tắt hết → onboarding y hệt trước 4.6.
- [ ] 0 chuỗi "Decision Engine"/"GPS tài chính"/"CFO" trong user-facing copy (vi-localization-checker).
- [ ] Persona gates pass: prompt-tester cho goal acks + decision moment × 3 xưng hô.
- [ ] Toàn bộ test xanh; ruff + layer-contract-checker sạch.

---

## 🚫 Out of Scope (đã có nhà)

- **Decision engine mới** → Phase 4.5 (4.6 chỉ layer onboarding trên engine 4.5).
- **Guardian / scam check / drift warnings** → Phase 4.7.
- **Zalo onboarding surface** → Phase 5.0-5.1.
- **Monetization / paywall onboarding** → Phase 5.7.
- **Household / couple onboarding** → parked (segment 22-35 chưa cần).

---

## 🔀 Execution Order (đề xuất)

```
E1 (goal reset — nền content + flag, ship trước, đã implement)
 └─> E3 (decision moment — cần goal reset + decision service 4.5)
E2 (activation nudge — độc lập, song song được với E1/E3)
E4 (instrumentation — chảy từ khi E3 merge; chart cần data cohort mới)
```

E1 ship trước vì nó là điều kiện tiên quyết content cho E3 (decision moment gắn goal đã chọn) và không phụ thuộc gì. E4 vẽ chart chỉ có ý nghĩa khi cohort mới bắt đầu đi qua onboarding reset.

---

*Tạo 11/07/2026 — kickoff Phase 4.6 theo Strategy V4 §138-142. E1 (goal reset) implement trong PR đầu; E2/E3/E4 theo sau.*
