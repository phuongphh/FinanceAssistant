# Issue #42

[Phase 2 - Week 3] Weekly Fun Facts Generator

## User Story
As a user, I want to receive a fun, personalized insight about my spending every Sunday — like how many cups of coffee I bought or how my weekend spending compares to weekdays — so I feel the bot really understands my habits and I look forward to opening it.

## Background
Phase 2 - Week 3. "Surprise & Delight" feature. The goal: make users want to screenshot and share. Fun facts must be data-driven from the user's own transactions — not generic tips.

## Design Principle
*"Tháng này bạn tiêu 1.2tr cho café — bằng 60 ly Highlands 😄"* — personal, surprising, and slightly funny.

## Tasks

### Content File (`content/fun_fact_templates.yaml`)
- [ ] Create YAML with at least 8 fun fact template types:
  1. **coffee_equivalent** — chi café > 500k → convert to cup count (avg 55k/ly)
  2. **grab_count** — Grab >= 5 lần → trips + total + avg per trip
  3. **food_delivery_count** — GrabFood/ShopeeFood >= 10 lần → compare to cooking
  4. **weekend_vs_weekday** — weekend avg vs weekday avg, if ratio > 1.5x
  5. **biggest_category** — always-applicable fallback, top category of the week
  6. **new_merchant** — first time logging a merchant
  7. **saving_projection** — if saving consistently, show 1yr/5yr projection (6% interest)
  8. **day_of_month_pattern** — if spending pattern by day is detectable

### Fun Fact Generator (`app/bot/personality/fun_facts.py`)
- [ ] `generate_for_user(user)` — compute which facts are applicable, randomly pick the most interesting one
- [ ] Fact methods for each type (at least 5/8 for MVP):
  - `_coffee_fact(user, spend)`
  - `_grab_fact(user, count, total)`
  - `_delivery_fact(user, count, total)`
  - `_weekend_fact(user, weekend_avg, weekday_avg)`
  - `_biggest_category_fact(user, category_data)`
- [ ] Fallback to `biggest_category_fact` if no other fact applies
- [ ] Money formatting reuses Phase 1 `format_money_short` / `format_money_full`

### Scheduled Job (`app/scheduled/weekly_fun_facts.py`)
- [ ] Run every **Sunday at 19:00**
- [ ] Fetch users active in last 14 days
- [ ] Generate and send 1 fun fact per user
- [ ] asyncio.sleep(1) between users
- [ ] Skip users who have opted out of weekly messages (if opt-out exists)

## Acceptance Criteria
- [ ] At least 5 different fact types compute correctly
- [ ] Facts use real user data — not hardcoded examples
- [ ] Money amounts formatted with Vietnamese style (45k, 1.5tr)
- [ ] Messages are funny and light — no lecturing tone
- [ ] Manually trigger for a test user → receives correct fact
- [ ] Users with insufficient data (< 1 week transactions) receive generic fallback

## Reference
`docs/strategy/phase-2-detailed.md` — Section 3.2
