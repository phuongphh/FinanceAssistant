# Issue #993

[4.6/E4] D28 retention theo cohort (tách segment mới vs legacy)

## Bối cảnh

E4 DoD (`docs/current/phase-4.6/phase-4.6-issues.md:119`) yêu cầu admin analytics phải hiển thị **D28 theo cohort, tách segment mới**, và Strategy G2 đặt mốc **D28 ≥ 25%**. Chart `decision-adoption` hiện tại đo interactions/user + độ nét theo tuần lịch, nhưng **không** trả lời được câu hỏi retention "sau ~28 ngày kể từ lúc đăng ký, bao nhiêu % user còn hoạt động?" — và không tách được segment reset (goal mới) khỏi cohort legacy.

## Mục tiêu

Thêm một chart retention riêng, neo theo **tuần đăng ký** (signup week) của user, bucket theo onboarding cohort:

- `reset` — Segment mới (emergency_fund / first_home / wedding)
- `legacy` — Cohort cũ (understand_wealth / plan_goal / track_spending)
- `unattributed` — Chưa gắn cohort

Headline metric là **D28 = offset tuần thứ 4 (w4, ≈28 ngày)**, để feed gate G2.

## Phạm vi

- Endpoint mới `GET /charts/decision-retention` (read-only, tenant-scoped qua `users.tenant_id`, left-join `onboarding_sessions` lấy `goal_choice`).
- Classic signup→week-N retention: denominator `eligible` co lại theo từng offset (chỉ đếm user đủ tuổi để chạm offset k), nên D28 không bị pha loãng bởi user quá mới. `eligible` được trả ra để audit được con số.
- Schema `DecisionRetentionResponse` / `DecisionRetentionCohort` (aggregate-only, không PII).
- Admin dashboard: bảng "D28 theo cohort" highlight cột D28 (w4), so với mốc G2 25%.
- Unit test đầy đủ cho tenant scoping, cohort bucketing, denominator co lại, D28, cache short-circuit, và no-PII payload.

## DoD

- [ ] Endpoint trả D28 per cohort, tách reset / legacy / unattributed.
- [ ] `eligible` denominator co lại theo offset (D28 không loãng vì user mới).
- [ ] Dashboard hiển thị D28 theo cohort + đối chiếu G2 25%.
- [ ] Unit test xanh, ruff sạch.
