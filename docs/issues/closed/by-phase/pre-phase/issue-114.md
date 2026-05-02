# Issue #114

[Story] P3.5-S1: Define intent types and result data structures

**Parent Epic:** #110 (Epic 1: Intent Foundation & Patterns)

## User Story
As a developer building intent classification, I need typed enums and dataclasses representing intents and their results, so that the system has a stable contract that all classifiers, dispatchers, and handlers can rely on.

## Acceptance Criteria
- [ ] File `app/intent/intents.py` exists với `IntentType` enum
- [ ] Enum chứa đủ 17 intents:
  - **Read (10):** query_assets, query_net_worth, query_portfolio, query_expenses, query_expenses_by_category, query_income, query_cashflow, query_market, query_goals, query_goal_progress
  - **Action (2):** action_record_saving, action_quick_transaction
  - **Advanced (2):** advisory, planning
  - **Meta (4):** greeting, help, unclear, out_of_scope
- [ ] Dataclass `IntentResult` với fields: intent, confidence (0-1), parameters (dict), raw_text, classifier_used ("rule"|"llm"|"none"), needs_clarification, clarification_question
- [ ] Type hints đầy đủ, imports clean, không circular dependencies
- [ ] `IntentType` là `str` Enum để JSON-serializable
- [ ] `field(default_factory=dict)` cho parameters (tránh mutable default trap)
- [ ] Unit tests: serialize, default_params

## Estimate: ~0.5 day
## Depends on: None
## Reference: `docs/current/phase-3.5-detailed.md` § 1.1
