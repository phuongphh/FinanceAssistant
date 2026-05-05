# Phase 3.7 — GitHub Issues (Epics + User Stories)

> **Purpose:** 3 Epics chứa 12 User Stories — sẵn sàng copy-paste vào GitHub.  
> **Format:** Epic = issue cha có task list link tới Stories. Stories = issue con với AC chi tiết.  
> **Reference:** Mỗi story link về [phase-3.7-detailed.md](./phase-3.7-detailed.md)

---

## 📊 Overview

| Epic | Tuần | Stories | Goal |
|------|------|---------|------|
| Epic 1: Tool Foundation & DB-Agent | 1 | 5 stories | Tier 2 working — handle filter/sort/aggregate queries |
| Epic 2: Premium Reasoning & Orchestrator | 2 | 4 stories | Tier 3 + routing — handle multi-step reasoning |
| Epic 3: Polish, Audit & Testing | 3 | 3 stories | Production-ready agent system |

**Total:** 12 user stories across 3 epics, ~3 weeks of work.

---

## 🏷️ GitHub Labels

**Phase 3.7 specific:**
- `phase-3.7` (color: orange)
- `epic` (existing)
- `story` (existing)
- `agent` (specific area)
- `ai-llm` (existing)
- `architecture` (for foundational work)

---

## 🔗 GitHub Configuration

Same workflow như Phase 3.5/3.6. Epic body has task list with `#XXX` placeholders for story numbers.

---

# Epic 1: Tool Foundation & DB-Agent (Tier 2)

> **Type:** Epic | **Phase:** 3.7 | **Week:** 1 | **Stories:** 5

## Overview

Build the foundational tool system + Tier 2 DB-Agent that handles filter, sort, aggregate, and comparison queries. By end of Epic 1, the **critical bug** ("Mã đang lãi?" returning ALL stocks) is fixed.

## Why This Epic Matters

Phase 3.5 plateaus at simple queries. Real users want filtered/sorted views ("top 3 mã lãi", "tài sản trên 1 tỷ"). Tools provide structured data manipulation that LLM can call. This Epic builds tools + Tier 2 agent that uses them.

## Success Definition

When Epic 1 is complete:
- ✅ 5 tools implemented + unit tested (get_assets, get_transactions, compute_metric, compare_periods, get_market_data)
- ✅ DB-Agent translates Vietnamese queries → tool calls correctly
- ✅ **THE critical test passes:** "Mã chứng khoán nào của tôi đang lãi?" returns ONLY gainers
- ✅ Tier 2 average latency <3 seconds
- ✅ Tier 2 cost <$0.0005 per query

## Stories in this Epic

> Replace `#XXX` with actual issue numbers after creating GitHub issues.

- [ ] #XXX [Story] P3.7-S1: Define tool schemas with Pydantic
- [ ] #XXX [Story] P3.7-S2: Implement GetAssets and GetTransactions tools
- [ ] #XXX [Story] P3.7-S3: Implement ComputeMetric, ComparePeriods, GetMarketData tools
- [ ] #XXX [Story] P3.7-S4: Build DB-Agent with DeepSeek function calling
- [ ] #XXX [Story] P3.7-S5: Implement Tier 2 response formatters

## Out of Scope (for Epic 1)

- ❌ Tier 3 reasoning agent — Epic 2
- ❌ Orchestrator routing — Epic 2
- ❌ Streaming response — Epic 2
- ❌ Production cutover — Epic 3

## Dependencies

- ✅ Phase 3.5 complete (provides existing handlers + services to wrap)
- ✅ Phase 3.6 complete (menu working, no conflict)

## Reference

📖 [phase-3.7-detailed.md § Tuần 1](./phase-3.7-detailed.md)

### Labels
`phase-3.7` `epic` `agent` `architecture` `priority-critical`

---

## [Story] P3.7-S1: Define tool schemas with Pydantic

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** None

### Reference
📖 [phase-3.7-detailed.md § 1.1 — Tool Schema Design](./phase-3.7-detailed.md)

### User Story

As a developer building agent tools, I need typed Pydantic schemas for all tool inputs and outputs so that LLM gets clear JSON schemas, validation prevents bad calls, and tests have reusable models.

### Why This Story Comes First

Schemas shape capability. Loose schemas = LLM picks wrong args = bugs. Strict typed schemas = LLM picks correct args = success. Time invested here saves debugging later.

### Acceptance Criteria

- [ ] File `app/agent/tools/schemas.py` exists
- [ ] **Enums defined:**
  - `AssetType` (stock, real_estate, crypto, gold, cash)
  - `SortOrder` (value_asc/desc, gain_asc/desc, gain_pct_asc/desc, name, created_desc)
  - `TransactionCategory` (food, transport, housing, ...)
  - `MetricName` (saving_rate, net_worth_growth, portfolio_total_gain, ...)
- [ ] **Filter models:**
  - `NumericFilter` with gt/gte/lt/lte/eq
  - `AssetFilter` (asset_type, ticker, value, gain_pct)
  - `TransactionFilter` (category, date range, amount)
