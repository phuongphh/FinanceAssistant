# Issue #982

[Phase 4.6][E1] Onboarding Goal Reset — first-life goals cho segment 22-35

## Epic E1 — Onboarding Goal Reset ⭐

Phase 4.6 (Onboarding Reset cho segment mới). Detail: `docs/current/phase-4.6/phase-4.6-detailed.md` · Issues: `docs/current/phase-4.6/phase-4.6-issues.md`.

Onboarding viết lại cho 22-35 (Level 0→1): goal question dùng milestone đầu đời (quỹ khẩn cấp, mua nhà đầu tiên, cưới) thay framing "quản lý tài sản" vốn không land với người còn đang xây khoản tiết kiệm đầu tiên (Strategy V4 §138-142). Goal set là **content + flag**, không rẽ nhánh code — keyboard build data-driven từ `order` list; flag `ONBOARDING_RESET_ENABLED` off → `step_1_goal` legacy byte-identical.

### Child issues (gộp trong PR bootstrap này)
- **#1.1** Goal code first-life trong model (`GOAL_EMERGENCY_FUND`/`GOAL_FIRST_HOME`/`GOAL_WEDDING`, tuple `LEGACY_GOALS`/`RESET_GOALS`/`ALL_GOALS`, `understand_wealth` giữ đầu cho fallback ổn định, re-export).
- **#1.2** Content `step_1_goal_reset` (order + buttons + goal_acks) cùng `callback_prefix`; legacy thêm `order` list.
- **#1.3** Next-action matrix cho 3 goal reset × 3 asset state (additive, fallback `understand_wealth`).
- **#1.4** Handler + flag `ONBOARDING_RESET_ENABLED` (`is_onboarding_reset_enabled()`, `_goal_step_copy()` + fallback, `_send_goal_question()` data-driven, `_on_goal_picked()`).
- **#1.5** Persona QA + backward compat (prompt-tester goal acks, vi-localization-checker, regression test derive count từ matrix).

### Success criteria
- [ ] Goal question reset hiện 3 goal đầu đời khi flag on; off → `step_1_goal` legacy byte-identical.
- [ ] Goal code reset resolve đủ 3 asset state; goal lạ fallback `understand_wealth` không lỗi.
- [ ] Flag đọc ở handler edge, KHÔNG service; goal code ≤ 32 ký tự (vừa cột `goal_choice`, không cần migration).
- [ ] 0 chuỗi "Decision Engine/CFO/GPS tài chính" user-facing; vi-localization-checker pass.
- [ ] Toàn bộ test xanh; ruff + layer-contract-checker sạch.

