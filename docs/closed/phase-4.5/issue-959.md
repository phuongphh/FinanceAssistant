# Issue #959

[Epic 1 / Phase 4.5] Shock Simulation + Liquidation Advice ⭐

## Description

Ask trực tiếp của chị Nhung, end-to-end. Layer hội thoại trên Life Event Simulator (Phase 4B): hypothetical MC run + so sánh phương án rút + vẽ lại danh mục. ~70% engine đã có (`simulate_portfolio()`, `LifeEventInjection`).

## Success criteria (Epic-level)

- "Nếu phải chi 100tr thì rút từ đâu?" → so sánh phương án trên chính danh mục user → khuyến nghị thứ tự → redraw.
- 0 persist hypothetical (không LifeEvent row, không đè projection).
- 0 khuyến nghị sản phẩm bên ngoài (ranh giới pháp lý encode trong code).

## Child issues

5 issues — xem chi tiết + DoD trong [`docs/current/phase-4.5/phase-4.5-issues.md`](../blob/main/docs/current/phase-4.5/phase-4.5-issues.md) (Epic E1). Sub-issues sẽ được link bên dưới.

## Dependency

- Chặn bởi **E3 (Độ Nét Meter)** cho answer format hoàn chỉnh (dev song song được, merge answer format sau).
- Ưu tiên: P0 (cột sống của phase). Ước lượng: ~1 tuần. Thứ tự build: sau E3, E2.
