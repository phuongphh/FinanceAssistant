# Issue #645

improve: Rename 'BĐS cho thuê' to 'Cho thuê BĐS'

## Summary
Rename the foot button label from "BĐS cho thuê" to "Cho thuê BĐS" in the Asset menu.

## Motivation
The current label "BĐS cho thuê" is awkward in Vietnamese. "Cho thuê BĐS" sounds more natural and grammatically correct.

## Requirements
- [ ] Change button text from "BĐS cho thuê" → "Cho thuê BĐS"
- [ ] Keep all other button properties (position, color, size, action)

## Technical Notes
- Affected file(s): Asset menu — foot button configuration
- Text change only, no functional changes

## Acceptance Criteria
- [ ] Button now displays "Cho thuê BĐS"
- [ ] Button still triggers the same action

## Out of Scope
- Changing icon, color, or position of the button

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Rename foot button in Asset menu from "BĐS cho thuê" to "Cho thuê BĐS".

Guidelines:
- Branch: improve/rename-bds-button
- Text change only
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

