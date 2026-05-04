# Issue #163

[Story] P3.6-S3: Implement /menu command handler

**Parent Epic:** #158 (Epic 1: Menu Structure & Content)

## User Story
As a user, when I type `/menu`, I expect a clean rich menu to appear immediately so I can navigate to what I want.

## Acceptance Criteria
- [ ] File `app/bot/handlers/menu_handler.py` với `cmd_menu` function
- [ ] Fetches user via UserService
- [ ] Calls `MenuFormatter.format_main_menu()`
- [ ] Sends với `reply_markup` và `parse_mode="Markdown"`
- [ ] Registered trong bot router làm handler cho `/menu` command
- [ ] **Replaces existing /menu handler** (old flat 8-button version retired)
- [ ] Old menu handler archived với comment: `# REMOVED in Phase 3.6 — see menu_handler.py`
- [ ] **Test E2E:** /menu → thấy 5-category menu trong <1 second
- [ ] **Regression:** /start, /help, /add_asset vẫn work

## Estimate: ~0.5 day
## Depends on: P3.6-S2
## Reference: `docs/current/phase-3.6-detailed.md` § 1.4
