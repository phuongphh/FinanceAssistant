# Issue #124: [Story] P3.5-S11: Add analytics for classifier accuracy and cost tracking

**GitHub:** https://github.com/phuongphh/FinanceAssistant/issues/124  
**Status:** Open

---

**Parent Epic:** #111 (Epic 2: LLM Fallback & Clarification)

## User Story
As the product owner, I need visibility vào intent system performance và cost, để identify weak patterns cần improve và verify cost stays <$5/month.

## Acceptance Criteria
- [ ] Track các events với properties:
  - `intent_classified`: intent, confidence, classifier_used (rule|llm|none), latency_ms
  - `intent_handler_executed`: intent, handler_name, success, error
  - `intent_unclear`: raw_text, suggested_intents (top 3)
  - `intent_clarification_sent`: original_intent, clarification_type
  - `intent_clarification_resolved`: original_intent, final_intent, time_to_resolve_seconds
  - `intent_oos_declined`: raw_text, oos_category
  - `llm_classifier_call`: input_tokens, output_tokens, latency_ms, cost_usd
- [ ] Daily aggregation (cron job):
  - Total queries handled
  - Rule vs LLM split (%)
  - Confidence histogram
  - Top unclear queries (raw_text, count)
  - Total LLM cost yesterday
  - Average latency
- [ ] Mini App admin endpoint `/miniapp/api/intent-metrics`:
  - Daily aggregation
  - Top 20 unclear queries (cho pattern improvement)
  - Cost trend (7d, 30d)
- [ ] Alert logging khi:
  - LLM cost yesterday > $0.50
  - Rule classifier rate <50% for 3+ days
  - Unclear rate >20% for 3+ days

## Estimate: ~1 day
## Depends on: P3.5-S7, P3.5-S8
