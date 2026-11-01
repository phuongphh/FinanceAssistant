# Issue #168

[Story] P3.6-S8: Update Telegram bot menu button commands

**Parent Epic:** #159 (Epic 2: Adaptive Polish & Integration)

## User Story
As a Telegram user familiar với bot menu button (corner of input area), tôi muốn thấy relevant Bé Tiền commands khi tap — không phải stale commands.

## Acceptance Criteria
- [ ] File `app/bot/setup_commands.py` với `BOT_COMMANDS` list
- [ ] 4 core commands registered:
  - `/start` — "Bắt đầu / Onboarding"
  - `/menu` — "Menu chính"
  - `/help` — "Hướng dẫn sử dụng"
  - `/dashboard` — "Mở Mini App dashboard"
- [ ] Function `setup_bot_commands(bot)` calls `bot.set_my_commands()`
- [ ] Called once on bot startup trong `main.py`
- [ ] Verify trong Telegram: tap menu button → thấy 4 commands
- [ ] Old/deprecated commands removed từ list

## Estimate: ~0.25 day (quick win)
## Depends on: Epic 1 complete (independent)
## Reference: `docs/current/phase-3.6-detailed.md` § 1.5