- [ ] **Tool input models** (5 tools):
  - `GetAssetsInput` (filter, sort, limit)
  - `GetTransactionsInput` (filter, sort, limit)
  - `ComputeMetricInput` (metric_name, period_months)
  - `ComparePeriodsInput` (metric, period_a, period_b)
  - `GetMarketDataInput` (ticker, period)
- [ ] **Tool output models** (5 tools):
  - `GetAssetsOutput` with `AssetItem`
  - `GetTransactionsOutput` with `TransactionItem`
  - `MetricResult`
  - `ComparisonResult`
  - `MarketDataPoint`
- [ ] All schemas have **descriptive Field() descriptions** (used by LLM)
- [ ] All schemas pass `model_json_schema()` without errors
- [ ] Decimal used for money (never float)

### Test Plan

```python
def test_schemas_serialize():
    schema = GetAssetsInput.model_json_schema()
    assert "filter" in schema["properties"]

def test_filter_validation():
    f = NumericFilter(gt=0)
    assert f.gt == 0
    
def test_decimal_for_money():
    item = AssetItem(name="VNM", asset_type="stock", current_value=Decimal("1000000"))
    assert isinstance(item.current_value, Decimal)
```

### Definition of Done

- All schemas defined with proper types
- JSON schema generation works
- Type checks pass (mypy strict mode)
- Used in subsequent stories without modification

### Labels
`phase-3.7` `story` `architecture` `priority-critical`

---

## [Story] P3.7-S2: Implement GetAssets and GetTransactions tools

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1.5 days | **Depends on:** P3.7-S1

### Reference
📖 [phase-3.7-detailed.md § 1.2 — Tool Implementations](./phase-3.7-detailed.md)

### User Story

As an agent processing the query "Mã chứng khoán nào của tôi đang lãi?", I need a `get_assets` tool that wraps existing AssetService and adds filter/sort/limit capability so I can return only the assets matching user's criteria.

### Acceptance Criteria

- [ ] File `app/agent/tools/base.py` with `Tool` ABC + `ToolRegistry`
- [ ] `Tool` abstract class with: name, description, input_schema, output_schema, execute(), to_openai_function()
- [ ] **GetAssetsTool implemented** in `app/agent/tools/get_assets.py`:
  - Wraps existing `AssetService.get_user_assets()`
  - Applies filter (asset_type, ticker, value, gain_pct)
  - Applies sort (8 sort orders)
  - Applies limit (1-100)
  - Computes gain/gain_pct on the fly
  - Returns Pydantic-validated `GetAssetsOutput`
  - **Description for LLM has 5+ examples** (critical for accurate tool selection)

- [ ] **GetTransactionsTool implemented** in `app/agent/tools/get_transactions.py`:
  - Wraps existing `TransactionService.get_by_date_range()`
  - Applies filter (category, date_from, date_to, amount)
  - Applies sort (date_desc, amount_desc, amount_asc)
  - Applies limit (1-200)
  - Returns Pydantic-validated `GetTransactionsOutput`

- [ ] **Critical test passes:**
  ```python
  async def test_get_assets_winners_only():
      # Setup: portfolio with VNM +10%, HPG -5%, NVDA +20%, FPT -3%
      tool = GetAssetsTool()
      result = await tool.execute(
          GetAssetsInput(
              filter=AssetFilter(asset_type="stock", gain_pct=NumericFilter(gt=0))
          ),
          user
      )
      # Should return ONLY VNM and NVDA
      assert result.count == 2
      assert all(a.gain_pct > 0 for a in result.assets)
  ```

- [ ] All 8 sort orders tested
- [ ] Filter combinations tested (asset_type + gain_pct, value range, etc.)
- [ ] Edge cases: empty result, asset without cost_basis, NULL values

### Implementation Notes

- **DO NOT modify AssetService** — wrap it, extend on top
- Use `Decimal` arithmetic for money (no float errors)
- For ticker filter, normalize case (`.upper()`)
- For gain_pct filter, only include assets with cost_basis (skip NULL gain_pct)

### Definition of Done

- Both tools implemented + unit tested
- Critical winner test passes
- Description quality verified (LLM-readable)
- Coverage >90%

### Labels
`phase-3.7` `story` `agent` `priority-critical`

---

## [Story] P3.7-S3: Implement remaining 3 tools

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1.5 days | **Depends on:** P3.7-S1

### Reference
📖 [phase-3.7-detailed.md § 1.2 — Tool Implementations](./phase-3.7-detailed.md)

### User Story

As an agent answering aggregate, comparison, and market queries, I need tools for compute_metric, compare_periods, and get_market_data so users can ask "Tổng lãi portfolio?", "Tháng này vs tháng trước?", "VNM giá?".

### Acceptance Criteria

- [ ] **ComputeMetricTool** in `app/agent/tools/compute_metric.py`:
  - Accepts metric_name + period_months
  - Implements at least: saving_rate, net_worth_growth, portfolio_total_gain, average_monthly_expense, expense_to_income_ratio
  - Returns `MetricResult` with value, unit, context
  - Reuses Phase 3A/3.5 calculation logic where exists
  - For new metrics, implements clean computation

