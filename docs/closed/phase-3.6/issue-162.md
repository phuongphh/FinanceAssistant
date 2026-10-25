# Issue #162

[Story] P3.6-S2: Build MenuFormatter with basic intros

**Parent Epic:** #158 (Epic 1: Menu Structure & Content)

## User Story
As a developer building menu logic, I need a formatter class that loads YAML và produces Telegram InlineKeyboardMarkup objects so menu rendering is centralized and consistent.

## Acceptance Criteria
- [ ] File `app/bot/formatters/menu_formatter.py` với `MenuFormatter` class
- [ ] Method `format_main_menu(user) -> tuple[str, InlineKeyboardMarkup]`:
  - Load YAML once on init (cached)
  - Build text: title + intro + hint
  - Build keyboard: 2-column grid cho 5 main buttons (last button alone in last row)
  - **Note:** Story này dùng **basic intro** (default `young_prof` level) — Epic 2 mới adaptive
- [ ] Method `format_submenu(user, category: str) -> tuple[str, InlineKeyboardMarkup]`:
  - Load sub-menu config by category name
  - Build text: title + intro + hint
  - Build keyboard: 1-column vertical layout
  - Last button = "◀️ Quay về" với callback `menu:main`
- [ ] Both methods support `parse_mode="Markdown"`
- [ ] Error handling: unknown category raises ValueError
- [ ] Stateless after init (thread-safe)
- [ ] Placeholder substitution: `intro.format(name=user.display_name or "bạn")`

## Test Plan
```python
async def test_format_main_menu():
    text, keyboard = await formatter.format_main_menu(user)
    assert "Tài sản" in text
    assert len(keyboard.inline_keyboard) >= 3

async def test_submenu_back_button():
    _, keyboard = await formatter.format_submenu(user, "assets")
    assert "Quay về" in keyboard.inline_keyboard[-1][0].text
```

## Estimate: ~1 day
## Depends on: P3.6-S1
## Reference: `docs/current/phase-3.6-detailed.md` § 1.3
