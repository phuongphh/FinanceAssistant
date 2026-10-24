# Issue #652

[Epic] Bugs — NLU parsing failures (8 bugs)

## Summary
Fix 8 critical NLU (Natural Language Understanding) bugs where Bé Tiền fails to understand user queries or responds with incorrect actions.

## Motivation
Bé Tiền frequently fails to correctly parse user intents — either returning "Mình chưa biết câu trả lời này" when it should act, or performing the wrong action (e.g., recording an expense instead of editing an asset). These bugs severely impact the chat-first experience and user trust.

## Issues

### Asset NLU Failures
- [#653](https://github.com/phuongphh/FinanceAssistant/issues/653) [Bug] "Sửa đất ba tư" → Bé Tiền không hiểu là edit asset, trả lời "chưa biết"
- [#654](https://github.com/phuongphh/FinanceAssistant/issues/654) [Bug] "Thêm bất động sản" → Bé Tiền show báo cáo thay vì add asset
- [#659](https://github.com/phuongphh/FinanceAssistant/issues/659) [Bug] "Sửa cổ phiếu FPT thành 200 cổ" → ghi expense sai thay vì edit asset
- [#657](https://github.com/phuongphh/FinanceAssistant/issues/657) [Bug] "TCB 25tr320" → không bắt được số lẻ amount
- [#658](https://github.com/phuongphh/FinanceAssistant/issues/658) [Bug] "Giá vàng hôm nay" → Bé Tiền không query gold price

### Expense/Income NLU Failures
- [#655](https://github.com/phuongphh/FinanceAssistant/issues/655) [Bug] "Chi tiêu dashboard" → show báo cáo thay vì mở Expense Dashboard
- [#656](https://github.com/phuongphh/FinanceAssistant/issues/656) [Bug] "Hôm nay nhận lương 20tr vào tiền mặt" → ghi expense sai thay vì add income to asset

### Goal NLU Failures
- [#660](https://github.com/phuongphh/FinanceAssistant/issues/660) [Bug] "Thêm mục tiêu" → show goals report thay vì add goal

### Enhancement
- [#661](https://github.com/phuongphh/FinanceAssistant/issues/661) [Improve] Expand expense keyword mapping for better NLU

## Acceptance Criteria
- [ ] All 8 bugs are fixed and verified
- [ ] Bé Tiền correctly parses "sửa" + asset type + name → edit asset action
- [ ] Bé Tiền correctly parses "thêm" + asset type → add asset action
- [ ] Bé Tiền correctly parses "chi tiêu dashboard" → open Expense Dashboard
- [ ] Bé Tiền correctly parses "nhận" + income + amount + asset → add income to asset
- [ ] Bé Tiền handles amount with/without decimal correctly
- [ ] Bé Tiền queries DB for "giá vàng hôm nay"
- [ ] Bé Tiền correctly parses "thêm mục tiêu" → add goal
- [ ] Bé Tiền correctly parses "sửa cổ phiếu X thành Y cổ" → edit stock volume
- [ ] Expanded keyword mapping for expense flow (thêm/cộng/thưởng/được = +, tiêu/trừ/bớt/giảm/bỏ/loại = -)

## Out of Scope
- Backend API changes beyond NLU/intent parsing fixes
- UI changes

## Claude Code Implementation Prompt
```
Read GitHub Epic #652 "Bugs — NLU parsing failures" and ALL sub-issues (#653–#661) in phuongphh/FinanceAssistant.

Fix all NLU bugs where Bé Tiền fails to understand user intents. This is critical for the chat-first experience.

Key areas to fix:
1. Intent classification: "sửa" (edit) vs "thêm" (add) vs "chi tiêu" (expense) vs "nhận" (receive)
2. Entity extraction: asset type, asset name, amount (with/without decimals), quantity, currency
3. Action routing: ensure correct action is triggered for each intent
4. Expense keyword mapping: expand keywords (thêm/cộng/thưởng/được = +income, tiêu/trừ/bớt/giảm/bỏ/loại = -expense)
5. "Giá vàng hôm nay" → query gold prices from DB

Guidelines:
- Branch: fix/nlu-parsing-bugs
- Focus on the NLU/intent parsing layer
- Write tests for each bug case
- Conventional commits (fix:, improve:)
- Create draft PR linking to epic #652
```