- [ ] **ComparePeriodsTool** in `app/agent/tools/compare_periods.py`:
  - Accepts metric (expenses/income/net_worth/savings) + period_a + period_b
  - Computes diff_absolute and diff_percent
  - Returns `ComparisonResult`
  - Handles edge case: period has no data

- [ ] **GetMarketDataTool** in `app/agent/tools/get_market_data.py`:
  - Accepts ticker + period
  - Calls Phase 3.5 MarketService
  - Adds personal context if user owns ticker (quantity, holding_value)
  - Returns `MarketDataPoint`
  - Handles unknown ticker gracefully

- [ ] **All 3 tools registered in ToolRegistry**

- [ ] Test each tool with realistic scenarios:
  - ComputeMetric: saving_rate for Hà → reasonable %
  - ComparePeriods: this_month vs last_month expenses → diff calculated
  - GetMarketData: VNM → returns price, with Hà's holding info

### Implementation Notes

- ComputeMetric is most complex — keep metric calculations in pure functions, not in tool execute()
- ComparePeriods may need to call get_transactions internally (composition OK)
- GetMarketData stub OK if Phase 3B not done yet — return placeholder data with note

### Definition of Done

- All 3 tools implemented + tested
- Registered in ToolRegistry
- Each tool covers ≥3 realistic test cases

### Labels
`phase-3.7` `story` `agent` `priority-high`

---

## [Story] P3.7-S4: Build DB-Agent with DeepSeek function calling

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1.5 days | **Depends on:** P3.7-S2, P3.7-S3

### Reference
📖 [phase-3.7-detailed.md § 1.3 — Tier 2 DB-Agent](./phase-3.7-detailed.md)

### User Story

As Bé Tiền receiving "Top 3 mã lãi nhiều nhất", I need a DB-Agent that uses DeepSeek's function calling to translate this Vietnamese query into a `get_assets(filter, sort, limit)` call automatically.

### Acceptance Criteria

- [ ] File `app/agent/tier2/db_agent.py` with `DBAgent` class
- [ ] Uses DeepSeek API via OpenAI SDK
- [ ] System prompt includes:
  - Vietnamese instructions
  - Tool selection rules
  - 5+ concrete examples (query → tool call mapping)
  - Output format specification
- [ ] `answer(query, user)` method:
  - Sends query + tools schema to DeepSeek
  - Uses `tool_choice="auto"` (let LLM pick)
  - `temperature=0.0` for deterministic
  - `max_tokens=500` (cost control)
  - Parses tool call from response
  - Validates args via Pydantic input_schema
  - Executes tool via registry
  - Returns structured result dict

- [ ] Returns dict format:
  ```python
  {
      "success": bool,
      "tool_called": str,
      "tool_args": dict,
      "result": dict (Pydantic dump),
      "error": str (if any),
      "fallback_text": str (if LLM didn't call tool),
  }
  ```

- [ ] **Test queries that MUST work:**
  - "Mã nào đang lãi?" → get_assets with gain_pct > 0 filter
  - "Top 3 mã lãi nhiều nhất" → get_assets sort gain_pct_desc, limit 3
  - "Tài sản trên 1 tỷ" → get_assets with value > 1000000000
  - "Chi cho ăn uống tuần này" → get_transactions with category=food, date_range=this_week
  - "Tổng lãi portfolio" → compute_metric portfolio_total_gain
  - "Tháng này vs tháng trước" → compare_periods

- [ ] Cost per call < $0.0005
- [ ] Latency < 2 seconds (DB-Agent only, before tool execution)
- [ ] Error handling:
  - LLM doesn't pick tool → return graceful fallback
  - Invalid args → return validation error
  - API timeout → return clear error message
  - Unknown tool → return error

### Implementation Notes

- Cache LLM responses by query hash (Redis, 5 min) — same query twice = 1 LLM call
- Log full LLM response for debugging
- For Tier 2, take FIRST tool call only (Tier 2 = single-step)

### Definition of Done

- DB-Agent works end-to-end on 10+ test queries
- Cost verified <$0.0005/call
- Latency verified <2s
- Cache reduces repeat call count

### Labels
`phase-3.7` `story` `agent` `ai-llm` `priority-critical`

---

## [Story] P3.7-S5: Implement Tier 2 response formatters

**Type:** Story | **Epic:** Epic 1 | **Estimate:** ~1 day | **Depends on:** P3.7-S4

### Reference
📖 [phase-3.7-detailed.md § 1.3 — Response Formatting](./phase-3.7-detailed.md)

### User Story

As a user receiving the result of "Mã đang lãi?", I want a beautifully formatted response (not raw JSON) — list of winning stocks with current price, gain, and percentage, in Bé Tiền's warm tone.

### Acceptance Criteria

- [ ] File `app/agent/tier2/formatters.py` with `format_db_agent_response()`
- [ ] Format functions for each tool:
  - `format_assets_response(result, user, query)` — list with gain indicators (🟢/🔴)
  - `format_transactions_response(result, user, query)` — chronological list
  - `format_metric_response(result, user)` — metric value + context
  - `format_comparison_response(result, user)` — side-by-side comparison
  - `format_market_response(result, user)` — price + change + personal context
