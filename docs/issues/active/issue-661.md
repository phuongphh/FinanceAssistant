# Issue #661

[Improve] Expand expense keyword mapping for better NLU

## Summary
Expand the expense keyword mapping in the NLU layer to improve intent recognition accuracy for income and expense transactions.

## Motivation
Bé Tiền currently misses many common Vietnamese keywords that users naturally use for income/expense transactions. Expanding the keyword mapping will significantly improve the chat-first experience.

## Requirements

### Income keywords (→ add money / + income)
- "thêm" → +tiền (add money)
- "cộng" → +tiền (add money)
- "thưởng" → +tiền (bonus/reward — income)
- "được" → +tiền (received — income)
- "nhận" → +tiền (receive — income, already partially implemented)

### Expense keywords (→ subtract money / - expense)
- "tiêu" → -tiền (spend)
- "trừ" → -tiền (subtract)
- "bớt" → -tiền (reduce)
- "giảm" → -tiền (decrease)
- "bỏ" → -tiền (remove)
- "loại" → -tiền (eliminate)

### Additional requirements
- Must not conflict with existing "thêm" = add asset / add goal intent
- Context-aware: "thêm" before "mục tiêu"/"bất động sản" = add goal/asset, but "thêm" before amount = +income
- Handle combined phrases ("được thưởng", "bị trừ", etc.)

## Technical Notes
- NLU keyword mapping configuration
- Priority/weight system for overlapping keywords
- Context-based disambiguation

## Acceptance Criteria
- [ ] All listed keywords are mapped correctly
- [ ] "Thêm 50k" = add 50k income (not add asset)
- [ ] "Bị trừ 100k" = subtract 100k expense
- [ ] "Được thưởng 2tr" = add 2tr income
- [ ] "Thêm bất động sản" still = add asset (context-aware)
- [ ] No conflicts with existing intent mappings

## Claude Code Implementation Prompt
```
Read GitHub issue #661 in phuongphh/FinanceAssistant.

Expand expense keyword mapping for better NLU:

Income keywords → +: thêm, cộng, thưởng, được, nhận
Expense keywords → -: tiêu, trừ, bớt, giảm, bỏ, loại

Requirements:
- Add all keywords to NLU mapping
- Context-aware disambiguation (e.g., "thêm" before asset = add asset, before amount = income)
- Handle compound phrases
- Write tests for each keyword
- No conflicts with existing intents

Guidelines:
- Branch: improve/nlu-keyword-expansion
- Write comprehensive tests
- Conventional commits
- Create draft PR linking to issue #661
```

