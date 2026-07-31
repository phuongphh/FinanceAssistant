# Phase 4.6 — Issues Breakdown

> Onboarding Reset cho segment mới (22-35, Level 0→1). GitHub-ready issue list. Detail: [`phase-4.6-detailed.md`](phase-4.6-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E1 | Onboarding Goal Reset ⭐ | 5 | P0 (cột sống, nền content cho E3) | ~3-4 ngày |
| E2 | Sửa Đường Rơi "Chưa Từng Kích Hoạt" | 2 | P0 | ~2-3 ngày |
| E3 | Decision Moment Trong Onboarding | 3 | P0 | ~3 ngày |
| E4 | Instrumentation Cohort Mới → Dashboard | 2 | P1 | ~2 ngày |

**Tổng:** 4 Epics / 12 issues. Thứ tự build: E1 → E3, E2 song song, E4 sau khi E3 merge.

## 🏷️ Label Conventions
- `phase-4.6`, `epic-1`/`epic-2`/`epic-3`/`epic-4`
- `onboarding-reset` / `activation` / `decision-moment` / `instrumentation`
- `persona-critical` (mọi issue chạm copy Bé Tiền — bắt buộc prompt-tester / vi-localization-checker)

---

## 🅰️ Epic #E1 — Onboarding Goal Reset ⭐

### Description
Onboarding viết lại cho 22-35: goal question dùng milestone đầu đời (quỹ khẩn cấp, mua nhà đầu tiên, cưới) thay framing "quản lý tài sản" vốn không land với người còn đang xây khoản tiết kiệm đầu tiên. Goal set là content + flag, không rẽ nhánh code. **Ship trước** vì E3 (decision moment) gắn vào goal đã chọn.

### Success criteria (Epic-level)
- Goal question reset hiện 3 goal đầu đời khi `ONBOARDING_RESET_ENABLED` on; off → `step_1_goal` legacy byte-identical.
- Goal code reset resolve đủ 3 asset state trong next-action matrix; goal lạ fallback `understand_wealth` không lỗi.
- 0 chuỗi "Decision Engine/CFO/GPS" user-facing; copy nói ngôn ngữ 22-35.

### Child issues

#### Issue #1.1 — Goal code first-life trong model
- `backend/models/onboarding_session.py`: `GOAL_EMERGENCY_FUND`/`GOAL_FIRST_HOME`/`GOAL_WEDDING`; tuple `LEGACY_GOALS`/`RESET_GOALS`/`ALL_GOALS`; giữ `understand_wealth` đầu `ALL_GOALS` để `next(iter(...))` + fallback ổn định. Re-export ở `models/__init__.py`.
- **DoD:** `RESET_GOALS ⊂ ALL_GOALS`, disjoint với `LEGACY_GOALS`; mọi code ≤ 32 ký tự (vừa cột `goal_choice`); test re-export.

#### Issue #1.2 — Content `step_1_goal_reset`
- `content/onboarding/welcome_v2.yaml`: block `step_1_goal_reset` (order + buttons + goal_acks) cùng `callback_prefix` với legacy; legacy `step_1_goal` thêm `order` list để keyboard data-driven.
- **DoD:** order/buttons/goal_acks align đúng `RESET_GOALS`; cùng `callback_prefix`; legacy block không đổi; vi-localization-checker pass.

#### Issue #1.3 — Next-action matrix cho goal reset
- `content/onboarding/next_action.yaml`: ô CTA cho 3 goal reset × 3 asset state (demo / real_no_income / real_with_income). Additive — `compute()` fallback `understand_wealth` nên không bắt buộc về an toàn, nhưng cho copy khớp goal.
- **DoD:** cả 3 goal reset resolve trong cả 3 state; `understand_wealth` anchor còn nguyên mọi state; copy mỗi ô unique.

#### Issue #1.4 — Handler + flag `ONBOARDING_RESET_ENABLED`
- `backend/bot/handlers/onboarding_v2.py`: `is_onboarding_reset_enabled()` đọc env (default `false`); `_goal_step_copy()` chọn reset/legacy + fallback nếu thiếu block reset; `_send_goal_question()` build keyboard từ `order` (fallback `_DEFAULT_GOAL_ORDER`); `_on_goal_picked()` gọi `set_goal()` + render ack. Flag đọc ở handler edge, KHÔNG service.
- **DoD:** `_goal_step_copy` picks legacy khi off / reset khi on / fallback nếu thiếu; env parsing truthy/falsy; `_send_goal_question` build đúng keyboard 2 trường hợp; test flag on/off.

#### Issue #1.5 — Persona QA + backward compat `persona-critical`
- Reset goals resolve đủ; flag off → legacy byte-identical; regression test cũ (vd `test_phase_4_2` matrix count) cập nhật để derive count từ matrix thay vì hardcode.
- **DoD:** prompt-tester goal acks × 3 xưng hô; 0 "Decision Engine/CFO/GPS"; toàn bộ suite onboarding xanh; ruff + layer-contract-checker sạch.

---

## 🅱️ Epic #E2 — Sửa Đường Rơi "Chưa Từng Kích Hoạt"

### Description
Đường rơi lớn nhất cohort 6/2026: user vào bot rồi im — 0 tin nhắn. First message phải tự nổ ra không cần user gõ lời trước. Tái dùng proactive companion (Phase 4.4 E3) làm nền.

### Success criteria (Epic-level)
- User mở bot mà im lặng → Bé Tiền chủ động mở lời (cooldown + quiet hours tôn trọng).
- Đo được tỉ lệ kích hoạt cohort mới.

### Child issues

#### Issue #2.1 — First-message-tự-nổ
- Hook vào proactive companion (Phase 4.4): user mở bot / bấm start mà im → gửi first message. Flag `ACTIVATION_NUDGE_ENABLED` default `false` đọc ở worker/router. Copy ở content YAML.
- **DoD:** test trigger fire cho user im lặng; cooldown + quiet hours giữ nguyên; test flag on/off; vi-localization-checker pass.

#### Issue #2.2 — Đo tỉ lệ kích hoạt
- Tag event "first-message-fired" vs "user-first-reply" để dashboard thấy activation rate cohort mới.
- **DoD:** event ghi đúng 2 phía; feeds E4 chart.

---

## 🅲 Epic #E3 — Decision Moment Trong Onboarding

### Description
Decision moment đầu tiên xảy ra ngay trong onboarding: sau Twin reveal, hỏi 1 câu quyết định gắn goal đã chọn, trả lời được ngay với đúng 1 con số + độ nét thành thật. Tái dùng `plan_feasibility_service` + `clarity_service` (Phase 4.5) — KHÔNG viết engine mới.

### Success criteria (Epic-level)
- 1 câu hỏi quyết định goal-specific, trả lời ngay với data tối thiểu.
- Độ nét thành thật (thường thấp ở onboarding) + gợi ý làm nét — không ép nhập thêm trường.

### Child issues

#### Issue #3.1 — Decision moment gắn goal
- Sau Twin reveal, hỏi 1 câu quyết định theo goal đã chọn; trả lời bằng `plan_feasibility_service` (Phase 4.5) với 1 con số + goal. Flag `ONBOARDING_DECISION_MOMENT_ENABLED` default `false`.
- **DoD:** integration test cho mỗi goal reset; test flag off → onboarding kết ở Twin reveal như cũ.

#### Issue #3.2 — Độ nét thành thật
- Kèm `clarity_service` score + gợi ý làm nét ("ảnh còn mờ, nhưng đây là hướng"); KHÔNG ép nhập thêm trường để trả lời.
- **DoD:** test độ nét thấp vẫn trả lời được; humble copy đúng ngưỡng.

#### Issue #3.3 — Copy + persona QA `persona-critical`
- Copy decision moment onboarding: honest-not-harsh, goal-specific, 0 jargon.
- **DoD:** prompt-tester 3 xưng hô × goal; 0 "Decision Engine/CFO/GPS"; vi-localization-checker pass.

---

## 🅳 Epic #E4 — Instrumentation Cohort Mới → Admin Dashboard

### Description
Đo cohort mới trên admin dashboard (Phase 4.2.5): decision interactions/user/tuần + độ nét trung bình + D28 theo cohort. Feeds gate G1 (~mid-Sept) + G2 (late Oct). `decision_query_log` (Phase 4.5) đã ghi log — 4.6 tag cohort + vẽ.

### Success criteria (Epic-level)
- Dashboard tách segment mới khỏi cohort cũ.
- Số sạch cho G1 (decision adoption) + G2 (D28 ≥ 25% + độ nét avg ≥ 60%).

### Child issues

#### Issue #4.1 — Cohort tag trên decision_query_log
- Gắn cohort onboarding vào `decision_query_log` (Phase 4.5). Migration nếu cần cột `cohort` (chốt trong issue). Ghi qua service flush-only.
- **DoD:** migration sạch (nếu có); log ghi cohort đúng; append-only giữ nguyên.

#### Issue #4.2 — Chart admin dashboard
- Admin dashboard (Phase 4.2.5): decision interactions/user/tuần + độ nét avg active users + D28 theo cohort, tách segment mới.
- **DoD:** chart render đúng số từ `decision_query_log`; JWT auth giữ nguyên; PII mask giữ nguyên.

---

## 🔗 Dependency Graph

```
E1 (goal reset) ──> E3 (decision moment gắn goal đã chọn)
E2 (activation nudge — độc lập, song song E1/E3)
E3 ──> E4 (chart cần data cohort mới đi qua decision moment)
#4.1 (cohort tag) ──> #4.2 (chart)
```

E1 là nền content cứng cho E3. E4 vẽ chart chỉ có ý nghĩa khi cohort mới bắt đầu đi qua onboarding reset + decision moment. E2 độc lập, ship song song.
