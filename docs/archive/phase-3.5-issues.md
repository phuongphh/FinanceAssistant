# Phase 3.5 — GitHub Issues (Epics + User Stories)

> **Purpose:** 4 Epics chứa 22 User Stories — sẵn sàng copy-paste vào GitHub.  
> **Format:** Epic = issue cha có task list link tới Stories. Stories = issue con với AC chi tiết.  
> **Reference:** Mỗi story link về [phase-3.5-detailed.md](../current/phase-3.5-detailed.md)

---

## 📊 Overview

| Epic | Tuần | Stories | Goal |
|------|------|---------|------|
| Epic 1: Foundation & Patterns | 1 | 6 stories | Rule-based classifier + 6 read handlers |
| Epic 2: LLM Fallback & Clarification | 2 | 5 stories | Cover ambiguous queries with LLM |
| Epic 3: Personality & Advisory | 3 (1st half) | 5 stories | Wealth-aware tone + advisory queries |
| Epic 4: Quality Assurance | 3 (2nd half) | 6 stories | Test suite, integration, user testing |

**Total:** 22 user stories across 4 epics, ~3 weeks of work.

---

## 🏷️ GitHub Labels Setup

Add new labels in addition to existing Phase labels:

**Phase 3.5 specific:**
- `phase-3.5` (color: cyan)
- `epic` (color: dark purple) — for Epic-type issues
- `story` (color: light purple) — for User Story-type issues
- `intent-classifier` (specific area)
- `nlu` (Natural Language Understanding work)
- `personality` (Bé Tiền tone work)

---

## 🔗 GitHub Configuration

### Epic Structure

Each Epic body contains a **task list** with story references:

```markdown
## Stories in this Epic
- [ ] #142 [Story] P3.5-S1: Define intent types
- [ ] #143 [Story] P3.5-S2: Create test fixtures
```

GitHub auto-renders as checkboxes that update when child issues close — visual progress tracking for free.

### Project Board Layout

Suggested columns:
- 📋 **Epic Backlog** — Epics not yet started
- 🎯 **Epic Active** — currently in progress (1-2 max)
- 📦 **Story Backlog** — stories within active epic
- 🏗️ **Story In Progress** — being coded
- 👀 **Story Review** — PR open
- ✅ **Story Done**
- 🎉 **Epic Complete**

### Workflow

