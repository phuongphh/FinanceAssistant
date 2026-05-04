# Phase 3.6 — GitHub Issues (Epics + User Stories)

> **Purpose:** 3 Epics chứa 13 User Stories — sẵn sàng copy-paste vào GitHub.  
> **Format:** Epic = issue cha có task list link tới Stories. Stories = issue con với AC chi tiết.  
> **Reference:** Mỗi story link về [phase-3.6-detailed.md](./phase-3.6-detailed.md)

---

## 📊 Overview

| Epic | Tuần | Stories | Goal |
|------|------|---------|------|
| Epic 1: Menu Structure & Content | 1 | 6 stories | Build 3-level menu hierarchy with 5 categories |
| Epic 2: Adaptive Polish & Integration | 1 (cuối) | 4 stories | Wealth-level adaptive copy + handler routing |
| Epic 3: Migration & Quality Assurance | 2 (1/2) | 3 stories | Hard cutover deploy + user testing |

**Total:** 13 user stories across 3 epics, ~1.5-2 weeks of work.

---

## 🏷️ GitHub Labels

Reuse existing labels từ phase trước, thêm:

**Phase 3.6 specific:**
- `phase-3.6` (color: pink)
- `epic` (existing)
- `story` (existing)
- `menu-ux` (specific area)
- `content` (cho YAML copy work)

---

## 🔗 GitHub Configuration

Same workflow như Phase 3.5:

1. Create 3 Epic issues first → note numbers
2. Create 13 Story issues with Parent Epic reference
3. Edit Epic bodies → fill in story numbers in task list
4. Project Board: same columns as Phase 3.5

---

# Epic 1: Menu Structure & Content

> **Type:** Epic | **Phase:** 3.6 | **Week:** 1 | **Stories:** 6

## Overview

Build the foundational 3-level menu hierarchy với 5 main categories (Tài sản, Chi tiêu, Dòng tiền, Mục tiêu, Thị trường), complete content YAML, formatter, và navigation handlers. By end of Epic 1, user can /menu and navigate full hierarchy without errors — but adaptive descriptions and migration come in later Epics.

## Why This Epic Matters

Menu cũ là **expense-tracker era artifact** — flat 8 buttons với "Quét Gmail" deprecated. Menu mới reflects Personal CFO positioning với wealth-first hierarchy. Epic 1 builds the structural foundation; everything else depends on it.

## Success Definition

When Epic 1 is complete:
- ✅ /menu shows 5-category main menu
- ✅ Tap each category → sub-menu with 4-5 actions
- ✅ Tap action → trigger handler or navigate to wizard
- ✅ "◀️ Quay về" buttons work consistently
- ✅ Edit message in place (no spam new messages)
- ✅ All 5 sub-menus have hint about free-form alternative

## Stories in this Epic

> Replace `#XXX` with actual issue numbers after creating GitHub issues.

- [ ] #XXX [Story] P3.6-S1: Create menu copy YAML with all 5 categories
- [ ] #XXX [Story] P3.6-S2: Build MenuFormatter with basic (non-adaptive) intros
- [ ] #XXX [Story] P3.6-S3: Implement /menu command handler
- [ ] #XXX [Story] P3.6-S4: Implement menu callback router
- [ ] #XXX [Story] P3.6-S5: Wire menu actions to existing handlers (assets, expenses)
- [ ] #XXX [Story] P3.6-S6: Wire remaining menu actions (cashflow, goals, market)

## Out of Scope (for Epic 1)

- ❌ Wealth-level adaptive intros — Epic 2
- ❌ Migration from old menu — Epic 3
- ❌ User testing — Epic 3

## Dependencies

- ✅ Phase 3A complete (provides asset wizards, OCR, etc.)
- ✅ Phase 3.5 complete (provides intent handlers reused by menu actions)

## Reference

📖 [phase-3.6-detailed.md § Tuần 1](./phase-3.6-detailed.md)

### Labels
`phase-3.6` `epic` `menu-ux` `priority-high`

---

## [Story] P3.6-S1: Create menu copy YAML with all 5 categories

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** None

### Reference
📖 [phase-3.6-detailed.md § 1.2 — Content File](./phase-3.6-detailed.md)

### User Story

As a content owner, I need all menu text stored in editable YAML so that copy refinement based on user feedback doesn't require code deploys.

### Acceptance Criteria

- [ ] File `content/menu_copy.yaml` exists
- [ ] **Main menu section** with:
  - Title variations for 4 wealth levels
  - Intro for 4 wealth levels (placeholder support: `{name}`)
  - 5 buttons: 💎 Tài sản, 💸 Chi tiêu, 💰 Dòng tiền, 🎯 Mục tiêu, 📊 Thị trường
  - Hint section with 3 example free-form queries
