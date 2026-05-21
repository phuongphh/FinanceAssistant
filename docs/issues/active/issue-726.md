# Issue #726

[Story 1] Fix milestone card color contrast — Twin Dashboard

## Summary
Fix the milestone card color — current gray is hard to read. Replace with a more visible color while keeping the card's visual hierarchy.

## Requirements
- [ ] Change milestone card background/text color from gray to something more readable
- [ ] Ensure contrast ratio meets WCAG AA minimum (4.5:1 for normal text)
- [ ] Keep consistency with Twin Dashboard color palette
- [ ] Test on Telegram iOS, Android, and Web

## Acceptance Criteria
- [ ] Milestone card text is clearly readable
- [ ] Color change is visible but not distracting
- [ ] No regression on other card styles

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Fix milestone card color in Twin Dashboard — replace gray with more visible color while maintaining design consistency. Ensure WCAG AA contrast ratio.

Branch: improve/twin-milestone-color
PR closes #[ISSUE_NUMBER]
```

