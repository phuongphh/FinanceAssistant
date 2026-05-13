# Issue #26

[Phase 1 - Week 1] Setup Categories & Emoji Config System

## User Story
As a developer, I want a centralized category configuration system so that all modules use consistent emojis, names, and colors.

## Background
Phase 1 - Week 1 foundation task. All other formatters and keyboards depend on this config file.

## Tasks
- [ ] Create `app/config/categories.py` with 13 categories using `@dataclass Category` (code, name_vi, emoji, color_hex)
- [ ] Create `app/config/emoji_map.py` as re-export helper
- [ ] Implement `get_category(code)` with fallback to `other`
- [ ] Implement `get_all_categories()` returning full list
- [ ] Ensure categories include: food, transport, housing, shopping, health, education, entertainment, saving, investment, gift, utility, transfer, other

## Acceptance Criteria
- [ ] `get_category("food")` returns Category with emoji 🍜 and color #FF6B6B
- [ ] `get_category("unknown")` returns the "other" category (no crash)
- [ ] `get_all_categories()` returns all 13 categories
- [ ] Adding a new category only requires editing `categories.py` (no other files)
- [ ] color_hex is included for future Mini App chart usage

## Reference
`docs/strategy/phase-1-detailed.md` — Section 1.1
