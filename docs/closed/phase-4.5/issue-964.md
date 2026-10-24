# Issue #964

[Phase 4.5 / E3] 3.1 — clarity_service.compute_clarity()

`backend/services/decision/clarity_service.py` — score 0-100 + component breakdown (asset coverage/freshness, income streams, expense history ≥1 tháng, goals). Deterministic, không LLM, <100ms, flush-only.

**DoD:**
- [ ] Unit test 4 profile (user trống / chỉ asset / asset+income / đầy đủ)
- [ ] Score đơn điệu tăng khi thêm data

Epic: #961 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