- [ ] **5 sub-menus**, each with:
  - Title (with emoji + uppercase category name)
  - 4-level adaptive intros (starter, young_prof, mass_affluent, hnw)
  - 4-5 action buttons + 1 "◀️ Quay về" button
  - Each button has: label, callback (e.g., `menu:assets:net_worth`), description
  - Hint with 3 example free-form queries specific to category
- [ ] All buttons have **callback_data ≤ 64 characters** (Telegram limit)
- [ ] All button labels ≤ 16 characters (mobile readability)
- [ ] All intros ≤ 200 words (avoid Telegram message length issues)
- [ ] YAML loads without syntax errors

### Implementation Notes

- Categories order matters: Tài sản FIRST (wealth-first positioning)
- Use `{name}` placeholder for personalization
- Adaptive intros differ in **language complexity + tone**, not content
- Buttons remain **identical across levels** (consistency)

### Test Plan

```python
def test_yaml_loads():
    config = load_menu_copy()
    assert "main_menu" in config
    assert len(config["main_menu"]["buttons"]) == 5

def test_all_callbacks_under_64_chars():
    config = load_menu_copy()
    for menu in config.values():
        if "buttons" in menu:
            for b in menu["buttons"]:
                assert len(b["callback"]) <= 64

def test_all_levels_present():
    config = load_menu_copy()
    for submenu_key in ["submenu_assets", "submenu_expenses", ...]:
        intros = config[submenu_key]["intro"]
        assert "starter" in intros
        assert "hnw" in intros
```

### Definition of Done

- YAML file complete and valid
- Loads via test helper
- 4 levels present in every adaptive section
- Button limits verified

### Labels
`phase-3.6` `story` `content` `priority-critical`

---

## [Story] P3.6-S2: Build MenuFormatter with basic intros

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.6-S1

### Reference
📖 [phase-3.6-detailed.md § 1.3 — Menu Formatter](./phase-3.6-detailed.md)

### User Story

As a developer building menu logic, I need a formatter class that loads YAML and produces Telegram InlineKeyboardMarkup objects so that menu rendering is centralized and consistent.

### Acceptance Criteria

- [ ] File `app/bot/formatters/menu_formatter.py` with `MenuFormatter` class
- [ ] Method `format_main_menu(user) -> tuple[str, InlineKeyboardMarkup]`:
  - Loads YAML once on init
  - Builds text: title + intro + hint
  - Builds keyboard: 2-column grid for 5 main buttons (last button alone in last row)
  - Returns text + keyboard
  - **Note:** This story uses **basic (non-adaptive) intro** — defaults to `young_prof` level. Epic 2 makes it adaptive.

- [ ] Method `format_submenu(user, category: str) -> tuple[str, InlineKeyboardMarkup]`:
  - Loads sub-menu config by category name
  - Builds text: title + intro + hint
  - Builds keyboard: 1-column vertical layout
  - Last button is "◀️ Quay về" with callback `menu:main`

- [ ] Both methods support `parse_mode="Markdown"` formatting
- [ ] Error handling: unknown category raises ValueError

### Implementation Notes