- [ ] **Wealth-level adaptive** (reuse Phase 3.5 logic):
  - Starter: simple language
  - HNW: detailed, professional
- [ ] **Empty state handling:**
  - 0 results → friendly message ("Không có mã nào đang lãi 🤔")
  - 0 assets → suggest adding ("/add_asset")
- [ ] **Bé Tiền personality:**
  - Greeting variation
  - Suggestion at end ("Muốn xem mã đang lỗ không?")
  - User name used naturally
- [ ] **Inline keyboard** for follow-up actions when relevant
- [ ] Test: Same query 3 times → variation in opening, same data
- [ ] Test: Empty result handled gracefully

### Implementation Notes

- Reuse `format_money_short()`, `format_money_full()` from Phase 1
- Reuse personality patterns from Phase 3.5's `query_voice.py`
- For ASSET response with gain, use 🟢 for gain >0, 🔴 for loss
- For ASSET response with sort, mention "top X" if limit applied

### Sample Output

```
✨ Mã chứng khoán đang lãi của Hà:

🟢 NVDA — 6.2 tỷ (+4.2%)
🟢 VHM — 5.4 tỷ (+80%)
🟢 VIC — 1.7 tỷ (+142.9%)
🟢 VPS — 1.4 tỷ (+40%)

Tổng giá trị: 14.7 tỷ

[💡 Xem mã đang lỗ] [📈 Báo cáo chi tiết]
```

### Definition of Done

- All 5 formatters working
- Wealth-level adaptive verified
- Personality wrapper applied
- Sample outputs reviewed by team

### Labels
`phase-3.7` `story` `frontend` `personality`

---

# Epic 2: Premium Reasoning & Orchestrator

> **Type:** Epic | **Phase:** 3.7 | **Week:** 2 | **Stories:** 4

## Overview

Build Tier 3 reasoning agent (Claude Sonnet) for multi-step queries + Orchestrator that routes between Tier 1/2/3. Add streaming for low-latency UX on long Tier 3 responses.

## Why This Epic Matters

Tier 2 handles 25% of new queries (filter/sort/aggregate). Tier 3 handles the remaining 5% — advisory, what-if, planning. These need real reasoning, not tool-calling. Premium LLM justified by query complexity.

## Success Definition

When Epic 2 is complete:
- ✅ Tier 3 answers "Có nên bán FLC?" with multi-step reasoning + disclaimer
- ✅ Orchestrator routes correctly: 90%+ accuracy on tier classification
- ✅ Streaming feels responsive: first chunk <2s
- ✅ Cost stays under $0.001/query average
- ✅ Rate limits prevent abuse (10 Tier 3/hour/user)

## Stories in this Epic

- [ ] #XXX [Story] P3.7-S6: Build Reasoning Agent with Claude Sonnet
- [ ] #XXX [Story] P3.7-S7: Implement Telegram streaming
- [ ] #XXX [Story] P3.7-S8: Build Orchestrator with heuristic routing
- [ ] #XXX [Story] P3.7-S9: Add rate limiting and cost caps

## Dependencies

- ✅ Epic 1 complete

## Reference

📖 [phase-3.7-detailed.md § Tuần 2](./phase-3.7-detailed.md)

### Labels
`phase-3.7` `epic` `agent` `ai-llm` `priority-high`

---

## [Story] P3.7-S6: Build Reasoning Agent with Claude Sonnet

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~2 days | **Depends on:** Epic 1 complete

### Reference
📖 [phase-3.7-detailed.md § 2.1 — Tier 3 Reasoning Agent](./phase-3.7-detailed.md)

### User Story

As a user asking "Có nên bán FLC để cắt lỗ không?", I need a reasoning agent that can call multiple tools (check current loss, market trend, opportunity cost) then provide a balanced framework with options (not specific buy/sell advice).

### Acceptance Criteria

- [ ] File `app/agent/tier3/reasoning_agent.py` with `ReasoningAgent` class
- [ ] Uses **Anthropic Claude Sonnet** (claude-sonnet-4-5-20250929 or latest)
- [ ] **Multi-round tool use loop:**
  - Up to 5 tool calls per query
  - Each tool call: validate args, execute, append result to messages
  - Hard cap MAX_TOOL_CALLS=5 (prevent infinite loops)
- [ ] **System prompt** includes:
  - Bé Tiền personality (Vietnamese, warm)
  - Wealth-level context (adapted per user)
  - Hard constraints (no specific stock recs, no profit promises, disclaimer)
  - Tool descriptions
  - User context (name, level, net worth)
- [ ] **Streaming support:**
  - `answer_streaming(query, user, on_chunk)` method
  - Calls `on_chunk` callback as text chunks arrive
  - Allows TelegramStreamer to send chunks to user
- [ ] **Disclaimer enforcement:**
  - Auto-append if not present in response
  - Standard text: "Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư chuyên nghiệp"
- [ ] **Compliance test:**
  - Send "có nên mua VNM không?" 10 times
  - Response should NEVER include specific buy/sell recommendation
  - Response should ALWAYS include disclaimer
