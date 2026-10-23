# Issue #69

[P3A-11] Build BriefingFormatter (ladder-aware, personalized)

## Epic
Epic 2 — Morning Briefing | **Week 2** | Depends: P3A-4, P3A-5, P3A-10 | Blocks: P3A-12

## Description
Generate personalized morning briefing dựa trên wealth level + user data. Output phải <800 chars cho mobile.

## Acceptance Criteria
- [ ] Class `BriefingFormatter` với method `generate_for_user(user) -> str`
- [ ] Auto-detect level từ current net worth
- [ ] Render đúng template cho level
- [ ] `_format_net_worth()` — hero section với change emoji (📈/📉)
- [ ] `_format_breakdown()` — asset type breakdown (sort by value desc)
- [ ] `_format_milestone_progress()` cho Starter — next milestone + ETA estimate
- [ ] `_format_cashflow()` cho Mass Affluent — monthly income/expense/net/saving_rate
- [ ] `_format_storytelling_prompt()` — append cuối
- [ ] Edge cases:
  - 0 assets → empty state message
  - Net worth = 0 → không divide by zero
  - Change pct = 0 → "không đổi" (không hiện 0%)
- [ ] Output length <800 chars (mobile screen)
- [ ] Unit tests với mock users cho cả 4 levels

## Estimate
~1.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 2.2
