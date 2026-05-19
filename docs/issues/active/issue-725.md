# Issue #725

[Epic] Enhance Twin Dashboard — UI/UX Improvements

## Summary
UI/UX improvements for the Twin Dashboard: fix color contrast issues, improve readability of suggestion text, fix spacing, remove low-value intro slides, and always show technical details with friendly labels.

## Motivation
Dogfooding feedback highlights several UI pain points in the Twin Dashboard: gray milestone card lacks contrast, suggestion text blends in, uneven spacing in uncertainty card, the 5-slide intro carousel adds friction without value, and the "Xem kỹ thuật" button creates unnecessary tapping. These fixes make the dashboard cleaner and more readable.

## Issues
- [#725](https://github.com/phuongphh/FinanceAssistant/issues/725) Fix milestone card color contrast
- [#726](https://github.com/phuongphh/FinanceAssistant/issues/726) Bold/colorize suggestion text in Current vs Optimal card
- [#727](https://github.com/phuongphh/FinanceAssistant/issues/727) Fix uniform spacing in Main Uncertainty Source card
- [#728](https://github.com/phuongphh/FinanceAssistant/issues/728) Remove 5-slide intro carousel
- [#729](https://github.com/phuongphh/FinanceAssistant/issues/729) Always show tech detail card with friendly labels, remove button

## Acceptance Criteria
- [ ] Milestone card has visible, readable color (not gray)
- [ ] Suggestion text in Current vs Optimal card is bold/colorized for visibility
- [ ] Main Uncertainty Source card has uniform line spacing
- [ ] 5-slide intro carousel removed from Twin Dashboard top
- [ ] Technical detail card always visible with friendly labels replacing P10/P50/P90
- [ ] "Xem kỹ thuật" button removed
- [ ] No regression on Twin Dashboard functionality

## Out of Scope
- Twin logic changes (UI only)
- New features or data additions

## Claude Code Implementation Prompt
```
Read Epic #[EPIC_NUMBER] and all sub-issues (#725-#729) in phuongphh/FinanceAssistant.

Implement UI/UX improvements for Twin Dashboard:
1. Fix milestone card color (replace gray with more visible color)
2. Bold/colorize suggestion text in Current vs Optimal card
3. Fix uniform spacing in Main Uncertainty Source card
4. Remove 5-slide intro carousel from top of Twin Dashboard
5. Always show tech detail card, replace P10/P50/P90 with friendly labels, remove "Xem kỹ thuật" button

Guidelines:
- Branch: improve/twin-dashboard-ui-ux
- UI changes only — no logic changes
- Vietnamese labels for technical terms (use existing weather vocabulary: 🌧️ Khiêm tốn / ⛅ Bình thường / ☀️ Lạc quan)
- Conventional commits
- Create draft PR linking to epic #[EPIC_NUMBER]
```

