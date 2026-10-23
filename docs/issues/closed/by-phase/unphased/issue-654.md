# Issue #654

[Bug] 'Thêm bất động sản' → Bé Tiền show báo cáo thay vì add asset

## Summary
When user types "Thêm bất động sản", Bé Tiền shows real estate report instead of triggering add asset action.

## Actual Behavior
User input: "Thêm bất động sản"
Bé Tiền: shows real estate report
Wrong action triggered.

## Expected Behavior
Bé Tiền should parse:
- Intent: "thêm" = add
- Asset type: "bất động sản" = real estate
→ Action: start add asset flow with type "bất động sản"

## Steps to Reproduce
1. User types "thêm bất động sản"
2. Bé Tiền shows report instead of add flow

## Technical Notes
- NLU layer incorrectly classifies "thêm bất động sản" as a report request instead of add intent
- "thêm" keyword must map to ADD action, not VIEW/REPORT

## Acceptance Criteria
- [ ] "Thêm bất động sản" triggers add asset flow with type real estate
- [ ] "Thêm [asset type]" pattern works for all asset types
- [ ] Report is NOT shown for add-intent queries

## Claude Code Implementation Prompt
```
Read GitHub issue #654 in phuongphh/FinanceAssistant.

Fix: "Thêm bất động sản" should trigger add asset flow, not show report.

Requirements:
- Parse "thêm" as add intent
- Extract asset type from query
- Route to add asset flow with correct type

Guidelines:
- Branch: fix/nlu-add-asset
- Write test for "thêm [asset type]" pattern
- Conventional commits
- Create draft PR linking to issue #654
```