- [ ] Cost per call: ~$0.003-0.008 (acceptable for premium tier)
- [ ] Multi-tool test: query that requires 2+ tool calls answered correctly

### Implementation Notes

- Use Anthropic SDK's tool use feature
- Convert Pydantic schemas to Claude tool format
- For streaming, accumulate tokens in async generator pattern
- Log full conversation for debugging compliance issues

### Test Queries

```python
test_queries = [
    "Có nên bán FLC để cắt lỗ không?",  # what-if + decision
    "Làm thế nào để đạt mục tiêu mua xe trong 2 năm?",  # planning
    "Nếu tôi giảm chi 20% thì tiết kiệm thêm bao nhiêu/năm?",  # what-if
    "Phân tích portfolio của tôi giúp",  # multi-tool synthesis
    "Có nên đầu tư BĐS hay tiếp tục stocks?",  # advisory
]
```

### Definition of Done

- Reasoning agent works on 5+ test queries
- Streaming functional
- Compliance verified (no specific recs, disclaimers always)
- Cost monitored and within budget

### Labels
`phase-3.7` `story` `agent` `ai-llm` `priority-critical`

---

## [Story] P3.7-S7: Implement Telegram streaming

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** P3.7-S6

### Reference
📖 [phase-3.7-detailed.md § 2.3 — Telegram Streaming](./phase-3.7-detailed.md)

### User Story

As a user waiting for an answer to "Có nên bán FLC?", I want to see immediate feedback (typing indicator + initial message) within 2 seconds, then watch the response build progressively, rather than staring at a frozen screen for 10 seconds.

### Acceptance Criteria

- [ ] File `app/agent/streaming/telegram_streamer.py` with `TelegramStreamer` class
- [ ] **`start()` method:**
  - Sends typing indicator (`bot.send_chat_action(chat_id, "typing")`)
  - Sends initial placeholder message: "⏳ Đang phân tích..."
  - Stores message_id for later edits
- [ ] **`send_chunk(text)` method:**
  - Accumulates text in buffer
  - Flushes when EITHER:
    - Buffer ≥50 chars AND last flush ≥0.8s ago
    - Total stream ended
  - Edit message in place via `bot.edit_message_text(message_id, ...)`
- [ ] **`finish()` method:**
  - Final flush of remaining buffer
- [ ] **Error handling:**
  - If edit_message_text fails (rate limit) → fallback to new message
  - If message too long (>4096 chars) → split into multiple messages
  - If network error → log and continue
- [ ] **First chunk latency <2 seconds** (typing indicator + placeholder)
- [ ] **Smooth experience:** updates not too frequent (spam) or too rare (frozen feeling)
- [ ] Markdown parse_mode supported

### Implementation Notes

- Telegram rate limits edits to ~30/min per chat — keep flush_interval ≥0.8s
- Send typing indicator ONCE at start, Telegram auto-clears after 5s
- For very long responses (>4096), split at sentence boundary
- Test on real Telegram (mobile + desktop)

### Test Plan

```python
async def test_streaming_first_chunk_under_2s():
    streamer = TelegramStreamer(...)
    start_time = time.time()
    await streamer.start()
    elapsed = time.time() - start_time
    assert elapsed < 2.0

async def test_streaming_with_long_response():
    streamer = TelegramStreamer(...)
    await streamer.start()
    # Simulate 5000-char streaming response
    for chunk in chunked_text(long_text, 100):
        await streamer.send_chunk(chunk)
        await asyncio.sleep(0.1)
    await streamer.finish()
    # Verify: split into 2+ messages, no errors
```

### Definition of Done

- Streaming feels responsive on Telegram (manual test)
- Edge cases handled (rate limit, long text, errors)
- Visual UX approved

### Labels
`phase-3.7` `story` `frontend` `priority-high`

---

## [Story] P3.7-S8: Build Orchestrator with heuristic routing

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1.5 days | **Depends on:** P3.7-S6, P3.7-S7

### Reference
📖 [phase-3.7-detailed.md § 2.2 — Orchestrator](./phase-3.7-detailed.md)

### User Story

As Bé Tiền receiving any query, I need an orchestrator that decides which tier handles it (Phase 3.5 / Tier 2 / Tier 3) based on heuristic keywords, with cascade fallback when uncertain — so cheap queries stay cheap and expensive queries justified.

### Acceptance Criteria

- [ ] File `content/router_heuristics.yaml` with:
  - `tier2_signals`: filter/sort/aggregate/compare/list keywords
  - `tier3_signals`: should/plan/what_if/advice/why keywords
  - All Vietnamese, regex-compatible
- [ ] File `app/agent/orchestrator.py` with `Orchestrator` class
- [ ] **`route(query, user, telegram_handler)` method:**
  - Step 1: Heuristic classification (`_heuristic_classify`)
  - Step 2: Direct route if strong signal:
    - tier3 signal detected → Tier 3
    - tier2 signal detected → Tier 2
    - ambiguous → cascade
  - Step 3: Cascade (when ambiguous):
    - Try Phase 3.5 first
    - If confidence ≥0.8 → use Phase 3.5
    - Else → escalate to Tier 2
    - If Tier 2 fails → escalate to Tier 3
