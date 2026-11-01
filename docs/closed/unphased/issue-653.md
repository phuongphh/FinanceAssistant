# Issue #653

[Bug] 'Sửa đất ba tư' → Bé Tiền không hiểu là edit asset

## Summary
When user types "Sửa đất ba tư", Bé Tiền responds "Mình chưa biết câu trả lời này" instead of performing edit asset action.

## Actual Behavior
User input: "Sửa đất ba tư"
Bé Tiền response: "Mình chưa biết câu trả lời này"
No action taken.

## Expected Behavior
Bé Tiền should parse:
- Intent: "sửa" = edit
- Asset subtype: "đất" = Land
- Asset name: "ba tư"
→ Action: open edit flow for asset named "ba tư" with subtype "Đất"

## Steps to Reproduce
1. User has an asset named "ba tư" with subtype "Đất"
2. User types "sửa đất ba tư"
3. Bé Tiền fails to recognize the edit intent and asset reference

## Technical Notes
- NLU/intent parsing layer in Finance Assistant bot
- Likely missing: "sửa" keyword mapping for edit-intent, combined asset subtype + name extraction

## Acceptance Criteria
- [ ] "Sửa đất ba tư" correctly triggers edit action for asset "ba tư" (Đất)
- [ ] "Sửa" is recognized as edit intent for all asset types
- [ ] Format "sửa [subtype] [name]" is handled correctly

## Claude Code Implementation Prompt
```
Read GitHub issue #653 in phuongphh/FinanceAssistant.

Fix: "Sửa đất ba tư" should trigger edit asset action, not "chưa biết câu trả lời".

Requirements:
- Parse "sửa" as edit intent
- Extract asset subtype (đất) and asset name (ba tư)
- Open edit flow for the matched asset

Guidelines:
- Branch: fix/nlu-edit-asset
- Write test for "sửa [subtype] [name]" pattern
- Conventional commits
- Create draft PR linking to issue #653
```