1. Create Epic issue first → get number (e.g., #150)
2. Create child Story issues → get numbers (e.g., #151-156)
3. Edit Epic body → fill in story numbers in task list
4. As stories close → Epic task list auto-checks
5. When all stories closed → close Epic

---

# Epic 1: Intent Foundation & Patterns

> **Type:** Epic | **Phase:** 3.5 | **Week:** 1 | **Stories:** 6

## Overview

Build the foundational intent classification system using **rule-based pattern matching** for Vietnamese queries. **No LLM calls** in this Epic. By end of Epic 1, Bé Tiền can correctly classify and respond to ~75% of queries using regex patterns alone.

## Why This Epic Matters

Phase 3A already has services that fetch data (assets, transactions, market). What's missing is the **understanding layer** — when user types free-form text, how do we know what they want? This Epic builds that bridge.

## Success Definition

When Epic 1 is complete:
- ✅ User text matching common patterns gets correct response
- ✅ All 11 real queries from design phase work end-to-end
- ✅ Zero LLM API calls in this layer
- ✅ Response time < 200ms for rule-matched queries
- ✅ Test suite established for future regression prevention

## Stories in this Epic

> Replace `#XXX` with actual issue numbers after creating GitHub issues.

- [ ] #XXX [Story] P3.5-S1: Define intent types and result data structures
- [ ] #XXX [Story] P3.5-S2: Create test fixtures from real queries
- [ ] #XXX [Story] P3.5-S3: Build parameter extractors (time, category, ticker, amount)
- [ ] #XXX [Story] P3.5-S4: Implement rule-based pattern matching engine
- [ ] #XXX [Story] P3.5-S5: Build read query handlers (assets, expenses, market, etc.)
- [ ] #XXX [Story] P3.5-S6: Wire intent pipeline into Telegram message router

## Out of Scope (for Epic 1)

- ❌ LLM fallback — Epic 2
- ❌ Clarification flow — Epic 2
- ❌ Personality wrapping — Epic 3
- ❌ Advisory queries — Epic 3

## Dependencies

- ✅ Phase 3A complete (provides Asset, Transaction, Market services)
- ✅ Phase 2 complete (provides user.display_name, wealth_level)

## Reference

📖 [phase-3.5-detailed.md § Tuần 1](../current/phase-3.5-detailed.md)

### Labels
`phase-3.5` `epic` `intent-classifier` `priority-critical`

---

## [Story] P3.5-S1: Define intent types and result data structures

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~0.5 day | **Depends on:** None

### Reference
📖 [phase-3.5-detailed.md § 1.1](../current/phase-3.5-detailed.md)

### User Story

As a developer building intent classification, I need typed enums and dataclasses representing intents and their results, so that the system has a stable contract that all classifiers, dispatchers, and handlers can rely on.

### Acceptance Criteria

- [ ] File `app/intent/intents.py` exists with `IntentType` enum
- [ ] Enum contains all 17 intents from spec:
  - **Read intents (10):** query_assets, query_net_worth, query_portfolio, query_expenses, query_expenses_by_category, query_income, query_cashflow, query_market, query_goals, query_goal_progress
  - **Action intents (2):** action_record_saving, action_quick_transaction
  - **Advanced intents (2):** advisory, planning
  - **Meta intents (4):** greeting, help, unclear, out_of_scope
- [ ] Dataclass `IntentResult` with fields:
  - `intent: IntentType`
  - `confidence: float` (0.0-1.0)
  - `parameters: dict` (default empty)
  - `raw_text: str`
  - `classifier_used: str` ("rule" | "llm" | "none")
  - `needs_clarification: bool`
  - `clarification_question: str | None`
- [ ] Module-level docstring explains intent design philosophy
- [ ] Type hints on all fields
- [ ] Imports clean — no circular dependencies

### Implementation Notes

- Use `str` Enum so values are JSON-serializable: `IntentType.QUERY_ASSETS == "query_assets"`
- Use `field(default_factory=dict)` for parameters (avoid mutable default trap)
- Add `__repr__` to IntentResult for easier debugging

### Test Plan

```python
def test_intent_type_serializable():
    assert IntentType.QUERY_ASSETS.value == "query_assets"

def test_intent_result_default_params():
    r = IntentResult(intent=IntentType.UNCLEAR, confidence=0.0, raw_text="")
    assert r.parameters == {}
    assert r.classifier_used == ""
```

### Definition of Done

- Code merged to main
- Unit tests passing
- No type errors (`mypy app/intent/intents.py`)

### Labels
`phase-3.5` `story` `backend` `priority-critical`

---

## [Story] P3.5-S2: Create test fixtures from real queries

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~0.5 day | **Depends on:** P3.5-S1

### Reference
📖 [phase-3.5-detailed.md § Tuần 3 — User Testing Protocol](../current/phase-3.5-detailed.md)

### User Story

As a developer who values test-driven development, I need a YAML fixture file with real Vietnamese queries and expected classifications, so that I can validate every change against known-good behavior throughout development.

### Why This Story Comes Early

Test fixtures created **before** classifier implementation force test-first thinking. Pattern development becomes "make this test pass" instead of subjective tweaking. This is the canonical fixture file.

### Acceptance Criteria

- [ ] File `tests/test_intent/fixtures/query_examples.yaml` exists
- [ ] Contains the **11 real queries** from design phase, each with expected intent + parameters:
  - "tiết kiệm 1tr" → action_record_saving, amount=1000000
  - "tài sản của tôi có gì?" → query_assets
  - "tôi có tài sản gì?" → query_assets
  - "làm thế nào để đầu tư tiếp?" → advisory
  - "hiện tại có thể mua gì để có thêm tài sản?" → advisory
  - "mục tiêu hiện giờ của tôi có gì?" → query_goals
  - "muốn đạt được việc mua xe tôi cần phải làm gì?" → query_goal_progress, goal_name="mua xe"
  - "portfolios chứng khoán của tôi gồm những mã gì?" → query_portfolio
  - "các chi tiêu cho sức khỏe của tôi trong tháng này gồm những gì?" → query_expenses_by_category, category="health", time_range="this_month"
  - "liệt kê cho tôi mọi chi phí về ăn uống của tôi tháng này?" → query_expenses_by_category, category="food", time_range="this_month"
  - "thu nhập của tôi là như thế nào?" → query_income
- [ ] **20 additional edge case queries:**
  - Diacritic variations: "tai san cua toi co gi" (no diacritics)
  - Typos: "tài sảnn", "tai sảm"
  - English mixed: "show my assets", "VNM giá today"
  - Out of scope: "thời tiết hôm nay", "kể chuyện cười"
  - Gibberish: "asdkfjh", "?"
  - Greetings: "chào", "hi"
  - Help: "/help", "giúp tôi"
  - Mixed language: "check VNM giúp tôi"
- [ ] Pytest helper `load_query_fixtures()` reads file
- [ ] Each fixture entry has: text, expected_intent, expected_parameters (optional), expected_min_confidence (optional), notes (optional)

### YAML Format Example

```yaml
queries:
  - text: "tài sản của tôi có gì?"
    expected_intent: query_assets
    expected_min_confidence: 0.9
    notes: "Direct, common phrasing"
  
  - text: "liệt kê cho tôi mọi chi phí về ăn uống của tôi tháng này?"
    expected_intent: query_expenses_by_category
    expected_parameters:
      category: food
      time_range_label: "tháng này"
    expected_min_confidence: 0.9
  
  - text: "thời tiết hôm nay"
    expected_intent: out_of_scope
    notes: "Should NOT match any finance intent"
```

### Definition of Done

- Fixture file committed
- Helper function imported and usable from any test
- 31 total fixtures (11 real + 20 edge cases)
- Documentation in fixture file explaining how to add more

### Labels
`phase-3.5` `story` `testing` `priority-critical`

---

## [Story] P3.5-S3: Build parameter extractors

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.5-S1

### Reference
📖 [phase-3.5-detailed.md § 1.3 — Parameter Extractors](../current/phase-3.5-detailed.md)

### User Story

As an intent classifier, I need helper functions to extract structured parameters (time ranges, categories, tickers, amounts) from raw Vietnamese text, so that downstream handlers receive clean, typed data instead of raw strings.

### Acceptance Criteria

- [ ] **Time range extractor** (`app/intent/extractors/time_range.py`)
  - Returns `TimeRange(start, end, label)` dataclass
  - Recognizes: hôm nay, hôm qua, tuần này, tuần trước/qua, tháng này, tháng trước/qua, năm nay
  - Returns None when no time expression found
  - Edge case: tháng 1 → tháng trước = tháng 12 năm trước

- [ ] **Category extractor** (`app/intent/extractors/category.py`)
  - Returns category code string (e.g., "food", "health") or None
  - Maps Vietnamese keywords for all 10 categories
  - Each category has 5+ keyword variations
  - Returns first match found

- [ ] **Ticker extractor** (`app/intent/extractors/ticker.py`)
  - Returns ticker string (e.g., "VNM", "BTC") or None
  - **Whitelist-based:** only returns known VN30 tickers + major crypto + ETFs (avoid false positive với từ tiếng Anh)
  - Handles "VN-Index", "VN Index", "vnindex" → "VNINDEX"
  - Handles "bitcoin" → "BTC", "ethereum" → "ETH"

- [ ] **Amount extractor** (`app/intent/extractors/amount.py`)
  - Returns int (VND value) or None
  - Recognizes: "1tr"=1000000, "500k"=500000, "2 triệu"=2000000, "1.5 tỷ"=1500000000
  - Handles plain numbers ≥1000 (e.g., "150000" → 150000)
  - Returns None for ambiguous "5" or "10"

- [ ] All extractors have unit tests covering happy path + edge cases
- [ ] Each extractor function takes only `text: str` parameter (stateless)

### Implementation Notes

- Reuse amount parser from Phase 3A (DRY principle)
- Whitelist tickers in module constant — easy to update
- For category: order keywords by specificity (specific keywords first)

### Test Examples

```python
def test_time_range_thang_nay():
    r = extract("chi tiêu tháng này")
    assert r.label == "tháng này"
    assert r.start.day == 1

def test_category_food():
    assert extract("ăn uống nhà hàng") == "food"
    assert extract("phở bò") == "food"

def test_ticker_whitelist():
    assert extract("VNM giá bao nhiêu") == "VNM"
    assert extract("XYZ giá bao nhiêu") is None  # Not in whitelist

def test_amount_vietnamese():
    assert extract("tiết kiệm 1tr") == 1000000
    assert extract("500 nghìn") == 500000
```

### Definition of Done

- All 4 extractor modules implemented
- Unit test coverage >90%
- Used inside fixture tests

### Labels
`phase-3.5` `story` `backend` `nlu` `priority-critical`

---

## [Story] P3.5-S4: Implement rule-based pattern matching engine

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1.5 days | **Depends on:** P3.5-S1, P3.5-S2, P3.5-S3

### Reference
📖 [phase-3.5-detailed.md § 1.2 — Pattern Matching Engine](../current/phase-3.5-detailed.md)

### User Story

As Bé Tiền, I need to recognize common Vietnamese query patterns (e.g., "tài sản của tôi có gì") and classify them into intents instantly without calling expensive LLM APIs, so that 75% of queries are handled with zero compute cost and sub-200ms latency.

### Acceptance Criteria

- [ ] File `content/intent_patterns.yaml` with 30+ patterns covering all Phase 3.5 intents
- [ ] Each pattern entry has: regex pattern, confidence (0.0-1.0), optional parameter_extractors
- [ ] Patterns ordered: highest specificity / confidence first
- [ ] File `app/intent/classifier/rule_based.py` with `RuleBasedClassifier` class
- [ ] Method `classify(text: str) -> IntentResult | None`:
  - Loads patterns from YAML on init
  - Iterates patterns, returns best match (or None)
  - Tracks best match across all patterns when multiple match
  - Runs parameter extractors when configured
  - Sets `classifier_used = "rule"` on result
- [ ] **Test: All 11 real queries from P3.5-S2 fixture classify with confidence ≥ 0.85**
- [ ] **Test: Out-of-scope queries return None** (not false-positive match)
- [ ] **Test: Time taken to classify < 50ms per query**
- [ ] Patterns handle Vietnamese diacritics gracefully (test fixture includes no-diacritic versions)

### Pattern Coverage Matrix

| Intent | # Patterns | Test queries from fixture |
|--------|-----------|---------------------------|
| query_assets | 4+ | "tài sản của tôi có gì", "tôi có tài sản gì" |
| query_net_worth | 4+ | "tổng tài sản tôi bao nhiêu" |
| query_portfolio | 3+ | "portfolios chứng khoán..." |
| query_expenses | 3+ | "chi tiêu tháng này" |
| query_expenses_by_category | 3+ | "chi sức khỏe tháng này" |
| query_income | 3+ | "thu nhập của tôi" |
| query_cashflow | 2+ | "tháng này dư bao nhiêu" |
| query_market | 4+ | "VNM giá", "VN-Index hôm nay" |
| query_goals | 3+ | "mục tiêu của tôi" |
| query_goal_progress | 2+ | "muốn mua xe cần làm gì" |
| action_record_saving | 2+ | "tiết kiệm 1tr" |
| advisory | 4+ | "nên đầu tư gì" |
| greeting | 1 | "chào", "hi" |
| help | 2+ | "/help", "giúp tôi" |

### Implementation Notes

- Use `re.IGNORECASE` everywhere
- Compile regexes once on init for performance
- Confidence values: 0.95 for very specific, 0.85-0.9 for clear, 0.70-0.80 for ambiguous
- Parameter extractors run AFTER intent match (intent-specific extractors only)

### Definition of Done

- Pass test: all 11 real queries classified correctly with conf ≥0.85
- Pass test: 5+ no-diacritic variations classified correctly
- Pass test: 5+ out-of-scope queries return None
- Performance test: 100 queries < 5 seconds total

### Labels
`phase-3.5` `story` `backend` `nlu` `priority-critical`

---

## [Story] P3.5-S5: Build read query handlers

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~2 days | **Depends on:** P3.5-S1, P3.5-S4

### Reference
📖 [phase-3.5-detailed.md § 1.4 — Action Handlers](../current/phase-3.5-detailed.md)

### User Story

As a user asking "tài sản của tôi có gì?", I expect Bé Tiền to fetch my actual assets and respond with a beautifully formatted summary that reflects my data accurately.

### Acceptance Criteria

- [ ] File `app/intent/handlers/base.py` with abstract `IntentHandler` class
- [ ] **8 concrete handlers** implemented:
  - `query_assets.py` — list user's assets with breakdown by type
  - `query_net_worth.py` — total + change vs last month
  - `query_portfolio.py` — only stocks/funds, with current value
  - `query_expenses.py` — transactions in time range
  - `query_expenses_by_category.py` — filtered by category + time
  - `query_income.py` — list income streams + total
  - `query_market.py` — current price, optionally with user's holding
  - `query_goals.py` — list active goals with progress

- [ ] Each handler:
  - Implements `async def handle(intent: IntentResult, user) -> str`
  - Reuses existing services from Phase 3A
  - Returns formatted string ready for Telegram (Markdown OK)
  - Handles empty state gracefully ("you have no assets yet")
  - Handles errors gracefully (no stack trace to user)

- [ ] **Critical: query_market handler adds personal context:**
  - If user owns ticker → show quantity + current value
  - Example: "VNM 45,000đ (+1.5%) — bạn sở hữu 100 cổ, giá trị 4.5tr"

- [ ] All handlers use `format_money_short()` and `format_money_full()` from Phase 1

- [ ] **Test: All 11 real queries trigger correct handler and return non-empty response**

### Per-Handler AC Specifics

**query_assets:**
- Lists assets grouped by type
- Shows top 3 per type, "...và X mục nữa" if more
- Total at top
- Filter by `asset_type` parameter if provided

**query_expenses_by_category:**
- Uses TimeRange from parameters
- Uses category from parameters
- Empty result → friendly message
- Show top 10 transactions sorted by amount desc

**query_market:**
- Calls MarketService (Phase 3B will improve, OK to stub for now)
- Personal context lookup via AssetService.find_by_ticker()
- Handles unknown ticker → "Mình chưa biết về mã X"

### Implementation Notes

- Don't add personality wrapper here — Epic 3 does that
- Don't add wealth-level adaptive responses here — Epic 3 does that
- Just clean factual responses for now

### Definition of Done

- All 8 handlers implemented and tested
- Each handler has at least 1 unit test
- Integration test: classify + dispatch returns valid response for fixture queries

### Labels
`phase-3.5` `story` `backend` `priority-critical`

---

## [Story] P3.5-S6: Wire intent pipeline into Telegram message router

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.5-S4, P3.5-S5

### Reference
📖 [phase-3.5-detailed.md § 1.5 — Pipeline & Free-Form Handler, § 1.6 — Integration](../current/phase-3.5-detailed.md)

### User Story

As a user, when I type free-form text into Bé Tiền (not in a wizard, not a command), I expect my message to be understood and handled. The bot should NOT show me a generic menu when it could understand my question.

### Acceptance Criteria

- [ ] File `app/intent/classifier/pipeline.py` with `IntentPipeline` class
  - Wraps RuleBasedClassifier
  - LLM classifier set to None (Epic 2 fills this in)
  - Returns IntentResult always (never None — falls back to UNCLEAR)

- [ ] File `app/intent/dispatcher.py` with `IntentDispatcher` class
  - Maps IntentType → IntentHandler
  - Confidence-based routing (skeleton for Epic 2):
    - confidence > 0.8 → execute handler
    - 0.5-0.8 → execute (full clarify in Epic 2)
    - < 0.5 → return generic "unclear" message
  - Handles UNCLEAR → friendly message with suggestions
  - Handles OUT_OF_SCOPE → polite decline message

- [ ] File `app/bot/handlers/free_form_text.py` with main entry function
  - Called when text doesn't match wizard/command/storytelling
  - Calls pipeline → dispatcher → reply
  - Tracks analytics event `intent_handled`

- [ ] Update `app/bot/router.py` (or main message handler):
  - Add free-form route AFTER existing checks (wizard, storytelling, command)
  - **CRITICAL: Replace existing "show menu on unknown" fallback** with this pipeline

- [ ] **Test E2E:** Send test message via Telegram → receive correct response
  - Test: "tài sản của tôi có gì?" → list of assets
  - Test: "VNM giá bao nhiêu?" → market price
  - Test: "asdkfjh" → friendly "didn't understand" with suggestions
  - Test: "thời tiết hôm nay" → polite out-of-scope decline

- [ ] **Regression test:** Existing flows still work
  - Wizard mode: text in middle of asset wizard goes to wizard handler
  - Storytelling mode: text goes to storytelling
  - Commands like /help, /start unchanged

### Implementation Notes

Order of checks in router matters! Check most specific first:
1. Active wizard → wizard handler
2. Storytelling mode → storytelling handler
3. Command (`/...`) → command handler
4. Free-form text → intent pipeline (NEW)

- Singleton pattern for IntentPipeline (load patterns once)
- Add timeout: if classifier takes >5s, send fallback message

### Analytics Events

Track these events from Day 1:
- `intent_classified` — properties: intent, confidence, classifier_used (rule|llm|none)
- `intent_handler_executed` — properties: intent, handler_name, success
- `intent_unclear` — properties: raw_text (for pattern improvement)

### Definition of Done

- Bot responds to free-form text via intent pipeline
- All Epic 1 handlers reachable through Telegram
- Existing flows not broken
- Analytics tracking working

### Labels
`phase-3.5` `story` `backend` `integration` `priority-critical`

---

# Epic 2: LLM Fallback & Clarification

> **Type:** Epic | **Phase:** 3.5 | **Week:** 2 | **Stories:** 5

## Overview

Augment the rule-based foundation with **LLM-powered classification** for queries that don't match patterns. Add **clarification flows** for ambiguous queries where confidence is medium. By end of Epic 2, Bé Tiền handles 95%+ of queries gracefully — either confidently answers, asks clarification, or politely declines.

## Why This Epic Matters

Rule-based covers 75% but plateaus there. Real users phrase things in unexpected ways:
- "tôi đang giàu cỡ nào?" (no exact pattern, but clearly asks net worth)
- "tháng này tôi xài hoang chưa?" (idiom, asks about expenses)

LLM handles these. But LLM hallucinates → confidence-based dispatching becomes critical.

## Success Definition

When Epic 2 is complete:
- ✅ Queries not matching rules get classified by LLM (with intent + parameters extracted)
- ✅ LLM cost remains <$0.0005 per query average
- ✅ Medium-confidence classifications (0.5-0.8) trigger confirmation OR safe execution (read intents)
- ✅ Low-confidence classifications (<0.5) trigger clarification questions
- ✅ Out-of-scope queries get polite decline messages

## Stories in this Epic

- [ ] #XXX [Story] P3.5-S7: Implement LLM-based intent classifier
- [ ] #XXX [Story] P3.5-S8: Build confidence-based dispatcher with confirm/clarify flows
- [ ] #XXX [Story] P3.5-S9: Create clarification message templates (YAML)
- [ ] #XXX [Story] P3.5-S10: Implement out-of-scope detection and polite decline
- [ ] #XXX [Story] P3.5-S11: Add analytics for classifier accuracy and cost tracking

## Out of Scope (for Epic 2)

- ❌ Personality polish — Epic 3
- ❌ Advisory queries (full LLM reasoning) — Epic 3
- ❌ Wealth-level adaptive responses — Epic 3

## Dependencies

- ✅ Epic 1 complete

## Reference

📖 [phase-3.5-detailed.md § Tuần 2](../current/phase-3.5-detailed.md)

### Labels
`phase-3.5` `epic` `intent-classifier` `ai-llm` `priority-high`

---

## [Story] P3.5-S7: Implement LLM-based intent classifier

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** Epic 1 complete

### Reference
📖 [phase-3.5-detailed.md § 2.1](../current/phase-3.5-detailed.md)

### User Story

As Bé Tiền, when I see a query that no rule pattern matches, I need a cheap and fast LLM call to classify the intent and extract parameters, so that I can still answer the user instead of saying "didn't understand."

### Acceptance Criteria

- [ ] File `app/intent/classifier/llm_based.py` with `LLMClassifier` class
- [ ] Uses **DeepSeek API** via OpenAI SDK (cheaper than Claude/OpenAI for classification)
- [ ] Prompt template defined as module constant `LLM_CLASSIFIER_PROMPT`
- [ ] Method `classify(text: str) -> IntentResult | None`:
  - Sends text + intent list to DeepSeek
  - Uses `response_format={"type": "json_object"}` for structured output
  - Sets `temperature=0.0` (deterministic)
  - Sets `max_tokens=200` (cost control)
  - Parses JSON response into IntentResult
  - Sets `classifier_used = "llm"`
  - Returns None on API errors (caller handles)

- [ ] Prompt instructs LLM to:
  - Choose intent from defined enum only (no creative intents)
  - Provide confidence 0.0-1.0
  - Extract parameters when applicable
  - Return `out_of_scope` for non-finance queries

- [ ] **Test: Classify these queries correctly via LLM:**
  - "tôi đang giàu cỡ nào" → query_net_worth
  - "tháng này xài hoang chưa" → query_expenses
  - "thời tiết hôm nay" → out_of_scope
  - "show me my stocks" → query_portfolio (English)
  - "tài sản của em" → query_assets (different pronoun)

- [ ] **Test: Cost per call < $0.0005** (verify via DeepSeek pricing × token count)

- [ ] **Test: Latency < 2 seconds** (95th percentile)

- [ ] Integrate into `IntentPipeline` (Epic 1's pipeline)
  - Pipeline tries rule first
  - If rule confidence < 0.85 → try LLM
  - Compare confidences, return higher

### Prompt Engineering Notes

- Provide intent list with brief descriptions (helps disambiguation)
- Provide parameter list (allows extraction)
- Use few-shot examples in prompt? **Test both ways** — measure cost vs accuracy
- Vietnamese prompt vs English prompt? **Test both** — Vietnamese may help with linguistic nuance

### Implementation Notes

- Cache LLM responses by query hash (Redis, TTL 24h) — same query twice = 1 call
- Log raw LLM responses for debugging classifier mistakes
- Fail gracefully: if API down, return None — let pipeline fallback to rule's lower confidence match

### Definition of Done

- LLM classifier handles 5+ queries that rule classifier misses
- Cost tracked and verified <$0.0005/call
- Cache hits reduce calls in tests

### Labels
`phase-3.5` `story` `ai-llm` `priority-high`

---

## [Story] P3.5-S8: Build confidence-based dispatcher with confirm/clarify flows

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1.5 days | **Depends on:** P3.5-S7

### Reference
📖 [phase-3.5-detailed.md § 2.2 — Clarification System](../current/phase-3.5-detailed.md)

### User Story

As a user, when Bé Tiền isn't sure what I want, I want it to ASK me a clarifying question rather than execute a wrong action — especially for write operations like recording transactions or savings.

### Acceptance Criteria

- [ ] Update `IntentDispatcher` (from Epic 1) with full confidence routing:

| Confidence | Read Intent | Write Intent |
|-----------|-------------|--------------|
| ≥ 0.8 | Execute | Execute |
| 0.5-0.8 | Execute (read is safe) | **Confirm before execute** |
| < 0.5 | **Clarify** | **Clarify** |

- [ ] **Confirmation flow** for write intents (action_record_saving, action_quick_transaction):
  - Build confirmation message: "Mình hiểu bạn muốn ghi tiết kiệm 1tr. Đúng không?"
  - Inline keyboard: [✅ Đúng] [❌ Không phải]
  - Store pending action in `context.user_data["pending_action"]`
  - On ✅ → execute handler, clear pending
  - On ❌ → ask user to rephrase, clear pending

- [ ] **Clarification flow** for low-confidence intents:
  - Look up clarification template from YAML (P3.5-S9)
  - Send with options as inline keyboard
  - Set state `awaiting_clarification` with last intent
  - User's next message → re-route through pipeline with context

- [ ] **Read intent fast-path** for medium confidence:
  - Read = safe (worst case = wrong info, no data damage)
  - Skip confirmation, just execute
  - But add subtle "if this isn't what you meant, let me know" line at end

- [ ] Test cases:
  - Query "tiết kiệm 1tr" with confidence 0.85 → execute saving (rule high)
  - Query "tiết kiệm" with confidence 0.6 → ask "tiết kiệm bao nhiêu?"
  - Query "show stuff" with confidence 0.3 → unclear response with options
  - Query "tài sản" with confidence 0.7 → execute (read intent, fast-path)

### Implementation Notes

State machine for clarification:
```
Normal → (low conf) → Awaiting Clarification → (user replies) → Re-classify with hint
```

- Timeout: clarification state expires after 10 minutes
- Store original raw_text for context when re-classifying

### Definition of Done

- All 4 confidence × intent-type combinations handled correctly
- Confirmation flow has inline keyboard with callback handlers
- Tested with 20 ambiguous queries

### Labels
`phase-3.5` `story` `backend` `priority-critical`

---

## [Story] P3.5-S9: Create clarification message templates

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.5 day | **Depends on:** P3.5-S8

### Reference
📖 [phase-3.5-detailed.md § 2.2 — Content YAML](../current/phase-3.5-detailed.md)

### User Story

As a content owner, I want clarification messages stored in editable YAML so I can refine wording without code changes when user testing reveals confusing prompts.

### Acceptance Criteria

- [ ] File `content/clarification_messages.yaml` exists with templates for:
  - `low_confidence_assets` — disambiguate which asset type to show
  - `low_confidence_expenses` — ask which time period
  - `low_confidence_market` — ask which ticker
  - `low_confidence_action` — disambiguate save/spend/goal
  - `ambiguous_amount` — confirm parsed amount
  - `ambiguous_category` — choose from list
  - `awaiting_response` — generic "I'm waiting for your reply"

- [ ] Each template has 2-3 variations (avoid repetition)
- [ ] Templates use placeholders: `{name}`, `{amount}`, `{ticker}`, etc.
- [ ] Templates designed with inline keyboard in mind (mention buttons)
- [ ] Tone matches Bé Tiền's personality (warm, "mình"/"bạn")

### Sample Templates

```yaml
low_confidence_assets:
  - |
    Mình hiểu bạn hỏi về tài sản, nhưng chưa rõ chi tiết...
    
    Bạn muốn:
    [📊 Xem tổng tài sản]
    [🏠 Chỉ BĐS]
    [📈 Chỉ chứng khoán]
    [💵 Chỉ tiền mặt]

low_confidence_expenses:
  - |
    Bạn muốn xem chi tiêu của period nào?
    [📅 Hôm nay]
    [📅 Tuần này]
    [📅 Tháng này]
    [📅 Tháng trước]

ambiguous_amount:
  - |
    Số tiền là **{amount}đ** đúng không {name}?
    [✅ Đúng rồi] [✏️ Sửa]
```

### Definition of Done

- All 7 template types present
- 2-3 variations each
- File loads without YAML errors
- Used in P3.5-S8 dispatcher

### Labels
`phase-3.5` `story` `content`

---

## [Story] P3.5-S10: Implement out-of-scope detection and polite decline

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~0.5 day | **Depends on:** P3.5-S7

### Reference
📖 [phase-3.5-detailed.md § Triết Lý — "Out of Scope Polite Decline"](../current/phase-3.5-detailed.md)

### User Story

As a user who occasionally types non-finance things ("thời tiết hôm nay", "kể chuyện cười"), I want Bé Tiền to politely tell me what it can/can't do, instead of failing silently or returning the generic menu.

### Acceptance Criteria

- [ ] File `content/out_of_scope_responses.yaml` with response templates
- [ ] Categories of OOS handled:
  - Weather queries: "thời tiết hôm nay"
  - Entertainment: "kể chuyện cười", "hát cho tôi"
  - General knowledge: "thủ đô của Pháp"
  - Personal: "tôi có nên kết hôn không"
  - Greetings/chitchat: handled by greeting intent, not OOS

- [ ] Polite decline messages:
  - Acknowledge what user asked
  - Mention what Bé Tiền CAN do
  - Don't apologize excessively
  - Keep warm tone

- [ ] LLM classifier returns `out_of_scope` for clear OOS queries (test fixtures)
- [ ] Dispatcher routes `out_of_scope` to dedicated handler
- [ ] Handler logs OOS query (for future expansion analysis)

### Sample Responses

```yaml
out_of_scope_general:
  - |
    Mình chưa biết trả lời câu này {name} ạ 😅
    
    Mình giúp được về:
    💎 Tài sản & dòng tiền
    📊 Chi tiêu & thu nhập
    📈 Thị trường VN & crypto
    🎯 Mục tiêu tài chính
    
    Bạn thử hỏi cách khác xem?

out_of_scope_weather:
  - |
    Thời tiết hôm nay mình không biết được {name} ơi 🌤️
    
    Nhưng nếu bạn muốn hỏi về tài sản, chi tiêu, đầu tư — mình rành lắm!

out_of_scope_chitchat:
  - |
    Mình thiên về tài chính chứ không tán gẫu giỏi 😄
    
    Nhưng có gì về tiền nong mình nghe nhé?
```

### Definition of Done

- 3+ OOS categories with dedicated responses
- 2 variations per category
- LLM classifier accuracy on OOS detection >85%
- Logging for future pattern improvement

### Labels
`phase-3.5` `story` `content` `nlu`

---

## [Story] P3.5-S11: Add analytics for classifier accuracy and cost

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** P3.5-S7, P3.5-S8

### Reference
📖 [phase-3.5-detailed.md § Metrics Phase 3.5](../current/phase-3.5-detailed.md)

### User Story

As the product owner, I need visibility into how well the intent system performs and how much it costs, so that I can identify weak patterns to improve and verify cost stays within budget (<$5/month).

### Acceptance Criteria

- [ ] Track these events with properties:
  - `intent_classified`: intent, confidence, classifier_used (rule|llm|none), latency_ms
  - `intent_handler_executed`: intent, handler_name, success (bool), error
  - `intent_unclear`: raw_text, suggested_intents (top 3 by confidence)
  - `intent_clarification_sent`: original_intent, clarification_type
  - `intent_clarification_resolved`: original_intent, final_intent, time_to_resolve_seconds
  - `intent_oos_declined`: raw_text, oos_category
  - `llm_classifier_call`: input_tokens, output_tokens, latency_ms, cost_usd

- [ ] Daily aggregation (cron job) computing:
  - Total queries handled
  - Rule vs LLM split (% rule, % LLM, % unclassified)
  - Confidence histogram (how many at each 0.1 band)
  - Top unclear queries (raw_text, count)
  - Total LLM cost yesterday
  - Average latency

- [ ] Mini App admin endpoint `/miniapp/api/intent-metrics`:
  - Returns daily aggregation
  - Returns top 20 unclear queries (for pattern improvement)
  - Returns cost trend (7d, 30d)

- [ ] Alert thresholds (log warnings):
  - LLM cost yesterday > $0.50 (10x normal)
  - Rule classifier rate <50% for 3+ days
  - Unclear rate >20% for 3+ days

### Implementation Notes

- Reuse Event model from Phase 2 (don't create new table unless needed)
- Aggregation query: write SQL view or simple script — don't over-engineer
- Cost calculation: track tokens per call, multiply by DeepSeek pricing

### Definition of Done

- All 7 events tracked from Day 1 of Epic 2
- Daily aggregation runs and writes to DB
- Admin endpoint returns metrics
- Tested by manually checking metrics after sending 10 test queries

### Labels
`phase-3.5` `story` `backend` `analytics`

---

# Epic 3: Personality & Advisory

> **Type:** Epic | **Phase:** 3.5 | **Week:** 3 (first half) | **Stories:** 5

## Overview

Transform technically-correct responses into **Bé Tiền responses** — warm, wealth-aware, with personality. Add the **advisory handler** for queries needing reasoning. By end of Epic 3, users feel they're talking to an intelligent assistant that knows them, not a generic chatbot.

## Why This Epic Matters

A correct answer in robotic tone fails the product vision. Phase 1-2 built personality infrastructure (display_name, wealth_level, tone guide). Phase 3.5 must use that infrastructure for query responses, not just for proactive briefings.

## Success Definition

When Epic 3 is complete:
- ✅ Same query yields different responses for Starter vs HNW user (wealth-adaptive)
- ✅ Bé Tiền uses user's name in responses
- ✅ Bé Tiền suggests next actions naturally
- ✅ Advisory queries get useful, contextual reasoning (not generic advice)
- ✅ Advisory handler has legal disclaimer baked in

## Stories in this Epic

- [ ] #XXX [Story] P3.5-S12: Add personality wrapper to query responses
- [ ] #XXX [Story] P3.5-S13: Implement wealth-level adaptive responses
- [ ] #XXX [Story] P3.5-S14: Build advisory handler with rich context
- [ ] #XXX [Story] P3.5-S15: Add follow-up suggestions to responses
- [ ] #XXX [Story] P3.5-S16: Handle voice queries through intent pipeline

## Out of Scope (for Epic 3)

- ❌ Storytelling-style multi-transaction extraction (Phase 3A handles)
- ❌ Real-time market data (Phase 3B)
- ❌ Detailed portfolio analytics (Phase 4)

## Dependencies

- ✅ Epic 1 + Epic 2 complete

## Reference

📖 [phase-3.5-detailed.md § Tuần 3](../current/phase-3.5-detailed.md)

### Labels
`phase-3.5` `epic` `personality` `ai-llm` `priority-high`

---

## [Story] P3.5-S12: Add personality wrapper to query responses

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1 day | **Depends on:** Epic 2 complete

### Reference
📖 [phase-3.5-detailed.md § 3.1 — Personality Layer](../current/phase-3.5-detailed.md)

### User Story

As a user, when I ask "tài sản của tôi có gì?", I don't want a sterile data dump. I want Bé Tiền to greet me, present the info warmly, and feel like it knows me — not a Google Sheets export.

### Acceptance Criteria

- [ ] File `app/bot/personality/query_voice.py` with `add_personality()` function
- [ ] Function `add_personality(response, user, intent_type) -> str`:
  - 30% probability: prepend warm greeting using user.display_name
  - 50% probability: append next-action suggestion related to intent
  - Always: ensure tone matches Bé Tiền guide (xưng "mình", call user "bạn"/{name})

- [ ] Greetings file or constant with 5+ variations:
  - "{name} ơi,"
  - "Hiểu rồi {name}!"
  - "Cho mình check liền,"
  - "Có ngay {name}!"
  - "{name}, đây nè:"

- [ ] Suggestions per intent (5+ each):
  - query_assets → "Muốn xem chi tiết phần nào?"
  - query_expenses → "So sánh với tháng trước không?"
  - query_market → "Xem chi tiết phân tích không?"
  - etc.

- [ ] Integrate into IntentDispatcher: wrap handler result before sending
- [ ] **Test: Same query 5 times produces 3+ different opening phrases** (variation working)
- [ ] **Test: Sterile generic phrases NEVER appear** ("Here are your assets", "Following are...")

### Implementation Notes

- Use Python's `random` for variation
- Avoid stacking too much: don't always greet AND suggest — feel busy
- Never inject personality into clarification or error messages (would feel inauthentic)

### Definition of Done

- All Epic 1 handlers' output goes through personality wrapper
- Visual diff: before/after on 5 sample queries shows clear improvement
- User testing P3.5-S20 will validate this further

### Labels
`phase-3.5` `story` `personality`

---

## [Story] P3.5-S13: Implement wealth-level adaptive responses

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1 day | **Depends on:** P3.5-S12

### Reference
📖 [phase-3.5-detailed.md § 2.3 — Context-Aware Intent](../current/phase-3.5-detailed.md)

### User Story

As a Starter user with 15 million in cash, I want a simple "💵 Tiền mặt: 15tr — đang xây dựng tài sản!" — not an intimidating wall of YTD returns and Sharpe ratios meant for HNW users.

### Acceptance Criteria

- [ ] Update key handlers to be wealth-level aware:
  - `query_assets.py`
  - `query_net_worth.py`
  - `query_portfolio.py`
  - `query_cashflow.py`

- [ ] Each handler detects user's wealth level (from `app/wealth/ladder.py`)

- [ ] **Starter level (0-30tr)** responses:
  - Simple language, no jargon
  - Encouraging tone ("đang xây dựng", "bước đầu tốt")
  - Focus on: total, simple categorization
  - Hide: percentages, change rates, technical metrics

- [ ] **Young Professional (30-200tr)** responses:
  - Add growth context (vs last month)
  - Suggest investment options
  - Slightly more technical

- [ ] **Mass Affluent (200tr-1tỷ)** responses:
  - Full breakdown by type
  - Change tracking
  - Some analytics (top performer, allocation %)

- [ ] **HNW (1tỷ+)** responses:
  - Detailed portfolio analytics
  - YTD return, volatility hints
  - Diversification score
  - Ready for advisor-level conversation

- [ ] **Test: Same query "tài sản của tôi có gì" produces 4 distinctly different responses for 4 mock users (one at each level)**

### Sample Output Comparison

```
Query: "tài sản của tôi có gì?"

Starter (Minh, 15tr):
  💎 Tài sản hiện tại của Minh:
  💵 Tiền mặt: 15tr
  
  Bạn đang ở giai đoạn xây dựng nền tảng — tốt đó! 🌱
  Bước tiếp theo: thử tiết kiệm thêm 1tr/tháng?

HNW (Anh Phương, 5.2 tỷ):
  💎 Tổng giá trị ròng của anh Phương: 5.2 tỷ
  📈 +85tr (+1.6%) so với tháng trước
  
  Phân bổ:
  🏠 BĐS: 2.5 tỷ (48%)
  📈 Chứng khoán: 1.8 tỷ (35%)
  ...
  
  YTD return: +12.5% — tốt hơn VN-Index 3%!
```

### Implementation Notes

- Don't duplicate handler code — use composition (e.g., `format_assets_for_level(level, data)`)
- Reuse `BriefingFormatter` patterns from Phase 3A if applicable
- Test with mock users at boundary values (29.9tr, 30tr, 199.9tr, 200tr)

### Definition of Done

- 4 distinct response styles for 4 levels
- Visual review: each level "feels right" for that user
- No starter user sees HNW-level metrics

### Labels
`phase-3.5` `story` `personality` `priority-high`

---

## [Story] P3.5-S14: Build advisory handler with rich context

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1.5 days | **Depends on:** Epic 2 complete

### Reference
📖 [phase-3.5-detailed.md § 3.2 — Advisory Handler](../current/phase-3.5-detailed.md)

### User Story

As a user asking "làm thế nào để đầu tư tiếp?", I want context-aware advice that considers my actual portfolio, income, and goals — not generic "diversify your investments" platitudes.

### Acceptance Criteria

- [ ] File `app/intent/handlers/advisory.py` with `AdvisoryHandler` class
- [ ] Handler builds rich context before LLM call:
  - User name + wealth level
  - Net worth + breakdown by asset type
  - Monthly income (sum of income_streams)
  - Active goals
  - Recent significant transactions (top 5 of last 30 days)

- [ ] LLM prompt template `ADVISORY_PROMPT`:
  - Tone instructions (Bé Tiền, Vietnamese, "mình"/"bạn")
  - Hard constraints:
    - **Never recommend specific stock tickers** (legal)
    - **Never promise returns** (legal)
    - Suggest 2-3 options, not 1 prescription
    - Ask back if needs more info

- [ ] DeepSeek call with:
  - max_tokens=500 (longer reasoning OK)
  - temperature=0.7 (some creativity)
  - cost monitor (~$0.002/call)

- [ ] **Disclaimer footer always appended:**
  ```
  _Đây là gợi ý dựa trên data cá nhân của bạn, không phải lời khuyên đầu tư chuyên nghiệp._
  ```

- [ ] **Test queries:**
  - "làm thế nào để đầu tư tiếp?" → contextual options
  - "có nên mua VNM không?" → must NOT recommend, redirect to general principles
  - "mình nên tiết kiệm bao nhiêu?" → calculation-based answer
  - "đầu tư crypto được không?" → balanced view, risks

- [ ] Handle context-fetching failures gracefully (e.g., missing income data → ask user)

### Implementation Notes

- Cache advisory responses by query+user_context_hash (Redis, 1 hour TTL)
- Log full conversation for compliance review later
- Consider: rate limit advisory queries to 5/day per user (avoid abuse)

### Sample Response Pattern

```
{name} ơi, dựa vào portfolio của bạn:

📊 Hiện tại bạn có:
- 60% BĐS (concentration cao)
- 30% Cash (chưa đầu tư)
- 10% CK

Mình thấy 2 hướng đi:

**Option 1: Đa dạng hóa nhẹ**
Chuyển 200tr cash sang quỹ ETF VN30 — vừa đầu tư vừa giữ thanh khoản.

**Option 2: Tập trung kỹ thuật**  
Học thêm về stock picking, đầu tư active 30% portfolio. Cần thời gian học hỏi.

Bạn nghiêng về hướng nào hơn? 🤔

_Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư chuyên nghiệp._
```

### Definition of Done

- 4+ test advisory queries produce contextual responses
- No hallucinated stock recommendations in 20 test runs
- Disclaimer present in 100% of responses

### Labels
`phase-3.5` `story` `ai-llm` `priority-high`

---

## [Story] P3.5-S15: Add follow-up suggestions to responses

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~0.5 day | **Depends on:** P3.5-S12

### Reference
📖 [phase-3.5-detailed.md § 3.1 — `_get_suggestion()`](../current/phase-3.5-detailed.md)

### User Story

As a user who got an answer, I want Bé Tiền to suggest natural next questions or actions — turning each response into a launching pad for deeper exploration.

### Acceptance Criteria

- [ ] Each handler returns response with optional follow-up suggestion
- [ ] Suggestions are **inline keyboard buttons**, not just text
- [ ] Buttons trigger pre-defined intents on tap
- [ ] Suggestions are wealth-aware (Starter sees beginner suggestions, HNW sees advanced)
- [ ] Examples per intent:
  - After query_assets → "📈 So với tháng trước", "🏠 Chỉ BĐS", "💎 Tổng net worth"
  - After query_expenses → "📅 Tuần này", "🍕 Theo loại", "📊 So sánh"
  - After query_market → "💼 Portfolio của tôi", "📰 Tin liên quan" (Phase 3B)
  - After query_net_worth → "📊 Phân bổ chi tiết", "📈 Trend 6 tháng"

- [ ] Suggestions don't duplicate what user just asked
- [ ] Maximum 3 suggestions per response (avoid clutter)

### Implementation Notes

- Use Telegram InlineKeyboardMarkup
- Callback data format: `intent:{intent_type}:{params_encoded}`
- Add a callback handler that translates back to intent execution

### Definition of Done

- All 8 read handlers return responses with relevant suggestions
- Tap on any suggestion triggers next correct intent
- No suggestion buttons exceed Telegram's row width

### Labels
`phase-3.5` `story` `frontend`

---

## [Story] P3.5-S16: Handle voice queries through intent pipeline

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~0.5 day | **Depends on:** Phase 3A's voice infrastructure

### Reference
📖 [phase-3.5-detailed.md § Bẫy Thường Gặp #8](../current/phase-3.5-detailed.md)

### User Story

As a user, when I send a voice message asking "tài sản của tôi có gì", I expect Bé Tiền to transcribe and answer — not just store it as a transaction storytelling input.

### Acceptance Criteria

- [ ] Update voice handler from Phase 3A to:
  1. Transcribe audio → text (existing)
  2. Send transcribed text through intent pipeline (new)
  3. If intent is `unclear` AND user is in storytelling mode → fall back to storytelling
  4. Otherwise → use intent pipeline result

- [ ] Show transcript before processing (existing behavior)
- [ ] Handle voice queries with same accuracy as text queries
- [ ] **Test: Voice query "tài sản của tôi có gì" → query_assets → response**
- [ ] **Test: Voice during storytelling mode → still extracts transactions**
- [ ] **Test: Voice query in noisy environment with bad transcription → graceful "didn't catch that"**

### Implementation Notes

- Order matters: storytelling mode check FIRST, then intent pipeline
- Whisper sometimes adds punctuation differently — patterns must handle both
- If transcription confidence low (Whisper exposes this), prefer asking user to retype

### Definition of Done

- Voice query "tài sản của tôi có gì" works end-to-end
- Storytelling mode still works for voice
- Edge case: empty transcript handled

### Labels
`phase-3.5` `story` `integration`

---

# Epic 4: Quality Assurance

> **Type:** Epic | **Phase:** 3.5 | **Week:** 3 (second half) | **Stories:** 6

## Overview

Validate the entire Phase 3.5 system through systematic testing, real user trials, and performance verification. By end of Epic 4, we have data confirming Phase 3.5 meets all exit criteria and users genuinely feel Bé Tiền is intelligent.

## Why This Epic Matters

Phase 3.5's success is **subjective** ("does it feel intelligent?"). Without rigorous testing, we'd ship something that "works in dev" but fails real users. This Epic exists to ground the work in evidence.

## Success Definition

When Epic 4 is complete, all exit criteria from phase-3.5-detailed.md are verifiably met:
- ✅ 30 test queries pass with success rates per group
- ✅ Cost <$5/month at current usage  
- ✅ D7 retention not regressed
- ✅ User feedback: "Bé Tiền hiểu mình tốt hơn"
- ✅ Rule-based catches >70% of queries
- ✅ No regressions in existing flows

## Stories in this Epic

- [ ] #XXX [Story] P3.5-S17: Run regression test suite for existing flows
- [ ] #XXX [Story] P3.5-S18: Build automated test suite for 30 canonical queries
- [ ] #XXX [Story] P3.5-S19: Performance and cost verification
- [ ] #XXX [Story] P3.5-S20: User testing with 5 real users
- [ ] #XXX [Story] P3.5-S21: Pattern improvement based on unclear queries
- [ ] #XXX [Story] P3.5-S22: Document Phase 3.5 lessons learned

## Dependencies

- ✅ Epic 1, 2, 3 all complete

## Reference

📖 [phase-3.5-detailed.md § Exit Criteria, § Metrics, § Tuần 3 Testing](../current/phase-3.5-detailed.md)

### Labels
`phase-3.5` `epic` `testing` `priority-high`

---

## [Story] P3.5-S17: Run regression test suite for existing flows

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~1 day | **Depends on:** Epic 1-3 complete

### User Story

As a user who relied on Phase 3A features (asset wizards, briefing, storytelling), I expect them to keep working exactly as before — Phase 3.5 should ADD capabilities, not BREAK existing ones.

### Acceptance Criteria

- [ ] Test asset wizard flows (cash, stock, real_estate) — all work
- [ ] Test storytelling mode (text + voice) — extracts transactions correctly
- [ ] Test morning briefing (7am scheduled) — sends correctly
- [ ] Test daily snapshot job (23:59) — runs correctly
- [ ] Test command handlers (/start, /help, /add_asset) — unchanged
- [ ] Test onboarding flow (Phase 2) — completes correctly
- [ ] Test milestone celebrations (Phase 2) — fire correctly
- [ ] Test empathy triggers (Phase 2) — fire correctly

- [ ] Document any breaking changes (should be zero)
- [ ] Document any improvements found in regression (e.g., text in wizard now also smart-extracts)

### Implementation Notes

- Run via test bot account (not production)
- Have one human go through each flow manually + record observations
- Check error logs for unexpected exceptions during regression

### Definition of Done

- All existing flows verified working
- Zero unexpected errors in logs during testing
- Sign-off document committed to docs

### Labels
`phase-3.5` `story` `testing` `priority-critical`

---

## [Story] P3.5-S18: Build automated test suite for 30 canonical queries

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~1 day | **Depends on:** Epic 3 complete

### Reference
📖 [phase-3.5-detailed.md § 3.3 — User Testing Protocol](../current/phase-3.5-detailed.md)

### User Story

As a developer, I need an automated test suite covering all 30 canonical query types from the design doc, so that future changes to patterns or LLM prompts can be validated without manual testing.

### Acceptance Criteria

- [ ] File `tests/test_intent/test_canonical_queries.py`
- [ ] 30 test cases organized in groups (A through E from spec):
  - **Group A (10):** Direct queries — expect rule match, confidence ≥0.85
  - **Group B (5):** Indirect queries — expect LLM match, confidence ≥0.7
  - **Group C (4):** Action queries — expect confirmation flow
  - **Group D (4):** Advisory — expect advisory handler
  - **Group E (7):** Edge cases — expect graceful handling

- [ ] Tests assert:
  - Correct intent classified
  - Correct parameters extracted (where applicable)
  - Response is non-empty and non-error
  - Latency under threshold (200ms rule, 2s LLM)

- [ ] Group success thresholds (from spec):
  - Group A: ≥95%
  - Group B: ≥80%
  - Group C: ≥85%
  - Group D: ≥80%
  - Group E: 100% graceful (no exception, no silent fail)

- [ ] Tests are CI-runnable (mockable LLM if needed for speed)
- [ ] Test report shows breakdown per group

### Implementation Notes

- For LLM tests: option to record real responses then replay (avoid hitting API in CI)
- For latency: separate "real" suite vs "fast" suite for CI
- Failures should be informative: "Query X expected intent Y, got Z (confidence W)"

### Definition of Done

- All 30 tests written and passing initially
- CI integration (GitHub Action runs on PR)
- Failure of any test blocks merge

### Labels
`phase-3.5` `story` `testing` `priority-critical`

---

## [Story] P3.5-S19: Performance and cost verification

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~0.5 day | **Depends on:** Epic 3 complete

### User Story

As a product owner, I need data confirming Phase 3.5 stays within performance and cost budgets, so that scaling to 1000+ users won't surprise us with unexpected bills or laggy UX.

### Acceptance Criteria

- [ ] Performance benchmarks measured and documented:
  - Rule classifier: p50 <50ms, p99 <200ms
  - LLM classifier: p50 <1.5s, p99 <3s
  - End-to-end (text → response): p50 <1s, p99 <3s
  - Voice end-to-end (audio → response): p50 <5s, p99 <8s

- [ ] Cost projections:
  - Cost per query (current): documented
  - Projected monthly cost at 1000 queries/day: <$5
  - Projected monthly cost at 10000 queries/day: <$30
  - Cache hit rate: documented (should reduce duplicate LLM calls)

- [ ] Run load test: 100 queries in 60 seconds
  - System remains responsive
  - No errors
  - LLM rate limiting handled if hit

- [ ] Document findings in `docs/current/phase-3.5-perf-report.md`

### Implementation Notes

- Use existing analytics events for measurement
- For load test: tool of choice (locust, simple Python script)
- Don't run load test on production DB — use staging

### Definition of Done

- Perf report committed
- All targets met OR mitigation plan documented
- Cost stays within budget

### Labels
`phase-3.5` `story` `testing` `performance`

---

## [Story] P3.5-S20: User testing with 5 real users

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~3 days (1 week elapsed) | **Depends on:** P3.5-S17, P3.5-S18

### Reference
📖 [phase-3.5-detailed.md § 3.3 — User Testing Protocol](../current/phase-3.5-detailed.md)

### User Story

As a product owner, I need real user feedback to verify Phase 3.5 actually delivers the "feel intelligent" experience — automated tests can't capture subjective UX quality.

### Acceptance Criteria

- [ ] Recruit 5 users covering wealth levels:
  - 2 Starter (young, building wealth)
  - 2 Mass Affluent (mid-career professional)
  - 1 HNW (executive/entrepreneur)

- [ ] Each user uses Bé Tiền with Phase 3.5 for 1 week
- [ ] Track usage metrics for each user (% rule matches, LLM rate, query types)

- [ ] **Day 7 interview** with each user (30 min):
  - Did Bé Tiền understand your questions?
  - Any moment where it felt smart? When did it disappoint?
  - Was it ever wrong in dangerous ways (executed wrong action)?
  - Compared to expectation, where on 1-10 scale?

- [ ] Document insights:
  - Top 5 query patterns NOT in current rules (add to backlog)
  - Top 3 confusing responses (refine wording)
  - Top success moments (validation for marketing later)

- [ ] **Success criteria:**
  - 4/5 users rate experience ≥7/10
  - 0 users reported dangerous wrong actions
  - 3/5 users said "Bé Tiền hiểu mình tốt hơn rồi"

### Implementation Notes

- Have users use a separate bot instance (not affecting other users)
- Backup their data before testing
- Pay/thank users appropriately (they're providing real value)
- Use real queries from log analysis to drive testing scenarios

### Definition of Done

- Interviews completed and transcribed
- Insights document committed
- Decision: ship to public beta OR iterate? Documented with rationale

### Labels
`phase-3.5` `story` `testing` `priority-critical`

---

## [Story] P3.5-S21: Pattern improvement based on unclear queries

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~1 day | **Depends on:** P3.5-S20

### Reference
📖 [phase-3.5-detailed.md § Bẫy #6 — No Analytics](../current/phase-3.5-detailed.md)

### User Story

As a product owner, I want to mine insights from analytics data on `intent_unclear` events to refine our rule patterns and prompts, so that the system continuously improves and rule-classification rate increases over time.

### Why This Story

Real user queries always reveal patterns we didn't anticipate. The classifier ships with ~30 patterns, but week 1 of real usage will surface new phrasings. This story creates a **feedback loop** so the system gets smarter from real data.

### Acceptance Criteria

- [ ] Analyze top 20 unclear queries from analytics (P3.5-S11 setup)
- [ ] For each pattern, decide:
  - **Add new rule pattern** → update `intent_patterns.yaml`
  - **Improve LLM prompt** → if LLM also struggled
  - **Add to fixture file** → if pattern is canonical now
  - **Mark as truly OOS** → update OOS messages

- [ ] At minimum, **add 10 new rule patterns** based on findings
- [ ] **Re-run automated test suite (P3.5-S18)** — should still pass
- [ ] Re-run user testing metrics — verify rule-match rate increased

- [ ] Document the improvement loop in `docs/current/phase-3.5-improvement-process.md`:
  - Where to find unclear queries (admin endpoint)
  - How to add patterns (YAML format)
  - How to verify improvement
  - Cadence: weekly review during early launch

### Implementation Notes

- This is a SHORT story but TIME-INVESTED (real data analysis)
- Use admin endpoint from P3.5-S11
- Pair with someone for pattern review (catch biases)

### Definition of Done

- 10+ new patterns added
- Rule-match rate increased measurably (e.g., 75% → 80%)
- Documentation for ongoing improvement committed

### Labels
`phase-3.5` `story` `nlu` `improvement`

---

## [Story] P3.5-S22: Document Phase 3.5 lessons learned

**Type:** Story | **Epic:** Epic 4 | **Estimate:** ~0.5 day | **Depends on:** All other stories complete

### User Story

As a future-self (or future team member), I want a concise post-mortem document capturing what worked, what didn't, and what surprised us during Phase 3.5, so that Phase 4+ can build on insights instead of repeating mistakes.

### Acceptance Criteria

- [ ] File `docs/current/phase-3.5-retrospective.md` exists with sections:

**1. What Worked Well:**
- Tier C (rule-first, LLM-fallback) cost analysis
- Pattern matching approach for Vietnamese
- Confidence-based dispatching
- Test fixtures from Day 1
- Re-using Phase 3A services

**2. What Was Harder Than Expected:**
- (Filled in during retro)
- Common patterns: tone consistency, edge cases, etc.

**3. What Surprised Us:**
- Top 3 unexpected findings from user testing or implementation

**4. Patterns to Reuse in Future Phases:**
- Architectural patterns
- Testing approaches
- Anti-patterns to avoid

**5. Open Questions / Tech Debt:**
- Things deferred to Phase 4+
- Scaling concerns

**6. Metrics Achieved:**
- Final cost per query
- Rule vs LLM ratio
- User satisfaction score
- Performance numbers

- [ ] Document referenced in `docs/README.md` updates
- [ ] Insights shared with future Phase 4 planning

### Implementation Notes

- Brief but honest — no sugar-coating issues
- Concrete numbers where possible
- Format: bullet points, not essays

### Definition of Done

- Retro document committed
- Linked from main docs README
- Used as input for Phase 4 planning

### Labels
`phase-3.5` `story` `documentation`

---

# 🎯 Epic Dependencies Graph

```
Epic 1 (Week 1) — Foundation
  P3.5-S1 → P3.5-S2 → P3.5-S3 → P3.5-S4 → P3.5-S5 → P3.5-S6
                                                         ↓
Epic 2 (Week 2) — LLM & Clarification
  P3.5-S7 → P3.5-S8 → P3.5-S9
        ↓
       P3.5-S10  P3.5-S11
                                                         ↓
Epic 3 (Week 3a) — Personality
  P3.5-S12 → P3.5-S13
  P3.5-S14 (parallel — Advisory)
  P3.5-S15  P3.5-S16
                                                         ↓
Epic 4 (Week 3b) — QA
  P3.5-S17  P3.5-S18  P3.5-S19
        ↓        ↓
       P3.5-S20 → P3.5-S21 → P3.5-S22
```

**Parallel opportunities:**
- Epic 1: P3.5-S2 (test fixtures) and P3.5-S3 (extractors) can be done in parallel
- Epic 2: P3.5-S10 and P3.5-S11 can run parallel after P3.5-S7
- Epic 3: P3.5-S14 (advisory) is mostly independent of S12/S13
- Epic 4: P3.5-S17, S18, S19 can all run parallel before user testing

---

# 📝 Setup Instructions for Phase 3.5

## Step 1: Create Epic Issues First

Order matters! Create the 4 Epic issues first, get their numbers, THEN create stories that reference them.

### Epic Order

1. Create `Epic 1: Intent Foundation & Patterns` → note issue # (e.g., #150)
2. Create `Epic 2: LLM Fallback & Clarification` → note issue # (e.g., #151)
3. Create `Epic 3: Personality & Advisory` → note issue # (e.g., #152)
4. Create `Epic 4: Quality Assurance` → note issue # (e.g., #153)

## Step 2: Create Story Issues

For each story, copy from this file, add Epic reference at top:
```
**Parent Epic:** #150 (Epic 1: Intent Foundation)
```

GitHub will auto-link bidirectionally.

## Step 3: Update Epic Task Lists

After all stories created, edit each Epic body. Replace `#XXX` with actual story numbers:

```markdown
## Stories in this Epic

- [ ] #154 [Story] P3.5-S1: Define intent types
- [ ] #155 [Story] P3.5-S2: Create test fixtures
...
```

GitHub will track completion as stories close.

## Step 4: Configure Project Board

Add columns as described in "GitHub Configuration" section above.

## Step 5: Start Implementation

Begin with **P3.5-S1** (no dependencies). Follow the dependency graph from there.

---

# 💡 Tips for Implementing with Claude Code

## Per-Story Implementation Pattern

For each story, prompt Claude Code with:

```
Implement #XXX [Story P3.5-Sn] following these references:
1. Read docs/current/phase-3.5-detailed.md (architecture)
2. Read docs/issues/active/issue-XXX.md (this story)
3. Check docs/issues/closed/by-phase/phase-3a/ for related patterns

Specific focus:
- All Acceptance Criteria items
- Test cases listed
- Implementation Notes
```

## Test-Driven Pattern

Follow this order for any code-heavy story:

1. **Read AC carefully** — understand all checkboxes
2. **Look at test cases** — write tests FIRST (especially for classifier work)
3. **Implement minimum code** to pass tests
4. **Refactor** for cleanliness
5. **Add docs/comments** for non-obvious decisions
6. **Run full test suite** — ensure no regressions
7. **Update PR with closes #XXX** for auto-close on merge

## When to Pause and Ask

Don't blindly implement if you encounter:
- AC seems contradictory or impossible
- Story requires data/files not present
- Implementation reveals architectural issue
- Testing reveals fundamental gap

Pause, document the issue, ask user. Better one slow issue than fast wrong code.

## Common Pitfalls Specific to Phase 3.5

1. **Pattern overfitting:** Don't write patterns that match exact test fixtures only — they must generalize. Test with paraphrases.

2. **Confidence inflation:** Don't set rule confidence to 1.0 unless it's truly unambiguous. 0.85-0.95 is normal range.

3. **LLM trust:** LLM can hallucinate intents. Always validate output is in IntentType enum. Always have fallback.

4. **Decimal precision:** When extracting amounts, use Decimal not float. Money math errors compound.

5. **Personality leak:** Personality wrapper should NEVER be applied to clarification or error messages. Those need to be neutral and clear.

6. **Order of router checks:** If you put intent pipeline BEFORE wizard mode check, wizards break. Order matters.

---

**Phase 3.5 transforms Bé Tiền from "menu app" to "AI assistant that understands me." This is the moment of truth for the product.** 

**Good luck implementing! 🚀💚**
