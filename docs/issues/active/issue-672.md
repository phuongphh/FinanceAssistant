# Issue #672

[Epic 3] Twin Habit Loop — Phase 4.3

## 📌 Epic 3: Twin Habit Loop

**Phase:** 4.3 | **Estimate:** 6 days | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Epic 1, Epic 2

### Goal
Convert Twin từ static viewer thành habit loop: user action → Twin recompute < 5s → causality explanation → action suggestion → user execute → Twin update → user return next day. Loop close rate ≥ 20% trong 7 ngày.

### Description
Đây là Epic dài nhất và risk nhất Phase 4.3. 6 stories implement đầy đủ loop: Recompute infra (loop trigger), Causality (vòng 1 — trust), Action (vòng 2 — reward + setup next loop), Negative handling (honest moment), Threshold (signal vs noise), Return tease (loop closure).

### Success Criteria
- [ ] On-demand recompute P95 latency < 5s end-to-end
- [ ] Causality breakdown user-tested: ≥ 70% user trả lời đúng "tại sao Twin thay đổi"
- [ ] Action suggestion completion rate ≥ 30% trong 48h
- [ ] Negative delta notification: 0 user complaint về tone trong founding cohort
- [ ] Loop close rate (trigger → view → action → return) ≥ 20% trong 7 ngày

### Stories
- **3.1** On-Demand Twin Recompute (1.5d, P0, no deps)
- **3.2** Causality Breakdown with Contribution Weights (1d, P0, depends on 3.1)
- **3.3** Action Suggestion Embedded in Twin Flow (1d, P0, depends on 3.2)
- **3.4** Negative Delta Handling (1d, P0, depends on 3.2, 3.5)
- **3.5** Delta Threshold for Noticeable Change (0.5d, P0, depends on 3.1)
- **3.6** Return Tease + Loop Closure (1d, P1, depends on 3.3)

