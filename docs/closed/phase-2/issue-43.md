# Issue #43

[Phase 2 - Week 3] Seasonal Content — Vietnam Events Calendar

## User Story
As a user in Vietnam, I want the bot to acknowledge important Vietnamese cultural events — like Tết, Trung thu, Black Friday, back-to-school season — with timely, relevant messages that help me plan my finances around them, so the bot feels like it truly understands my life context.

## Background
Phase 2 - Week 3. Seasonal content is a major differentiator in the Vietnamese market. Competitors (Money Lover, MISA) do NOT do this well. This is a relatively low-effort, high-impact feature.

## Key Insight from strategy.md
*"Seasonal content — quan trọng với thị trường VN"*. Tết alone can spike household spending by 200-300%. A bot that acknowledges this builds trust.

## Tasks

### Content File (`content/seasonal_calendar.yaml`)
- [ ] Define at least 8 Vietnam-specific events for the next 12 months:
  1. **tet_preparation** — 10 days before Tết: offer to create Tết category
  2. **tet_day** — Mùng 1 Tết: greeting message
  3. **post_tet_review** — 1 week after Tết: show Tết spending summary
  4. **mid_autumn** — Trung thu: recall last year's mooncake spend (if data exists)
  5. **back_to_school** — Mid August: budget planning reminder for parents
  6. **black_friday** — 4 days before BF: offer to set shopping budget limit
  7. **double_11** — Nov 10: reminder with last year's 11.11 spend
  8. **year_end_review** — Dec 28: tease upcoming year-end Wrapped report

### Lunar Date Support
- [ ] Integrate `lunardate` Python library for Tết and Trung thu (lunar calendar)
- [ ] Auto-calculate correct solar date for current year — do NOT hardcode
- [ ] Or: update YAML annually with correct dates (simpler approach for MVP)

### Seasonal Notifier (`app/scheduled/seasonal_notifier.py`)
- [ ] Run daily at 8:00 AM
- [ ] Load `seasonal_calendar.yaml`, compare event trigger_dates to today
- [ ] For matching events: render message with user context, send to all active users
- [ ] Fetch last-year context if needed (e.g., last_year_mid_autumn spend)
- [ ] asyncio.sleep(1) between users
- [ ] Each event fires only once per user per year (deduplication via user_events)

### Optional — Tết Category Action
- [ ] When `tet_preparation` event fires, include button: `[📂 Tạo category Tết 2026]`
- [ ] Callback creates a temporary category with Tết emoji 🧧

## Acceptance Criteria
- [ ] At least 8 events defined in YAML covering next 12 months
- [ ] Tết date computed correctly (not hardcoded) for current + next year
- [ ] Seasonal messages send only once per user per event per year
- [ ] Post-Tết review message shows actual Tết category spending (if available)
- [ ] Messages feel culturally appropriate — not generic (native speaker review)
- [ ] YAML is the single source of truth — no dates hardcoded in Python

## Reference
`docs/strategy/phase-2-detailed.md` — Section 3.3
