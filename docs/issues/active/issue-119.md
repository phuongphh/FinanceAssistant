# Issue #119: [Story] P3.5-S6: Wire intent pipeline into Telegram message router

**GitHub:** https://github.com/phuongphh/FinanceAssistant/issues/119  
**Status:** Open

---

**Parent Epic:** #110 (Epic 1: Intent Foundation & Patterns)

## User Story
As a user, khi tôi gõ free-form text vào Bé Tiền (không phải wizard, không phải command), tôi muốn message được hiểu và handled. Bot KHÔNG ĐƯỢC show generic menu khi nó có thể hiểu câu hỏi.

## Acceptance Criteria
- [ ] File `app/intent/classifier/pipeline.py` với `IntentPipeline` class
  - Wrap RuleBasedClassifier
  - LLM classifier = None (Epic 2 fills in)
  - Returns IntentResult always (fallback UNCLEAR)
- [ ] File `app/intent/dispatcher.py` với `IntentDispatcher`
  - Map IntentType → Handler
  - confidence > 0.8 → execute
  - 0.5-0.8 → execute (read) / confirm (write) (Epic 2 fleshes out)
  - < 0.5 → friendly unclear message với suggestions
- [ ] File `app/bot/handlers/free_form_text.py`
  - Called khi text không match wizard/command/storytelling
  - pipeline → dispatcher → reply
  - Track `intent_handled` analytics event
- [ ] Update `app/bot/router.py` — add free-form route AFTER existing checks

### Router Order (CRITICAL)
1. Active wizard → wizard handler
2. Storytelling mode → storytelling handler
3. Command (/...) → command handler
4. Free-form text → intent pipeline (**NEW**)

- [ ] **Replace existing "show menu on unknown" fallback** với pipeline
- [ ] Test E2E: "tài sản của tôi có gì?" → list assets
- [ ] Test E2E: "asdkfjh" → friendly unclear message
- [ ] Test E2E: "thời tiết hôm nay" → polite OOS decline
- [ ] **Regression: wizard/storytelling/commands still work**
- [ ] Analytics: `intent_classified`, `intent_handler_executed`, `intent_unclear`

## Estimate: ~1 day
## Depends on: P3.5-S4, P3.5-S5
## Reference: `docs/current/phase-3.5-detailed.md` § 1.5 & 1.6
