# Issue #659

[Bug] 'Thêm mục tiêu' → Bé Tiền show goals report thay vì add goal

## Summary
When user types "Thêm mục tiêu", Bé Tiền shows goals report instead of triggering add goal flow.

## Actual Behavior
User input: "Thêm mục tiêu"
Bé Tiền: shows goals report
Wrong action triggered.

## Expected Behavior
Bé Tiền should parse:
- Intent: "thêm" = add
- Target: "mục tiêu" = goal
→ Action: start add goal flow

## Steps to Reproduce
1. User types "thêm mục tiêu"
2. Bé Tiền shows goals report instead of add goal flow

## Technical Notes
- Similar to bug #654 (thêm bất động sản) — "thêm" is being classified as view/report instead of add
- Need consistent handling of "thêm" + object pattern

## Acceptance Criteria
- [ ] "Thêm mục tiêu" triggers add goal flow
- [ ] "Thêm [object]" consistently triggers add for all object types

## Claude Code Implementation Prompt
```
Read GitHub issue #659 in phuongphh/FinanceAssistant.

Fix: "Thêm mục tiêu" should trigger add goal flow, not show goals report.

Requirements:
- Parse "thêm mục tiêu" as add goal intent
- Route to add goal flow
- Ensure "thêm" + object consistently maps to ADD intent

Guidelines:
- Branch: fix/nlu-add-goal
- Write tests for "thêm mục tiêu" pattern
- Conventional commits
- Create draft PR linking to issue #659
```

