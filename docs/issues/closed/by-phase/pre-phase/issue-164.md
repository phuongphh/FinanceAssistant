# Issue #164

[Story] P3.6-S4: Implement menu callback router

**Parent Epic:** #158 (Epic 1: Menu Structure & Content)

## User Story
As a user navigating the menu, khi tôi tap "💎 Tài sản", tôi muốn menu transition smoothly sang sub-menu mà không spam new messages.

## Acceptance Criteria
- [ ] Function `handle_menu_callback(update, context)` trong menu_handler.py
- [ ] Registered làm `CallbackQueryHandler` cho pattern `^menu:`
- [ ] Parse callback format: `menu:{category}` hoặc `menu:{category}:{action}`
- [ ] **Top-level navigation** (`menu:main`, `menu:assets`):
  - Dùng `query.edit_message_text()` (KHÔNG phải new message)
  - Edit in-place cho smooth UX
- [ ] **"Quay về"** (`menu:main`): return về main menu via edit
- [ ] **Action callbacks** (`menu:assets:net_worth`): route tới handler (S5, S6)
- [ ] Unimplemented actions: show "🚧 Coming soon" message
- [ ] **Luôn gọi** `query.answer()` đầu tiên để dismiss loading spinner
- [ ] Wrap edit trong try/except (Telegram throws nếu message không edit được)

## Test E2E (manual)
1. /menu → see main
2. Tap Tài sản → main becomes sub-menu (CÙNG bubble)
3. Tap Quay về → về main (CÙNG bubble)
4. Verify chat history chỉ có 1 menu bubble (không phải nhiều)

## Estimate: ~1 day
## Depends on: P3.6-S3
## Reference: `docs/current/phase-3.6-detailed.md` § 1.4
