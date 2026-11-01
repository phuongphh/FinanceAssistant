# Issue #969

[Phase 4.5 / E2] 2.2 — Intent decision_feasibility + handler

Classifier route (pattern + LLM) + `backend/intent/handlers/decision_feasibility.py`; extract (start, target, horizon); thiếu tham số → hỏi lại đúng 1 câu. Flag `PLAN_FEASIBILITY_QA_ENABLED` default `false` đọc ở worker/router; tắt → route advisory cũ.

**DoD:**
- [ ] Integration test câu hỏi → answer
- [ ] Test thiếu tham số
- [ ] Test flag on/off

Epic: #960 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
