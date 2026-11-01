# Issue #648

improve: Reorder guidance in Expense Management — chat-first

## Summary
Reorder the guidance section in Expense Management to move the natural language / chat-with-Bé-Tiền instructions to the top.

## Motivation
The product is chat-first, so the natural language guidance should be the first thing users see in Expense Management — matching the pattern already implemented in Asset Management.

## Requirements
- [ ] Move the "Nói chuyện tự nhiên với Bé Tiền" guidance to the top of the Expense Management screen
- [ ] Keep all existing content, just reorder
- [ ] Match the same format/styling as in Asset Management

## Technical Notes
- Affected file(s): Expense Management view
- Reorder existing UI elements only

## Acceptance Criteria
- [ ] Chat guidance is now the first section in Expense Management
- [ ] All existing content is preserved
- [ ] Layout matches Asset Management pattern

## Out of Scope
- Changing the content of the guidance text

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

In Expense Management view:
1. Move the "Nói chuyện tự nhiên với Bé Tiền" guidance section to the top
2. Keep all existing content in the same order below it
3. Match the styling format used in Asset Management

Guidelines:
- Branch: improve/expense-chat-first
- Reorder only — no content changes
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

