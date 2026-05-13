# Issue #28

[Phase 1 - Week 2] Inline Keyboard System for Transactions

## User Story
As a user, I want to be able to edit, delete, or change the category of a transaction with a single tap — without typing any commands.

## Background
Phase 1 - Week 2. Every transaction message should come with action buttons.

## Tasks
- [ ] Create `app/bot/keyboards/common.py`
  - Define `CallbackPrefix` constants
  - `parse_callback(data)` → `(prefix, args)`
  - `build_callback(prefix, *args)` with 64-byte validation
- [ ] Create `app/bot/keyboards/transaction_keyboard.py`
  - `transaction_actions_keyboard(tx_id)` → [🏷 Đổi danh mục] [✏️ Sửa] [🗑 Xóa] + [↶ Hủy (5s)]
  - `category_picker_keyboard(tx_id)` → 2-column grid of all categories + ❌ Hủy
  - `confirm_delete_keyboard(tx_id)` → [✅ Xóa] [❌ Không]
- [ ] Create `app/bot/handlers/callbacks.py`
  - Main router: `handle_callback(update, context)`
  - `handle_change_category` (2-step flow: show picker → update DB → edit message)
  - `handle_delete_transaction` (show confirm dialog)
  - `handle_confirm_action` (execute delete)
  - `handle_cancel_action` (remove keyboard)
  - `handle_undo_transaction` (5-second window only)
- [ ] Update `app/bot/handlers/transaction.py` to attach keyboard after every transaction creation
- [ ] Register callback handler in bot setup

## Acceptance Criteria
- [ ] After logging a transaction, 4 action buttons appear
- [ ] Tapping "Đổi danh mục" shows category picker (2-column grid)
- [ ] Selecting a new category updates the message in-place
- [ ] Tapping "Xóa" shows confirmation dialog before deleting
- [ ] "↶ Hủy (5s)" works within 5 seconds, shows alert if too late
- [ ] Callback data never exceeds 64 bytes (Telegram limit)
- [ ] Unit tests for `parse_callback` and `build_callback`

## Reference
`docs/strategy/phase-1-detailed.md` — Sections 2.1 – 2.4
