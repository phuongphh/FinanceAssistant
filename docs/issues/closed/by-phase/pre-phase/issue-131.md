# Issue #131

[Story] P3.5-S18: Build automated test suite for 30 canonical queries

**Parent Epic:** #113 (Epic 4: Quality Assurance)

## User Story
As a developer, tôi cần automated test suite covering 30 canonical query types, so future changes to patterns hoặc LLM prompts có thể validated mà không cần manual testing.

## Acceptance Criteria
- [ ] File `tests/test_intent/test_canonical_queries.py`
- [ ] 30 test cases theo 5 groups:
  - **Group A (10):** Direct queries — rule match, confidence ≥0.85
  - **Group B (5):** Indirect queries — LLM match, confidence ≥0.7
  - **Group C (4):** Action queries — confirmation flow
  - **Group D (4):** Advisory — advisory handler
  - **Group E (7):** Edge cases — graceful handling
- [ ] Tests assert: correct intent, correct parameters, non-empty response, latency ≤ threshold
- [ ] Group success thresholds:
  - Group A: ≥95%
  - Group B: ≥80%
  - Group C: ≥85%
  - Group D: ≥80%
  - Group E: 100% graceful (no exception, no silent fail)
- [ ] CI-runnable (mockable LLM cho speed)
- [ ] Failure message: "Query X expected intent Y, got Z (confidence W)"
- [ ] GitHub Action runs on PR — failure blocks merge

## Estimate: ~1 day
## Depends on: Epic 3 complete
