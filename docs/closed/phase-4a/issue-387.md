# Issue #387

[Story] P4A-S13: PNG cone chart renderer

**Parent Epic:** #371 (Epic 3: Telegram Twin Surface)

## Description
Matplotlib renders cone (shaded P10-P90, line P50). Watermark + Vietnamese labels.

## Acceptance Criteria
- [ ] render_cone_chart(cone, optimal=None, width=800, height=600) → bytes
- [ ] VND formatted (tỷ / triệu)
- [ ] Watermark "Bé Tiền — dự phóng, không phải dự đoán"
- [ ] Perf: < 500ms p95
- [ ] Golden image test with fixed fixture
- [ ] Chart adapter is ONLY layer touching matplotlib

## Estimate: ~1 day
## Dependencies: P4A-S4

Close #371
