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
| # | Title | Issue | Estimate | Depends |
|---|-------|-------|----------|---------|
| 3.1 | On-Demand Twin Recompute | [#679](https://github.com/phuongphh/FinanceAssistant/issues/679) | 1.5d | None |
| 3.2 | Causality Breakdown with Contribution Weights | [#680](https://github.com/phuongphh/FinanceAssistant/issues/680) | 1d | #679 |
| 3.3 | Action Suggestion Embedded in Twin Flow | [#681](https://github.com/phuongphh/FinanceAssistant/issues/681) | 1d | #680 |
| 3.4 | Negative Delta Handling | [#682](https://github.com/phuongphh/FinanceAssistant/issues/682) | 1d | #680, #683 |
| 3.5 | Delta Threshold for Noticeable Change | [#683](https://github.com/phuongphh/FinanceAssistant/issues/683) | 0.5d | #679 |
| 3.6 | Return Tease + Loop Closure | [#684](https://github.com/phuongphh/FinanceAssistant/issues/684) | 1d (P1) | #681 |

### Claude Code Prompt
```
Implement Epic 3 (Phase 4.3) — all 6 stories (#679–#684).
Branch: phase-4.3/epic-3-twin-habit-loop
```

