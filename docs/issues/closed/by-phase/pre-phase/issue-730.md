# Issue #730

[Story 5] Always show tech detail card + friendly labels — Twin Dashboard

## Summary
Always show the technical detail card (currently hidden behind "Xem kỹ thuật" button). Replace P10/P50/P90 labels with friendly Vietnamese terms. Remove the "Xem kỹ thuật" button entirely.

## Requirements
- [ ] Technical detail card is always visible (no longer behind a button)
- [ ] Replace P10/P50/P90 labels with friendly terms:
  - P10 → "🌧️ Khiêm tốn" (conservative scenario)
  - P50 → "⛅ Bình thường" (normal scenario)
  - P90 → "☀️ Lạc quan" (optimistic scenario)
- [ ] Remove the "Xem kỹ thuật" button entirely
- [ ] Card should integrate naturally into the dashboard flow
- [ ] Ensure the card is positioned well in the content hierarchy

## Acceptance Criteria
- [ ] Technical detail card visible by default
- [ ] Labels use Vietnamese weather vocabulary (Khiêm tốn / Bình thường / Lạc quan)
- [ ] "Xem kỹ thuật" button removed
- [ ] Card integrates naturally into dashboard layout

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Always show technical detail card in Twin Dashboard. Replace P10/P50/P90 with 🌧️ Khiêm tốn / ⛅ Bình thường / ☀️ Lạc quan. Remove "Xem kỹ thuật" button.

Branch: improve/twin-always-show-tech
PR closes #[ISSUE_NUMBER]
```

