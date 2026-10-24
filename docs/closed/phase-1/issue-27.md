# Issue #27

[Phase 1 - Week 1] Rich Message Formatter — Progress Bar, Money Format & Templates

## User Story
As a user, I want the bot to send beautifully formatted messages (with progress bars, emoji, and proper Vietnamese money formatting) instead of plain text responses.

## Background
Phase 1 - Week 1. Replaces all plain `bot.send_message(..., 'Đã lưu')` with rich templates.

## Tasks
- [ ] Create `app/bot/formatters/progress_bar.py`
  - `make_progress_bar(current, total, width=10)` → e.g. `████████░░ 80%`
  - `make_category_bar(amount, max_amount)` (no % label)
  - Handle edge cases: total=0, current > total
- [ ] Create `app/bot/formatters/money.py`
  - `format_money_short(amount)` → 45k, 1.5tr, 25tr, 1.2 tỷ
  - `format_money_full(amount)` → 45,000đ, 1,500,000đ
- [ ] Create `app/bot/formatters/templates.py` with 4 templates:
  - `format_transaction_confirmation(merchant, amount, category_code, ...)`
  - `format_daily_summary(date, total_spent, transaction_count, breakdown, ...)`
  - `format_budget_alert(category_code, spent, budget, days_left)`
  - `format_welcome_message(display_name)`
- [ ] Replace ALL existing plain text bot replies with these templates
- [ ] Write unit tests: `tests/test_progress_bar.py`, `tests/test_templates.py`

## Acceptance Criteria
- [ ] `make_progress_bar(50, 100)` returns `█████░░░░░ 50%`
- [ ] `format_money_short(45000)` returns `45k`
- [ ] `format_money_short(1500000)` returns `1.5tr`
- [ ] Transaction confirmation message includes emoji, amount, and progress bar
- [ ] All unit tests pass
- [ ] Manually send 10 test transactions on Telegram — messages look polished

## Reference
`docs/strategy/phase-1-detailed.md` — Sections 1.2, 1.3, 1.4
