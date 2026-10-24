# Issue #658

[Bug] 'Giá vàng hôm nay' → Bé Tiền không query gold price

## Summary
When user types "Giá vàng hôm nay", Bé Tiền responds "Mình chưa biết câu trả lời này" instead of querying gold prices from the database.

## Actual Behavior
User input: "Giá vàng hôm nay"
Bé Tiền response: "Mình chưa biết câu trả lời này"
No DB query executed.

## Expected Behavior
Bé Tiền should:
- Parse "giá vàng hôm nay" as gold price query
- Query the database for today's gold prices
- Return gold price information to user

## Steps to Reproduce
1. User types "giá vàng hôm nay"
2. Bé Tiền doesn't recognize the query, returns generic response

## Technical Notes
- Missing NLU pattern for "giá [asset] hôm nay" queries
- Need to add gold price query intent
- Should query gold asset prices from DB

## Acceptance Criteria
- [ ] "Giá vàng hôm nay" triggers DB query for gold prices
- [ ] "Giá [kim loại] hôm nay" pattern works for other metals
- [ ] Result displays current gold price data

## Claude Code Implementation Prompt
```
Read GitHub issue #658 in phuongphh/FinanceAssistant.

Fix: "Giá vàng hôm nay" should query gold prices from DB, not respond "chưa biết".

Requirements:
- Parse "giá vàng hôm nay" as gold price query intent
- Query DB for gold asset prices
- Return formatted gold price information

Guidelines:
- Branch: fix/nlu-gold-price
- Add "giá [asset] hôm nay" pattern
- Write tests
- Conventional commits
- Create draft PR linking to issue #658
```