- [ ] **Heuristic classification accuracy:**
  - On 30 test queries: ≥85% routed correctly first try
  - Cascade catches the 15% misclassified
- [ ] **Tier 3 trigger ONLY for clear reasoning signals:**
  - "có nên" → Tier 3
  - "làm thế nào để" → Tier 3
  - But "tài sản của tôi" → Tier 1 (not Tier 3 by mistake)

- [ ] **Test fixture: 30+ queries with expected tier**
  - Tier 1: 10 queries (simple direct)
  - Tier 2: 15 queries (filter/sort/aggregate/compare)
  - Tier 3: 5 queries (advisory/planning)

### Implementation Notes

- Heuristics use regex via `re.search()`, case-insensitive
- Score-based classification: count signals per tier, highest wins
- For ambiguous, prefer cascade (cheaper) over direct Tier 3
- Cache routing decisions per query hash (small win, but helps)

### Test Plan

```python
@pytest.mark.parametrize("query,expected_tier", load_fixtures())
async def test_routing(query, expected_tier):
    orch = Orchestrator()
    actual_tier = orch._heuristic_classify(query)
    if expected_tier in ("tier1", "ambiguous"):
        assert actual_tier == "ambiguous"  # Both go through cascade
    else:
        assert actual_tier == expected_tier
```

### Definition of Done

- Routing accuracy ≥85% on test fixtures
- Cascade fallback works
- All 3 tiers reachable through orchestrator

### Labels
`phase-3.7` `story` `agent` `architecture` `priority-critical`

---

## [Story] P3.7-S9: Add rate limiting and cost caps

**Type:** Story | **Epic:** Epic 2 | **Estimate:** ~1 day | **Depends on:** P3.7-S8

### Reference
📖 [phase-3.7-detailed.md § 2.4 — Cost & Latency Caps](./phase-3.7-detailed.md)

### User Story

As a product owner, I want hard limits on per-user query rates and per-query costs so that no single user (or buggy code) can spike daily costs unexpectedly.

### Acceptance Criteria

- [ ] File `app/agent/limits.py` with constants:
  - MAX_TOOL_CALLS_PER_QUERY = 5
  - MAX_TOTAL_TOKENS_PER_QUERY = 10000
  - QUERY_TIMEOUT_SECONDS = 30
  - MAX_TIER3_QUERIES_PER_HOUR = 10 (per user)
  - MAX_TOTAL_QUERIES_PER_HOUR = 100 (per user)
- [ ] **Rate limiter** using Redis sliding window:
  - `check_tier3(user_id)` → True if user can make Tier 3 query
  - `check_total(user_id)` → True if user under total limit
- [ ] **Limits enforced in Orchestrator:**
  - Before Tier 3 call, check tier3 rate limit
  - If exceeded, fallback to Tier 2 OR show "đợi 1 lát nhé" message
- [ ] **Reasoning agent enforces:**
  - MAX_TOOL_CALLS=5 hard stop
  - QUERY_TIMEOUT_SECONDS=30 hard stop with `asyncio.wait_for`
- [ ] **Daily cost monitor:**
  - Track total spend in Redis (key: `cost:daily:YYYY-MM-DD`)
  - Alert if >$5/day
  - Hard stop if >$20/day (return graceful error to users)
- [ ] **Test rate limits:**
  - Send 11 Tier 3 queries in 1 hour → 11th rejected
  - Send 101 total queries → 101st rejected

### Implementation Notes

- Redis sliding window: store timestamps in sorted set, count entries in window
- Cost tracked per query in audit log (next story), aggregated nightly
- Failed rate limit shouldn't be silent — tell user politely
- Admin can override limits per user (allowlist)

### Definition of Done

- Rate limits work (verified in test)
- Cost monitoring active
- Hard caps prevent runaway scenarios

### Labels
`phase-3.7` `story` `backend` `priority-high`

---

# Epic 3: Polish, Audit & Testing

> **Type:** Epic | **Phase:** 3.7 | **Week:** 3 | **Stories:** 3

## Overview

Production-ready hardening: audit logging for every agent call, caching for performance + cost, comprehensive testing including the original bug fix, user testing, and documentation.

## Why This Epic Matters

Phase 3.7 introduces complex behavior. Without audit logs, debugging is impossible. Without caching, costs balloon. Without testing, the original bug ("đang lãi" returning ALL stocks) might not be properly fixed.

## Success Definition

When Epic 3 is complete:
- ✅ Every agent invocation logged with cost + latency
- ✅ Cache reduces Tier 2 calls by 30%+ for repeat queries
- ✅ THE critical test passes consistently: "Mã đang lãi?" → only winners
- ✅ User testing positive (≥3 users)
- ✅ Cost dashboard accessible

## Stories in this Epic

- [ ] #XXX [Story] P3.7-S10: Audit logging + cost dashboard
- [ ] #XXX [Story] P3.7-S11: Caching + integration with Phase 3.5
- [ ] #XXX [Story] P3.7-S12: Comprehensive testing + user trial

## Dependencies

- ✅ Epic 1 + Epic 2 complete

## Reference

📖 [phase-3.7-detailed.md § Tuần 3](./phase-3.7-detailed.md)

