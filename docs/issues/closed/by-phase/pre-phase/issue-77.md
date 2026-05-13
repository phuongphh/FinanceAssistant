# Issue #77

[P3A-19] Build storytelling confirmation UI with inline actions

## Epic
Epic 3 — Storytelling Expense | **Week 3** | Depends: P3A-18

## Description
UI để user confirm / edit / cancel list giao dịch extracted từ story. Must be friction-free.

## Acceptance Criteria
- [ ] Inline keyboard: [✅ Đúng hết] [✏️ Sửa] [❌ Bỏ hết]
- [ ] "Đúng hết" → save all với source="storytelling", verified_by_user=True
- [ ] "Bỏ hết" → discard all, clear pending, confirm message
- [ ] "Sửa" → show each transaction individually với [✏️ Sửa] [🗑 Bỏ] [✅ Giữ]
- [ ] Edit transaction: ask what to change (amount / merchant / category)
- [ ] After full confirm: success message với summary (X giao dịch, tổng Xtr)
- [ ] Show net worth impact nếu relevant
- [ ] Clear `pending_transactions` after any terminal action
- [ ] Keyboard disappears after action (edit_message_reply_markup)

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 3.3