- Use placeholder substitution: `intro.format(name=user.display_name or "bạn")`
- Use `InlineKeyboardButton` and `InlineKeyboardMarkup` from `python-telegram-bot`
- Cache YAML on init (don't reload on every call)
- Make formatter stateless after init (thread-safe)

### Test Plan

```python
async def test_format_main_menu():
    user = MockUser(display_name="Hà")
    text, keyboard = await formatter.format_main_menu(user)
    assert "Hà" in text
    assert "💎 Tài sản" in text or any("Tài sản" in b.text for row in keyboard.inline_keyboard for b in row)
    assert len(keyboard.inline_keyboard) >= 3  # at least 3 rows for 5 buttons in 2-col grid

async def test_format_submenu_assets():
    text, keyboard = await formatter.format_submenu(user, "assets")
    assert "TÀI SẢN" in text
    # Last button must be "Quay về"
    assert "Quay về" in keyboard.inline_keyboard[-1][0].text
```

### Definition of Done

- Formatter renders both menu types
- Tests pass with mock user
- Markdown formatting works in real Telegram message

### Labels
`phase-3.6` `story` `backend` `priority-critical`

---

## [Story] P3.6-S3: Implement /menu command handler

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~0.5 day | **Depends on:** P3.6-S2

### Reference
📖 [phase-3.6-detailed.md § 1.4 — Menu Handler](./phase-3.6-detailed.md)

### User Story

As a user, when I type `/menu`, I expect a clean rich menu to appear immediately so I can navigate to what I want.

### Acceptance Criteria

- [ ] File `app/bot/handlers/menu_handler.py` with `cmd_menu` function
- [ ] Function fetches user via UserService
- [ ] Calls MenuFormatter.format_main_menu()
- [ ] Sends as new message with `reply_markup` and `parse_mode="Markdown"`
- [ ] Registered in bot router as handler for `/menu` command
- [ ] **Replaces existing /menu handler** (old flat 8-button version retired)
- [ ] Old menu handler code archived with comment: `# REMOVED in Phase 3.6 (DD/MM/YYYY) — see menu_handler.py`

- [ ] **Test E2E:** Send /menu → see new 5-category menu within 1 second
- [ ] **Regression test:** /start, /help, /add_asset still work unchanged

### Implementation Notes

- Singleton pattern: instantiate MenuFormatter once at module level
- Don't worry about wealth-level adaptive yet (Epic 2)
- Don't migrate old callbacks yet (Epic 3)

### Definition of Done

- /menu command works end-to-end
- Response time <1 second
- No regression in other commands

### Labels
`phase-3.6` `story` `backend` `priority-critical`

---

## [Story] P3.6-S4: Implement menu callback router

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.6-S3

### Reference
📖 [phase-3.6-detailed.md § 1.4 — Menu Handler](./phase-3.6-detailed.md)

### User Story

As a user navigating the menu, when I tap a category button (e.g., "💎 Tài sản"), I expect the menu to smoothly transition to that sub-menu without spamming new messages in chat.

### Acceptance Criteria

- [ ] Function `handle_menu_callback(update, context)` in menu_handler.py
- [ ] Registered as CallbackQueryHandler for pattern `^menu:`
- [ ] Parses callback data format: `menu:{category}` or `menu:{category}:{action}`
- [ ] **Top-level navigation** (`menu:main` or `menu:assets`):
  - Use `query.edit_message_text()` (NOT new message)
  - Edits in place for smooth UX
  - Render appropriate menu via formatter

- [ ] **"Quay về" navigation** (`menu:main`):
  - Returns to main menu via edit
  - Doesn't push new message

- [ ] **Action callbacks** (`menu:assets:net_worth`, etc.):
  - Routes to appropriate action handler (Stories S5, S6)
  - For unimplemented actions: show "🚧 Coming soon" message

- [ ] **Always call** `query.answer()` first to dismiss loading spinner

- [ ] **Test:**
  - Tap "💎 Tài sản" → main menu replaced by sub-menu (same message)
  - Tap "◀️ Quay về" → back to main menu (same message)
  - Multiple navigations don't create new messages
  - Unknown callback shows graceful message

### Implementation Notes

- Use `query.edit_message_text()` instead of `update.message.reply_text()`
- Wrap edit in try/except — Telegram throws if message not edited
- Be careful: `parse_mode` must be set on edit too

### Test Plan

E2E test in real Telegram (manual):
1. /menu → see main
2. Tap Tài sản → main becomes sub-menu (same bubble)
3. Tap Quay về → sub becomes main again
4. Tap Chi tiêu → main becomes Chi tiêu sub
5. Verify chat history shows only 1 menu bubble (not 5)

### Definition of Done

- 3-level navigation works smoothly
- Edit-in-place verified visually
- All callbacks handled (or graceful coming-soon)

### Labels
`phase-3.6` `story` `backend` `priority-critical`

---

## [Story] P3.6-S5: Wire menu actions for Tài sản and Chi tiêu

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.6-S4

### Reference
📖 [phase-3.6-detailed.md § 1.4 — Menu Handler `_route_action`](./phase-3.6-detailed.md)

### User Story

As a user tapping "📊 Tổng tài sản" inside the Tài sản sub-menu, I expect the bot to show me my actual net worth — not just navigate me deeper into menus.

### Acceptance Criteria

- [ ] **Tài sản category actions** wired:
  - `menu:assets:net_worth` → reuse Phase 3.5 `QueryAssetsHandler`
  - `menu:assets:report` → show 30-day report (reuse existing report logic from Phase 3A)
  - `menu:assets:add` → trigger asset wizard from Phase 3A
  - `menu:assets:edit` → trigger edit asset wizard
  - `menu:assets:advisor` → reuse Phase 3.5 `AdvisoryHandler` with context "rebalance my portfolio"

- [ ] **Chi tiêu category actions** wired:
  - `menu:expenses:add` → start text expense entry flow
  - `menu:expenses:ocr` → prompt user to send receipt photo
  - `menu:expenses:report` → reuse Phase 3.5 `QueryExpensesHandler`
  - `menu:expenses:by_category` → trigger category breakdown view

- [ ] **No duplicate logic:** Each action reuses existing handler/wizard
- [ ] **State management:** When triggering wizard from menu, set wizard state correctly
- [ ] **Test:** Tap each of 9 actions → verify expected flow starts

### Implementation Notes

- For "Add asset", may need adapter: existing wizard expects `Update`, callback gives `CallbackQuery`. Build small adapter.
- For "OCR", just send instruction message: "Gửi ảnh hóa đơn cho mình nhé 📷". User then sends image via Telegram normally.
- For "Edit asset", show list of assets first, user picks one to edit.
- For "Advisor", route to existing AdvisoryHandler with synthesized query like "tư vấn tối ưu portfolio của tôi".

### Definition of Done

- All 9 actions work end-to-end
- No duplicate code (DRY with Phase 3.5)
- Tests pass for each action

### Labels
`phase-3.6` `story` `backend` `priority-high`

---

## [Story] P3.6-S6: Wire menu actions for Dòng tiền, Mục tiêu, Thị trường

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.6-S4

### User Story

As a user exploring the new "Dòng tiền" and "Mục tiêu" categories I haven't seen before, I expect each action to lead to useful information — not error messages.

### Acceptance Criteria

- [ ] **Dòng tiền category** (4 actions):
  - `menu:cashflow:overview` → reuse Phase 3.5 `QueryCashflowHandler`
  - `menu:cashflow:income` → reuse Phase 3.5 `QueryIncomeHandler`
  - `menu:cashflow:compare` → show 6-month income vs expense chart (text-based for now, Mini App link for visual)
  - `menu:cashflow:saving_rate` → calculate and show monthly saving rate %

- [ ] **Mục tiêu category** (4 actions):
  - `menu:goals:list` → reuse Phase 3.5 `QueryGoalsHandler`
  - `menu:goals:add` → trigger add-goal wizard (may need to build if not in Phase 3A)
  - `menu:goals:update` → list goals, user picks one to update progress
  - `menu:goals:advisor` → AdvisoryHandler with "lộ trình mục tiêu" context

- [ ] **Thị trường category** (5 actions):
  - `menu:market:vnindex` → reuse Phase 3.5 `QueryMarketHandler` with ticker=VNINDEX
  - `menu:market:stocks` → list user's owned stocks + watchlist (if any)
  - `menu:market:crypto` → top 5 crypto prices (BTC, ETH, etc.)
  - `menu:market:gold` → SJC + PNJ gold prices
  - `menu:market:advisor` → AdvisoryHandler with "cơ hội đầu tư mới" context

- [ ] **Test:** All 13 actions tested end-to-end

### Implementation Notes

- "Add goal" wizard may not exist yet — if not, **Phase 3.6 ships with stub** ("Tính năng đang phát triển, dùng tính năng cũ tạm nhé") and creates issue for Phase 4
- "Watchlist" may not exist yet — show "feature coming soon" if needed
- Market handlers may rely on Phase 3B services — if 3B not complete, use stub data with note

### Definition of Done

- All 13 actions handle gracefully (real data OR coming-soon message)
- No silent failures
- All sub-menus reachable and explorable

### Labels
`phase-3.6` `story` `backend` `priority-high`

---

# Epic 2: Adaptive Polish & Integration

> **Type:** Epic | **Phase:** 3.6 | **Week:** 1 (cuối) | **Stories:** 4

## Overview

Add wealth-level adaptive intros to elevate menu from "functional" to "personalized". Update Telegram bot menu button (corner) with command list. Verify menu integrates well with existing flows (wizards, intent pipeline, free-form queries).

## Why This Epic Matters

Epic 1 ships a working menu, but it doesn't feel "smart". Adaptive intros are what make Bé Tiền seem to **know who's using it**. Same query "💎 Tài sản" produces different intros for Minh (Starter) vs Anh Tùng (HNW) — small but powerful UX touch.

## Success Definition

When Epic 2 is complete:
- ✅ All 4 wealth levels show distinct intros for each menu screen
- ✅ Bot menu button (Telegram corner) shows updated command list
- ✅ Menu coexists with free-form queries (no conflicts)
- ✅ All Phase 3A wizards still work after menu integration

## Stories in this Epic

- [ ] #XXX [Story] P3.6-S7: Add wealth-level detection to MenuFormatter
- [ ] #XXX [Story] P3.6-S8: Update Telegram bot menu button commands
- [ ] #XXX [Story] P3.6-S9: Verify menu + free-form coexistence
- [ ] #XXX [Story] P3.6-S10: Run regression tests on existing flows

## Dependencies

- ✅ Epic 1 complete

## Reference

📖 [phase-3.6-detailed.md § 2.1 — Wealth Level Test Matrix](./phase-3.6-detailed.md)

### Labels
`phase-3.6` `epic` `personality` `priority-high`

---

## [Story] P3.6-S7: Add wealth-level detection to MenuFormatter

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** Epic 1 complete

### Reference
📖 [phase-3.6-detailed.md § 1.3 — Adaptive logic](./phase-3.6-detailed.md)

### User Story

As a Starter user, I want the menu to feel encouraging and educational. As an HNW user, I want it to feel professional and respectful. The same buttons should look the same, but the intro and tone should adapt to my wealth level.

### Acceptance Criteria

- [ ] Update `MenuFormatter.format_main_menu()` to:
  - Call `NetWorthCalculator().calculate(user.id)` to get total
  - Call `detect_level(total)` from Phase 3.5 ladder logic
  - Use level value to lookup correct intro from YAML
  - Format intro with `name=user.display_name`

- [ ] Update `MenuFormatter.format_submenu()` similarly

- [ ] **Visual test (manual):** Run /menu for 4 personas, screenshot all 4 main menus + 5 sub-menus = 24 screenshots total
- [ ] **All screenshots stored** in `tests/test_menu/visual/` for comparison

- [ ] **Verify:**
  - Starter Minh sees "Trợ lý tài chính" + encouraging intro
  - Mass Affluent Phương sees "Trợ lý CFO cá nhân" + professional intro
  - HNW Anh Tùng sees "Personal CFO của anh/chị" + advisor-level intro
  - Buttons identical across all 4 levels

- [ ] **Performance:** Wealth-level detection adds <100ms to menu render

### Implementation Notes

- Cache wealth level per user for short period (5 min) to avoid re-calculating on every menu interaction
- If `NetWorthCalculator` fails (e.g., no assets), fall back to `young_prof` level
- Don't expose wealth_level in menu UI — it's silent personalization

### Test Plan

```python
async def test_starter_intro():
    user = mock_user_minh()  # 17tr net worth
    text, _ = await formatter.format_main_menu(user)
    assert "Trợ lý tài chính" in text
    assert "Trợ lý CFO" not in text

async def test_hnw_intro():
    user = mock_user_anh_tung()  # 13 tỷ
    text, _ = await formatter.format_main_menu(user)
    assert "Personal CFO" in text
```

### Definition of Done

- 4-level adaptive working
- 24 screenshots captured
- Performance acceptable
- No buttons differ across levels

### Labels
`phase-3.6` `story` `personality` `priority-high`

---

## [Story] P3.6-S8: Update Telegram bot menu button commands

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.25 day | **Depends on:** Epic 1 complete

### Reference
📖 [phase-3.6-detailed.md § 1.5 — Update Bot Menu Button](./phase-3.6-detailed.md)

### User Story

As a Telegram user familiar with bot menu button (corner of input area), I want to see relevant Bé Tiền commands when I tap it — not stale or missing commands.

### Acceptance Criteria

- [ ] File `app/bot/setup_commands.py` with `BOT_COMMANDS` list
- [ ] 4 core commands registered:
  - `/start` — "Bắt đầu / Onboarding"
  - `/menu` — "Menu chính"
  - `/help` — "Hướng dẫn sử dụng"
  - `/dashboard` — "Mở Mini App dashboard"

- [ ] Function `setup_bot_commands(bot)` calls `bot.set_my_commands()`
- [ ] Called once on bot startup (in `main.py` or equivalent)
- [ ] Verify in Telegram: tap menu button (corner) → see 4 commands listed
- [ ] Old/deprecated commands removed from list

### Implementation Notes

- This is Telegram-native feature, not custom UI
- Commands list updates may take 1-2 minutes to propagate in Telegram clients
- After deploy, restart Telegram app to see updates immediately

### Definition of Done

- 4 commands visible in bot menu button
- Tapping each command works
- Stale commands removed

### Labels
`phase-3.6` `story` `integration` `quick-win`

---

## [Story] P3.6-S9: Verify menu + free-form coexistence

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.5 day | **Depends on:** P3.6-S7

### User Story

As a user who knows about both menu and free-form queries (Phase 3.5), I want to use either at any time without conflicts. Tapping menu shouldn't break my ability to type a question, and typing a question shouldn't dismiss my menu.

### Acceptance Criteria

- [ ] **Test scenario 1 — Menu open, then type:**
  - Open /menu → main menu visible
  - Without tapping menu, send free-form text "tài sản của tôi có gì?"
  - **Expected:** Bot answers query in new message, menu remains visible above
  - Old menu message NOT auto-deleted

- [ ] **Test scenario 2 — Type then menu:**
  - Send "tài sản của tôi có gì?" → bot replies
  - Send /menu → main menu appears below
  - **Expected:** Both messages coexist, no error

- [ ] **Test scenario 3 — Menu while wizard active:**
  - Start /add_asset wizard
  - Mid-wizard, send /menu
  - **Expected:** Either:
    - **(a)** Bot says "Bạn đang trong wizard, hủy trước khi mở menu?" with confirm
    - **(b)** Menu opens normally, wizard state preserved (user can resume by responding to wizard message)
  - **NOT acceptable:** Wizard silently lost or menu errors

- [ ] **Test scenario 4 — Old callback graceful:**
  - If old menu callbacks (`menu_old:*`) hit (e.g., user has stale message), respond with redirect: "Menu đã được nâng cấp! Mở /menu để xem giao diện mới"
  - Don't crash on unknown callback

- [ ] Document chosen behavior for scenario 3 in code comments

### Implementation Notes

- Free-form queries use `MessageHandler`, menu uses `CommandHandler` and `CallbackQueryHandler` — they don't conflict by Telegram's design
- Wizard state stored in `context.user_data` — preserved across messages

### Definition of Done

- All 4 scenarios behave gracefully
- No exceptions raised
- Documented behavior committed

### Labels
`phase-3.6` `story` `integration` `priority-high`

---

## [Story] P3.6-S10: Run regression tests on existing flows

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.5 day | **Depends on:** P3.6-S5, P3.6-S6, P3.6-S9

### User Story

As a user who relies on existing features (asset wizards, OCR, briefing, storytelling), I expect them all to keep working after the menu revamp — not be broken by the new navigation.

### Acceptance Criteria

Run manual regression suite covering:

- [ ] **Asset wizards:** /add_asset works for cash, stock, real_estate, crypto, gold (5 wizards)
- [ ] **OCR receipt:** Send receipt photo → extracts data
- [ ] **Storytelling:** Tap "💬 Kể chuyện" in briefing → multi-transaction extract works
- [ ] **Morning briefing:** 7 AM trigger fires correctly
- [ ] **Onboarding:** New user /start → completes Phase 2 onboarding
- [ ] **Free-form queries (Phase 3.5):** All 11 canonical queries still work
- [ ] **Voice queries:** Voice → transcribe → intent → handle
- [ ] **Mini App dashboard:** Tap Dashboard button → loads correctly

For each flow:
- Test with 2 personas (Minh + Phương)
- Document any issues found
- Fix or escalate before Epic 3 ships

### Implementation Notes

- Regression test sheet: copy from Phase 3.5 (`phase-3.5-test-cases.md` § Section 4.1)
- Estimate: ~3 hours manual testing for both personas

### Definition of Done

- All 8+ flows verified working
- Sign-off doc committed
- Zero blockers for Epic 3

### Labels
`phase-3.6` `story` `testing` `regression` `priority-critical`

---

# Epic 3: Migration & Quality Assurance

> **Type:** Epic | **Phase:** 3.6 | **Week:** 2 (1/2) | **Stories:** 3

## Overview

Execute hard cutover migration: pre-announce → deploy → post-announce → user test → cleanup. By end of Epic 3, the new menu is live for all users, old menu code archived, and user feedback collected.

## Why This Epic Matters

Phase 3.6 success depends on **smooth deploy**. Users currently rely on old menu — even though it's outdated, switching could disorient. Hard cutover with announcement minimizes confusion. User testing 24-48h post-deploy catches issues early.

## Success Definition

When Epic 3 is complete:
- ✅ New menu live for 100% users
- ✅ Old menu code archived (not deleted)
- ✅ Pre-announcement + post-announcement messages sent
- ✅ ≥3 users tested new menu, feedback positive
- ✅ Documentation updated (CLAUDE.md, strategy.md, README)

## Stories in this Epic

- [ ] #XXX [Story] P3.6-S11: Prepare and execute hard cutover deploy
- [ ] #XXX [Story] P3.6-S12: User testing with 3 users post-deploy
- [ ] #XXX [Story] P3.6-S13: Cleanup, archive, and documentation updates

## Dependencies

- ✅ Epic 1 + Epic 2 complete

## Reference

📖 [phase-3.6-detailed.md § 2.2 — Migration Strategy](./phase-3.6-detailed.md)

### Labels
`phase-3.6` `epic` `migration` `priority-critical`

---

## [Story] P3.6-S11: Prepare and execute hard cutover deploy

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1 day | **Depends on:** Epic 2 complete

### Reference
📖 [phase-3.6-detailed.md § 2.2 — Migration Strategy](./phase-3.6-detailed.md)

### User Story

As a product owner, I want the menu revamp to ship cleanly with clear user communication so that users feel informed about the change rather than surprised.

### Acceptance Criteria

- [ ] **Pre-deploy checklist completed:**
  - Old menu code commented (not deleted) with date stamp
  - Old callbacks (`menu_old:*`) gracefully redirect to new
  - Analytics event `menu_revamp_deployed` configured
  - Rollback plan documented (single git revert + redeploy command)
  - Smoke test script ready: 1 query each category

- [ ] **Pre-deploy announcement** sent to all users (1 day before deploy):
  ```
  📢 Bé Tiền sắp được nâng cấp giao diện mới!
  
  Menu sẽ rõ ràng hơn với 5 mảng:
  💎 Tài sản • 💸 Chi tiêu • 💰 Dòng tiền • 🎯 Mục tiêu • 📊 Thị trường
  
  Cập nhật vào ngày mai 7h sáng. Mọi tính năng vẫn còn — 
  chỉ tổ chức gọn hơn thôi!
  ```

- [ ] **Deploy executed** at off-peak hour (e.g., 7 AM):
  - Push code to production
  - Run `setup_bot_commands()` to update bot menu button
  - Run smoke test: send /menu → verify main menu loads
  - Send 1 test query per category → verify all work

- [ ] **Post-deploy notification** sent within 1 hour:
  ```
  ✨ Menu mới đã sẵn sàng!
  
  Gõ /menu để khám phá. Hoặc cứ hỏi mình tự nhiên 
  như cũ — mình hiểu mà 😊
  ```

- [ ] **Monitoring during 4h post-deploy:**
  - Watch error logs
  - Watch user complaint channel
  - Watch /menu invocation rate (should spike then normalize)

- [ ] **Rollback trigger documented:**
  - Error rate >5% → rollback
  - Critical flow broken → rollback
  - User complaints >3 → investigate, potential rollback

### Implementation Notes

- Schedule deploy when you have 4-hour window for monitoring
- Have rollback command ready in terminal before deploy
- Send announcements via broadcast feature or to main user channel

### Definition of Done

- New menu live and stable
- Both announcements sent
- 4h monitoring complete with no rollback needed

### Labels
`phase-3.6` `story` `deploy` `priority-critical`

---

## [Story] P3.6-S12: User testing with 3 users post-deploy

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~2 days (1 day testing + 1 day analyzing) | **Depends on:** P3.6-S11

### Reference
📖 [phase-3.6-detailed.md § 2.3 — User Testing](./phase-3.6-detailed.md)

### User Story

As a product owner, I need real user feedback within 48h of deploy to verify the new menu actually feels better than the old one — and catch any issues automated tests missed.

### Acceptance Criteria

- [ ] Recruit 3 real users (1 Starter, 1 Mass Affluent, 1 HNW)
- [ ] Each user spends 10-15 minutes exploring new menu
- [ ] Tasks given to each user:
  1. Tìm net worth của bạn
  2. Xem chi tiêu tháng này theo loại
  3. Thêm 1 mục tiêu mới (or check goals if can't add)
  4. Check VNM giá hôm nay

- [ ] **For each task, capture:**
  - Time to complete (in seconds)
  - Confusion points / wrong taps
  - Whether free-form was used as alternative
  - Any verbal reactions

- [ ] **Post-test interview** (15 min each):
  - Compared to old menu, better/worse/same?
  - Did the intro text help understand each section?
  - Did you notice the warmth ("mình giúp...")?
  - Any moment of confusion?
  - Would you recommend menu or just use free-form?

- [ ] **Success metrics:**
  - All 3 users complete all 4 tasks
  - Average task time <2 minutes
  - 0 users say "menu cũ tốt hơn"
  - ≥2 users notice warmer tone

- [ ] **Document findings** in `docs/current/phase-3.6-user-test-results.md`

### Implementation Notes

- Conduct sessions via video call if possible (record screen)
- Or async: give task list, user reports back via Telegram
- Pay/thank users (small token of appreciation)

### Definition of Done

- 3 users tested
- Findings documented
- Decision: ship as-is OR iterate (with specific changes)

### Labels
`phase-3.6` `story` `testing` `user-feedback`

---

## [Story] P3.6-S13: Cleanup, archive, and documentation updates

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~0.5 day | **Depends on:** P3.6-S11, P3.6-S12

### User Story

As a future-self maintaining this codebase 6 months later, I want the old menu code archived (not deleted) so I can reference past decisions, and documentation updated to reflect current state.

### Acceptance Criteria

- [ ] **Code cleanup:**
  - Move old menu handler → `app/bot/handlers/_archived/menu_v1.py` with header comment explaining context
  - Old callback redirect (graceful "menu deprecated") → keep for 1 month, then remove (create issue P4-S? for follow-up)
  - All temporary debug logs removed

- [ ] **Documentation updates:**
  - Update `CLAUDE.md`:
    - Remove mention of old menu
    - Add note about new 5-category menu
    - Update folder structure if changed
  - Update `docs/current/strategy.md`:
    - Add note: "Phase 3.6 (Menu UX Revamp) completed [date]"
  - Update `README.md`:
    - Update screenshots if any
  - Create `docs/current/phase-3.6-retrospective.md` with:
    - What worked well (adaptive intros, hard cutover smooth)
    - What was harder than expected
    - Open questions for Phase 4

- [ ] **Move issue files:**
  - All Phase 3.6 closed issues → `docs/issues/closed/by-phase/phase-3.6/` (handled by GitHub Action automatically)
  - Verify INDEX.md updated

- [ ] **Final analytics check:**
  - 1-week post-deploy: review menu invocation metrics
  - Document baseline vs after numbers

### Implementation Notes

- Don't aggressive delete — archive everything
- Retro doc honest about both wins and pain points
- This is final ribbon-tying for the phase

### Definition of Done

- Old code archived properly
- All docs updated
- Retrospective complete
- Phase 3.6 officially "done"

### Labels
`phase-3.6` `story` `documentation` `cleanup`

---

# 🎯 Epic Dependencies Graph

```
Epic 1 (Week 1) — Structure & Content
  P3.6-S1 → P3.6-S2 → P3.6-S3 → P3.6-S4
                         ↓        ↓
                       P3.6-S5  P3.6-S6
                                                       ↓
Epic 2 (Week 1 cuối) — Adaptive Polish
  P3.6-S7 (parallel-able)
  P3.6-S8 (independent quick win)
  P3.6-S9 → depends on Epic 1
  P3.6-S10 → depends on S5+S6+S9
                                                       ↓
Epic 3 (Week 2 first half) — Migration
  P3.6-S11 → P3.6-S12 → P3.6-S13
```

**Parallel opportunities:**
- Epic 1: P3.6-S5 và P3.6-S6 can run parallel after S4
- Epic 2: P3.6-S8 (bot commands update) is fully independent — can do anytime
- Epic 2: P3.6-S7 can start in parallel with S5/S6

---

# 📝 Setup Instructions for Phase 3.6

## Step 1: Create Epic Issues First

1. Create `Epic 1: Menu Structure & Content` → note issue # (e.g., #200)
2. Create `Epic 2: Adaptive Polish & Integration` → note issue # (e.g., #201)
3. Create `Epic 3: Migration & Quality Assurance` → note issue # (e.g., #202)

## Step 2: Create 13 Story Issues

For each story, copy from this file with Parent Epic reference at top.

## Step 3: Update Epic Task Lists

After all stories created, edit Epic bodies replacing `#XXX` with actual numbers.

## Step 4: Start Implementation

Begin with **P3.6-S1** (no dependencies). Follow dependency graph.

---

# 💡 Tips for Implementing with Claude Code

## Per-Story Pattern

```
Implement #XXX [P3.6-Sn] following these references:
1. Read docs/current/phase-3.6-detailed.md (architecture)
2. Read docs/issues/active/issue-XXX.md (this story)

Specific focus:
- All Acceptance Criteria items
- Reuse Phase 3.5 handlers where possible
- Test with 4 wealth-level personas
```

## Critical Pattern: Reuse, Don't Rebuild

Phase 3.6 is **plumbing** — connecting menu UI to existing handlers (Phase 3A wizards + Phase 3.5 intent handlers). Resist urge to add new features. If sub-menu action needs feature that doesn't exist, **stub it with "coming soon"** and create issue for Phase 4.

## Common Pitfalls Specific to Phase 3.6

1. **Telegram callback_data 64-char limit** — keep callbacks short (`menu:assets:net_worth` is 21 chars, fine)

2. **Markdown parse errors** — `*emphasis*` and `_underscores_` need escaping in Telegram. Test all intros render correctly.

3. **Edit vs Send confusion** — `query.edit_message_text()` for navigation, `update.message.reply_text()` for new content. Use right one.

4. **State leak between menus** — when entering a wizard from menu, set wizard state cleanly. Test the flow: menu → wizard → menu.

5. **Wealth level boundary flicker** — if user's net worth fluctuates near a boundary (e.g., 29.9tr ↔ 30.1tr), they may see different intros each time. **This is expected** — don't try to lock.

6. **Personality drift** — copy reviewers should be native Vietnamese speakers, ideally Bé Tiền target persona (30-50 yo). Tone consistency matters.

---

**Phase 3.6 transforms menu from "expense tracker era" to "Personal CFO interface". Sau phase này, mọi pixel của Bé Tiền match positioning V2. 🎨💚**
