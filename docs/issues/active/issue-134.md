# Issue #134: [Story] P3.5-S21: Pattern improvement based on unclear queries

**GitHub:** https://github.com/phuongphh/FinanceAssistant/issues/134  
**Status:** Open

---

**Parent Epic:** #113 (Epic 4: Quality Assurance)

## User Story
As a product owner, tôi muốn mine insights từ analytics `intent_unclear` events để refine rule patterns và prompts, so the system gets smarter from real data.

## Tại Sao Story Này
Real user queries luôn reveal patterns không anticipated. Classifier ships với ~30 patterns, nhưng week 1 real usage sẽ surface new phrasings. Story này tạo **feedback loop** để system tự cải thiện.

## Acceptance Criteria
- [ ] Analyze top 20 unclear queries từ analytics (P3.5-S11)
- [ ] Mỗi pattern, quyết định:
  - **Add new rule pattern** → update `intent_patterns.yaml`
  - **Improve LLM prompt** → nếu LLM cũng fail
  - **Add to fixture file** → nếu là canonical pattern
  - **Mark as OOS** → update OOS messages
- [ ] **Minimum: add 10 new rule patterns** dựa trên findings
- [ ] Re-run automated test suite (P3.5-S18) — phải vẫn pass
- [ ] Rule-match rate measurably increased
- [ ] Document improvement loop trong `docs/current/phase-3.5-improvement-process.md`:
  - Tìm unclear queries ở đâu (admin endpoint)
  - Cách add patterns (YAML format)
  - Verify improvement như thế nào
  - Cadence: weekly review during early launch

## Estimate: ~1 day
## Depends on: P3.5-S20