### Labels
`phase-3.7` `epic` `testing` `priority-high`

---

## [Story] P3.7-S10: Audit logging + cost dashboard

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1 day | **Depends on:** Epic 2 complete

### Reference
📖 [phase-3.7-detailed.md § 3.1 — Audit Logging](./phase-3.7-detailed.md)

### User Story

As a product owner monitoring Phase 3.7 performance, I need detailed audit logs of every agent invocation so I can debug issues, identify expensive query patterns, and verify cost stays within budget.

### Acceptance Criteria

- [ ] **DB model `AgentAuditLog`** in `app/agent/audit.py`:
  - id, user_id, query_text, query_timestamp
  - tier_used, routing_reason
  - tools_called (JSON array), tool_call_count
  - llm_model, input_tokens, output_tokens, cost_usd
  - success, response_preview, error
  - total_latency_ms
- [ ] **Migration** creates `agent_audit_logs` table
- [ ] **Logging integrated** in:
  - DBAgent (Tier 2): log every query
  - ReasoningAgent (Tier 3): log every query
  - Orchestrator: log routing decision
- [ ] **Async logging:** Don't block main path
  - Use background task or fire-and-forget
- [ ] **Admin dashboard endpoint** `/miniapp/api/agent-metrics`:
  - Today's total queries, total cost, latency p95
  - Tier distribution (% Tier 1/2/3)
  - Top 10 most expensive queries today
  - Top 10 slowest queries today
  - Top 10 unclear/failed queries
  - 7-day cost trend
- [ ] **Daily aggregation job:**
  - Cron at 23:59 daily
  - Compute daily metrics
  - Alert if cost >$5

### Implementation Notes

- Use SQLAlchemy session with `nullpool` for fire-and-forget logging
- Cost calc: `(input_tokens / 1M) * input_price + (output_tokens / 1M) * output_price`
- DeepSeek pricing: ~$0.14/1M input, $0.28/1M output
- Claude Sonnet: ~$3/1M input, $15/1M output

### Definition of Done

- All agent calls logged
- Dashboard accessible
- Logs queryable for debugging

### Labels
`phase-3.7` `story` `backend` `analytics`

---

## [Story] P3.7-S11: Caching + integration with Phase 3.5

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~1 day | **Depends on:** Epic 2 complete

### Reference
📖 [phase-3.7-detailed.md § 3.2 — Caching, § 3.3 — Integration](./phase-3.7-detailed.md)

### User Story

As a system, I want to cache agent responses (Tier 2: 5min, Tier 3: 1 hour) and integrate Orchestrator into the existing free-form text handler — so users transparently benefit from agent without breaking existing flows.

### Acceptance Criteria

- [ ] File `app/agent/caching.py` with `AgentCache` class
- [ ] **Tier 2 cache:**
  - Key: `agent:t2:{user_id}:{tool_name}:{args_hash}`
  - TTL: 5 minutes
  - Stores tool result (Pydantic dump)
- [ ] **Tier 3 cache:**
  - Key: `agent:t3:{user_id}:{query_hash}`
  - TTL: 1 hour
  - Stores response text
- [ ] **Cache invalidation:**
  - On asset add/edit/delete → invalidate user's Tier 2 cache
  - On transaction add → invalidate user's Tier 2 cache
- [ ] **Integration with Phase 3.5:**
  - Update `app/bot/handlers/free_form_text.py`:
    - Replace direct intent dispatcher call with `Orchestrator.route(...)`
    - Orchestrator internally falls back to Phase 3.5 dispatcher when needed
- [ ] **No regressions:**
  - All Phase 3.5 free-form queries still work
  - All Phase 3.5 test fixtures pass
- [ ] **Cache hit rate test:**
  - Send same Tier 2 query 5 times in 5 min → 1 LLM call (4 cache hits)
  - Send same Tier 3 query in 1 hour → cached response (no Claude call)

### Implementation Notes

- Use Redis from existing setup
- Hash args with `json.dumps(sort_keys=True)` for consistent keys
- Keep cache keys short (<200 chars)
- Invalidation: pattern delete `agent:t2:{user_id}:*` on data changes

### Definition of Done

- Cache working with measurable hit rate
- No Phase 3.5 regressions
- Orchestrator wired into main handler

### Labels
`phase-3.7` `story` `backend` `integration` `priority-high`

---

## [Story] P3.7-S12: Comprehensive testing + user trial

**Type:** Story | **Epic:** Epic 3 | **Estimate:** ~3 days (1 test + 2 user trial) | **Depends on:** P3.7-S10, P3.7-S11

### User Story

As a product owner shipping Phase 3.7, I need a comprehensive test suite covering the original bug, all 5 query types, performance targets, and cost projections — plus 3 real users validating the experience.

### Acceptance Criteria

- [ ] **Test fixtures** `tests/test_agent/fixtures/tier_test_queries.yaml`:
  - 10 Tier 2 queries (filter, sort, aggregate, compare)
  - 5 Tier 3 queries (advisory, what-if, planning)
  - Each with expected_tier, expected_tool (T2), or expected_min_tools_called (T3)

