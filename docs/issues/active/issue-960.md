# Issue #960

[Epic 2 / Phase 4.5] Plan-to-Goal Feasibility Q&A

## Description

"100tr → 5 tỷ trong 10 năm?" trả lời thành thật bằng engine. Tái dùng `project_goal_with_savings()` + `FeasibilityBand` (Phase 3.8) — KHÔNG viết lại logic feasibility.

## Success criteria (Epic-level)

- Câu hỏi tự nhiên → band + required monthly + (nếu bất khả thi) mốc gần nhất trong tầm tay.
- Honest-not-harsh: dám nói "gần như bất khả thi" mà 0 câu phán xét.

## Child issues

3 issues — xem chi tiết + DoD trong [`docs/current/phase-4.5/phase-4.5-issues.md`](../blob/main/docs/current/phase-4.5/phase-4.5-issues.md) (Epic E2). Sub-issues sẽ được link bên dưới.

## Dependency

- Chặn bởi **E3 (Độ Nét Meter)** cho answer format hoàn chỉnh.
- Ưu tiên: P0. Ước lượng: ~3 ngày. Thứ tự build: sau E3, trước E1.
