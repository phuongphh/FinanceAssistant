# Issue #642

improve: Hide/show total asset amount with eye button

## Summary
Add ability to hide/show the total asset amount in the Asset menu using an eye toggle button.

## Motivation
Users may want privacy when viewing their total assets in public or shared spaces. A toggle button allows them to quickly mask the amount with asterisks (*) and reveal only when needed.

## Requirements
- [ ] Total asset amount display has a toggle mechanism (hide/show)
- [ ] When hidden, the amount is masked with asterisk characters (*)
- [ ] A button with an eye icon (👁) is placed next to the total amount
- [ ] Clicking the eye button toggles between hidden and visible state
- [ ] The state persists during the current session

## Technical Notes
- Affected file(s): Asset menu UI component
- Use a simple state toggle (local state or session storage)
- Eye icon open/closed for visible/hidden states

## Acceptance Criteria
- [ ] Total asset amount shows as "********" when hidden
- [ ] Eye button click reveals the actual number
- [ ] Clicking again hides it back
- [ ] UI is smooth with no layout shift

## Out of Scope
- Persistent setting across sessions (nice-to-have, not required)
- Hiding individual asset amounts (only total)

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Implement hide/show toggle for total asset amount in Asset menu:
- Add eye button (👁) next to total asset figure
- Toggle between showing actual amount and masked "********"
- Use local state/session storage for toggle state
- Smooth transition between states

Guidelines:
- Branch: improve/asset-amount-toggle
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

