# Issue #585

[Story] P4.2.5-2.2: User growth & DAU chart endpoints

**Parent Epic:** #574 (Epic 2: Analytics APIs)

GET /api/admin/charts/user-growth?days=30 va GET /charts/dau?days=14.

- [ ] user-growth: [{date, cumulative, new_users}]
- [ ] dau: [{date, dau}]
- [ ] Fill missing dates voi 0
- [ ] Cache Redis 30 phut

Close #574
