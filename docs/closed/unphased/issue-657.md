# Issue #657

[Bug] 'TCB 25tr320' → không bắt được số lẻ amount

## Summary
When user types "TCB 25tr320", Bé Tiền only captures amount as 25tr and ignores the decimal portion (320).

## Actual Behavior
User input: "TCB 25tr320"
Bé Tiền: captures amount = 25,000,000 VND (ignores 320)

## Expected Behavior
Bé Tiền should parse:
- Asset symbol: "TCB"
- Amount: "25,320,000" VND (25tr + 320 = 25,320,000)
→ Full amount with decimal portion captured

## Steps to Reproduce
1. User types "TCB 25tr320"
2. Bé Tiền only captures 25tr, drops "320"

## Technical Notes
- Amount parsing regex/pattern doesn't handle "XtrY" format where Y is the decimal portion
- "25tr320" = 25,320,000 VND (25 triệu 320 nghìn)
- Need to handle "tr" (triệu) suffix with optional decimal/thousand suffix

## Acceptance Criteria
- [ ] "TCB 25tr320" → amount = 25,320,000
- [ ] "VNM 50tr500" → amount = 50,500,000
- [ ] "25tr" → amount = 25,000,000 (still works)
- [ ] "25tr320k" → amount = 25,320,000 (if k suffix also used)

## Claude Code Implementation Prompt
```
Read GitHub issue #657 in phuongphh/FinanceAssistant.

Fix: "TCB 25tr320" should parse full amount including decimal portion (25,320,000).

Requirements:
- Handle "XtrY" amount format where Y is thousands portion
- "25tr320" = 25,000,000 + 320,000 = 25,320,000
- Must not break existing "Xtr" (without decimal) parsing

Guidelines:
- Branch: fix/nlu-amount-decimal
- Write tests for various amount formats
- Conventional commits
- Create draft PR linking to issue #657
```

