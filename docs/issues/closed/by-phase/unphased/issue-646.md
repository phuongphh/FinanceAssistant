# Issue #646

improve: Change 'Hủy' to 'Quay về menu' in new asset form

## Summary
Change the "Hủy" (Cancel) button in the New Asset form to "Quay về menu" and make it navigate back to the main menu.

## Motivation
The current "Hủy" button is vague — users don't know where it goes. Changing to "Quay về menu" clarifies the action, and the button should actually trigger navigation back to the main menu.

## Requirements
- [ ] Change button text from "Hủy" → "Quay về menu"
- [ ] Button triggers navigation back to the main menu (not just cancel the form)
- [ ] Ensure the navigation works correctly from any step in the form

## Technical Notes
- Affected file(s): New Asset form view
- Button currently cancels/dismisses the form; needs to redirect to main menu

## Acceptance Criteria
- [ ] Button shows "Quay về menu"
- [ ] Clicking returns user to the main menu
- [ ] Works from any stage of the form

## Out of Scope
- Changing appearance/style of the button

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

In the New Asset form:
1. Change foot button text from "Hủy" to "Quay về menu"
2. Change its action from cancel/dismiss to navigate back to main menu
3. Ensure it works from any step in the form

Guidelines:
- Branch: improve/cancel-to-return-button
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

