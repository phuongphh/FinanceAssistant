# Issue #660

[Bug] 'Sửa cổ phiếu FPT thành 200 cổ' → ghi expense sai thay vì edit stock

## Summary
When user types "Sửa cổ phiếu FPT thành 200 cổ", Bé Tiền incorrectly records an expense instead of editing the stock volume.

## Actual Behavior
User input: "Sửa cổ phiếu FPT thành 200 cổ"
Bé Tiền: records expense "sửa cổ phiếu FPT thành 200 cổ" with amount 200 VND
Completely wrong action.

## Expected Behavior
Bé Tiền should parse:
- Intent: "sửa" = edit
- Asset type: "cổ phiếu" = stock
- Asset name: "FPT"
- New volume: "200 cổ" = 200 shares
→ Action: edit stock asset "FPT" volume to 200 shares

## Steps to Reproduce
1. User has stock asset "FPT" with current volume
2. User types "sửa cổ phiếu FPT thành 200 cổ"
3. Bé Tiền records it as expense instead of editing asset

## Technical Notes
- Similar to bug #653 (sửa đất) — "sửa" + asset type + name pattern
- "thành" keyword signals new value/quantity
- "cổ" = shares (context for stock volume)

## Acceptance Criteria
- [ ] "Sửa cổ phiếu FPT thành 200 cổ" → edits FPT stock volume to 200 shares
- [ ] "Sửa [asset_type] [name] thành [value] [unit]" pattern works
- [ ] Is NOT recorded as expense

## Claude Code Implementation Prompt
```
Read GitHub issue #660 in phuongphh/FinanceAssistant.

Fix: "Sửa cổ phiếu FPT thành 200 cổ" should edit stock volume, not record expense.

Requirements:
- Parse "sửa" as edit intent
- Extract asset type (cổ phiếu), asset name (FPT), new volume (200), unit (cổ)
- Edit FPT stock volume to 200 shares
- Must NOT record as expense

Guidelines:
- Branch: fix/nlu-edit-stock
- Write tests for "sửa [type] [name] thành [value] [unit]" pattern
- Conventional commits
- Create draft PR linking to issue #660
```