- [ ] **Test suite** `tests/test_agent/test_orchestrator.py`:
  - Routing accuracy ≥85% on fixtures
  - Cascade fallback works
  - Rate limits enforced
  - Cost caps enforced

- [ ] **CRITICAL TEST PASSES:**
  ```python
  async def test_winners_query_returns_only_winners():
      user = create_test_user_with_mixed_portfolio()
      # Portfolio: VNM +10%, HPG -5%, NVDA +20%, FPT -3%
      
      orchestrator = Orchestrator()
      response = await orchestrator.route("Mã chứng khoán nào của tôi đang lãi?", user, mock_handler)
      
      assert "VNM" in response and "NVDA" in response
      assert "HPG" not in response and "FPT" not in response
  ```

- [ ] **Performance verified:**
  - Tier 2 latency p95 <5s
  - Tier 3 first chunk latency p95 <2s
  - Tier 3 full response latency p95 <10s

- [ ] **Cost verified at scale:**
  - Run 100 mixed queries, measure total cost
  - Should be ~$0.10 (avg $0.001/query)

- [ ] **Regression suite:**
  - All Phase 3.5 fixture queries pass
  - All Phase 3.6 menu interactions work
  - No degradation in existing features

- [ ] **User testing with 3 users:**
  - 1 Mass Affluent (Phương profile)
  - 1 HNW (Anh Tùng profile)
  - 1 Young Professional (Hà profile)
  - Each user spends 30 min testing
  - Tasks include the 5 query types
  - Document feedback

- [ ] **Phase 3.7 retrospective doc** `docs/current/phase-3.7-retrospective.md`:
  - What worked
  - What was harder
  - Cost analysis (actual vs projected)
  - Next steps for Phase 3B / Phase 4

### Definition of Done

- All tests passing
- Critical bug fix verified
- User testing positive
- Retrospective committed

### Labels
`phase-3.7` `story` `testing` `priority-critical`

---

# 🎯 Epic Dependencies Graph

```
Epic 1 (Week 1) — Tools & DB-Agent
  P3.7-S1 → P3.7-S2 (parallel with S3) → P3.7-S4 → P3.7-S5
            P3.7-S3 ↗
                                                       ↓
Epic 2 (Week 2) — Reasoning & Orchestrator
  P3.7-S6 → P3.7-S7 → P3.7-S8 → P3.7-S9
                                                       ↓
Epic 3 (Week 3) — Polish & Test
  P3.7-S10 (parallel with S11) → P3.7-S12
  P3.7-S11 ↗
```

**Parallel opportunities:**
- Epic 1: S2 and S3 can run parallel after S1 (different tools)
- Epic 3: S10 and S11 can run parallel before S12

---

# 📝 Setup Instructions for Phase 3.7

## Step 1: Create Epic Issues First

1. Create `Epic 1: Tool Foundation & DB-Agent` → note issue #
2. Create `Epic 2: Premium Reasoning & Orchestrator` → note #
3. Create `Epic 3: Polish, Audit & Testing` → note #

## Step 2: Create 12 Story Issues

For each story, copy from this file with Parent Epic reference at top.

## Step 3: Update Epic Task Lists

After all stories created, edit Epic bodies replacing `#XXX` with actual numbers.

## Step 4: Start Implementation

Begin with **P3.7-S1** (no dependencies). Follow dependency graph.

---

# 💡 Implementation Tips

## Critical Pattern: Tools Wrap, Don't Replace

Tools wrap existing services from Phase 3A/3.5. **Don't rewrite logic.** Add filter/sort/limit on top.

```python
# GOOD
class GetAssetsTool:
    async def execute(self, input, user):
        all_assets = await AssetService().get_user_assets(user.id)  # Reuse!
        return self._apply_filter_sort_limit(all_assets, input)

# BAD - rewrites query logic
class GetAssetsTool:
    async def execute(self, input, user):
        return await db.query(Asset).filter(...).all()  # Don't do this
```

## Schema Design Quality = LLM Accuracy

Spend extra time on:
- Tool descriptions (LLM uses to pick)
- Field descriptions (LLM uses for args)
- Examples in description (LLM learns from)

5 examples per tool = 95% accuracy. 0 examples = 60% accuracy.

## Heuristic Tuning is Iterative

Initial heuristics catch 70%. Real usage reveals patterns. Plan to update heuristics weekly for first month.

## Cost Monitoring from Day 1

Don't ship without audit log. Cost spike from buggy code can be $50-100 before noticed.

## Common Pitfalls

1. **Cache key collisions** — different users sharing cache (BAD). Always include user_id.
2. **Decimal vs float** — money calc must use Decimal. Float = rounding errors compound.
3. **Tool description shifting** — small wording change → LLM picks differently. Use eval suite.
4. **Streaming over-flush** — every char = rate limit. Min 50 chars + 0.8s interval.
5. **Hard cap forgotten** — LLM loops, $$ burns. Always enforce MAX_TOOL_CALLS.

---

**Phase 3.7 = architectural inflection point. After this, Bé Tiền is a real AI agent. Adding capabilities = adding tools. No more redesign needed. 🚀💚**
