# Issue #961

[Epic 3 / Phase 4.5] Độ Nét Meter v1

## Description

Chưa có data completeness score (audit 07/2026: chỉ có `data_quality_warning_type` per-asset). Xây `clarity_service` deterministic + surface trên mọi Twin/decision view. **Build TRƯỚC TIÊN** vì mọi decision answer của E1/E2 bắt buộc kèm độ nét.

## Success criteria (Epic-level)

- Độ nét 0-100 hiện trên Twin Mini App + Twin Telegram view + mọi decision answer.
- Nhập thêm data → độ nét tăng ngay lập tức, nhìn thấy được.
- Dưới ngưỡng tối thiểu → humble mode: trả lời khiêm tốn + nói rõ cần nhập gì.

## Child issues

4 issues — xem chi tiết + DoD trong [`docs/current/phase-4.5/phase-4.5-issues.md`](../blob/main/docs/current/phase-4.5/phase-4.5-issues.md) (Epic E3). Sub-issues sẽ được link bên dưới.

## Dependency

- Không bị chặn bởi ai. **Chặn E1 + E2** (answer format kèm độ nét).
- Ưu tiên: P0 (build đầu tiên). Ước lượng: ~3-4 ngày.
