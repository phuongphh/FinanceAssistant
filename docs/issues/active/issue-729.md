# Issue #729

[Story 4] Remove 5-slide intro carousel — Twin Dashboard

## Summary
Remove the 5-slide intro carousel at the top of Twin Dashboard. It provides limited information and doesn't look visually appealing.

## Requirements
- [ ] Remove the 5-slide intro carousel from the top of Twin Dashboard
- [ ] Ensure the rest of the dashboard content still renders correctly
- [ ] No replacement needed — dashboard starts directly with main content
- [ ] If any content from the slides is essential, move it elsewhere; otherwise discard

## Acceptance Criteria
- [ ] 5-slide carousel is removed
- [ ] Dashboard loads directly to main content
- [ ] No regression on other dashboard sections
- [ ] No essential information loss

## Claude Code Implementation Prompt
```
Read issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Remove the 5-slide intro carousel from the top of Twin Dashboard. Dashboard should start directly with main content.

Branch: improve/twin-remove-carousel
PR closes #[ISSUE_NUMBER]
```

