# Issue #989

[Phase 4.6][E4] Instrumentation cohort mới → Admin dashboard — cohort tag + chart decision adoption

## Epic E4 — Instrumentation Cohort Mới → Admin Dashboard

Phase 4.6 (Onboarding Reset cho segment mới). Detail: `docs/current/phase-4.6/phase-4.6-detailed.md` · Issues: `docs/current/phase-4.6/phase-4.6-issues.md`.

Đo cohort mới trên admin dashboard (Phase 4.2.5): decision interactions/user/tuần + độ nét trung bình + D28 theo cohort. Feeds gate G1 (~mid-Sept) + G2 (late Oct). `decision_query_log` (Phase 4.5) đã ghi log — 4.6 **tag cohort** + **vẽ chart**. E3 (#985) đã merge nên E4 build được.

### Child issues (gộp trong PR này)

- **#4.1** Cohort tag trên `decision_query_log`: thêm cột `cohort VARCHAR(16) NULL` + index (migration down_revision `20260710dqlog45`); cohort onboarding derive từ `onboarding_sessions.goal_choice` — `RESET_GOALS` → `reset` (segment mới 22-35), `LEGACY_GOALS` → `legacy`, còn lại `NULL`. Pure classifier `cohort_for_goal()` trong model, re-export ở `models/__init__.py`; `log_query()` nhận thêm param `cohort` (flush-only). Thread cohort qua 3 call site: onboarding decision moment (free từ `session.goal_choice`), shock + feasibility handler (view-only resolver `resolve_user_cohort`). Append-only giữ nguyên.
- **#4.2** Chart admin dashboard (Phase 4.2.5): endpoint `/api/admin/charts/decision-adoption?weeks=N` đọc `decision_query_logs` — theo tuần × cohort: interactions (số dòng), active_users (distinct user), interactions/user, độ nét avg. Pydantic schema mới; JWT auth (`Depends(get_current_admin)`) giữ nguyên; PII mask giữ nguyên (output aggregate-only, 0 PII). Frontend wiring `betien-admin/src/`.

### Success criteria
- [ ] Migration sạch (down_revision `20260710dqlog45`); log ghi cohort đúng; append-only giữ nguyên.
- [ ] Cohort derive đúng: reset goals → `reset`, legacy goals → `legacy`, goal lạ/NULL → `NULL`.
- [ ] `cohort` param flush-only trong service; flag/env KHÔNG đọc trong service/formatter.
- [ ] Chart render đúng số từ `decision_query_log`, tách segment mới khỏi cohort cũ.
- [ ] JWT auth giữ nguyên; PII mask giữ nguyên (aggregate-only, 0 PII rò rỉ).
- [ ] Toàn bộ test xanh; ruff + layer-contract-checker sạch.
