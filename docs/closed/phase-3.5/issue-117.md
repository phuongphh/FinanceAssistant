# Issue #117

[Story] P3.5-S4: Implement rule-based pattern matching engine

**Parent Epic:** #110 (Epic 1: Intent Foundation & Patterns)

## User Story
As Bé Tiền, I need to recognize common Vietnamese query patterns instantly without LLM calls, so 75% of queries are handled với zero compute cost và sub-200ms latency.

## Acceptance Criteria
- [ ] File `content/intent_patterns.yaml` với 30+ patterns covering all Phase 3.5 intents
- [ ] Mỗi pattern có: regex, confidence (0-1), optional parameter_extractors
- [ ] Patterns ordered: highest specificity/confidence first
- [ ] File `app/intent/classifier/rule_based.py` với `RuleBasedClassifier` class
- [ ] Method `classify(text) -> IntentResult | None`:
  - Load patterns từ YAML on init (compile once)
  - Iterate patterns, return best match
  - Run parameter extractors khi configured
  - `classifier_used = "rule"`

### Coverage Required
| Intent | Min Patterns |
|--------|-------------|
| query_assets | 4+ |
| query_net_worth | 4+ |
| query_portfolio | 3+ |
| query_expenses | 3+ |
| query_expenses_by_category | 3+ |
| query_income | 3+ |
| query_market | 4+ |
| query_goals | 3+ |
| action_record_saving | 2+ |
| advisory | 4+ |

- [ ] **Test: 11 real queries từ P3.5-S2 fixture classify với confidence ≥0.85**
- [ ] **Test: Out-of-scope queries return None** (no false positives)
- [ ] **Test: 100 queries < 5 seconds total**
- [ ] Handle Vietnamese diacritics + no-diacritic variations

## Estimate: ~1.5 day
## Depends on: P3.5-S1, P3.5-S2, P3.5-S3
## Reference: `docs/current/phase-3.5-detailed.md` § 1.2
