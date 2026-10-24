# Issue #963

[Epic 5 / Phase 4.5] Decision Query Log + Re-engagement Một Lần

## Description

Ghi log decision queries (nuôi gate G1/G2 — chart là Phase 4.6) + 1 đợt broadcast duy nhất tới cohort dormant khi ship.

## Success criteria (Epic-level)

- Mọi decision query được log với clarity_score.
- Broadcast idempotent, dry-run bắt buộc, chạy đúng MỘT lần.

## Child issues

2 issues — xem chi tiết + DoD trong [`docs/current/phase-4.5/phase-4.5-issues.md`](../blob/main/docs/current/phase-4.5/phase-4.5-issues.md) (Epic E5). Sub-issues sẽ được link bên dưới.

## Dependency

- Chặn bởi E1 + E2 (log cần handler tồn tại); broadcast chặn bởi E1 + E2 + E3 live và migration của E4 (#4.2).
- Ưu tiên: P1 — **chạy CUỐI CÙNG có chủ đích** (one-shot với cohort dormant không được fire trước khi sản phẩm trả lời được "câu này").
- Ước lượng: ~2 ngày.
