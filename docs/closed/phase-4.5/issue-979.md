# Issue #979

[Phase 4.5 / E5] 5.1 — decision_query_log model + ghi log

`backend/models/decision_query_log.py` + migration (user_id UUID NOT NULL indexed, query_type, clarity_score NUMERIC(5,2), success, created_at); handlers E1/E2 ghi qua service flush-only.

**DoD:**
- [ ] Migration sạch
- [ ] Log ghi cả case success=False
- [ ] Append-only

Nuôi gate G1/G2 — chart admin dashboard là Phase 4.6, phase này CHỈ ghi log.

Epic: #963 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
