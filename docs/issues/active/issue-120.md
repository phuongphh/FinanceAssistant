# Issue #120

[Story] P3.5-S7: Implement LLM-based intent classifier

**Parent Epic:** #111 (Epic 2: LLM Fallback & Clarification)

## User Story
As Bé Tiền, khi tôi gặp query không match rule nào, tôi cần cheap + fast LLM call để classify intent, so I can still answer instead of saying "didn't understand."

## Acceptance Criteria
- [ ] File `app/intent/classifier/llm_based.py` với `LLMClassifier` class
- [ ] Dùng **DeepSeek API** via OpenAI SDK (cheapest option)
- [ ] Prompt template `LLM_CLASSIFIER_PROMPT` định nghĩa as module constant
- [ ] Method `classify(text) -> IntentResult | None`:
  - response_format={"type": "json_object"}
  - temperature=0.0 (deterministic)
  - max_tokens=200 (cost control)
  - Parse JSON → IntentResult
  - `classifier_used = "llm"`
  - Return None on API errors
- [ ] Prompt instruct LLM: choose from defined enum only, provide confidence 0-1, extract parameters, return out_of_scope cho non-finance
- [ ] Cache LLM responses by query hash (TTL 24h) — same query twice = 1 call
- [ ] Log raw LLM responses cho debugging

### Test Cases (phải classify đúng):
- [ ] "tôi đang giàu cỡ nào" → query_net_worth
- [ ] "tháng này xài hoang chưa" → query_expenses
- [ ] "thời tiết hôm nay" → out_of_scope
- [ ] "show me my stocks" → query_portfolio (English)
- [ ] "tài sản của em" → query_assets (different pronoun)

- [ ] **Cost per call < $0.0005**
- [ ] **Latency < 2 seconds**
- [ ] Integrate vào IntentPipeline: rule first, LLM if rule conf <0.85

## Estimate: ~1 day
## Depends on: Epic 1 complete
## Reference: `docs/current/phase-3.5-detailed.md` § 2.1
