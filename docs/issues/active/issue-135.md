# Issue #135: [Story] P3.5-S22: Document Phase 3.5 lessons learned (retrospective)

**GitHub:** https://github.com/phuongphh/FinanceAssistant/issues/135  
**Status:** Open

---

**Parent Epic:** #113 (Epic 4: Quality Assurance)

## User Story
As a future-self (hoặc future team member), tôi muốn concise post-mortem document capturing what worked, what didn't, và what surprised us, so Phase 4+ can build on insights instead of repeating mistakes.

## Acceptance Criteria
- [ ] File `docs/current/phase-3.5-retrospective.md` với sections:

**1. What Worked Well**
- Tier C (rule-first, LLM-fallback) cost analysis
- Pattern matching approach cho Vietnamese
- Confidence-based dispatching
- Test fixtures từ Day 1
- Re-using Phase 3A services

**2. What Was Harder Than Expected**
- (Filled in during retro)

**3. What Surprised Us**
- Top 3 unexpected findings

**4. Patterns to Reuse in Future Phases**
- Architectural patterns, testing approaches, anti-patterns

**5. Open Questions / Tech Debt**
- Things deferred to Phase 4+, scaling concerns

**6. Metrics Achieved**
- Final cost per query, rule vs LLM ratio, user satisfaction, performance numbers

- [ ] Document referenced trong `docs/README.md` updates
- [ ] Used as input cho Phase 4 planning

## Estimate: ~0.5 day
## Depends on: All other stories complete
