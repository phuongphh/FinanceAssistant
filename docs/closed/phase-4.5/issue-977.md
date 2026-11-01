# Issue #977

[Phase 4.5 / E4] 4.2 — Migration tone_preference + /profile setting

Alembic: `users.tone_preference VARCHAR(10) NULL` (+ `reengagement_broadcast_at TIMESTAMPTZ NULL` gộp cùng migration); ô chỉnh trong /profile; copy ở `content/profile_copy.yaml`. Flag `TONE_DIAL_ENABLED` default `false` → ô ẩn.

**DoD:**
- [ ] Migration sạch
- [ ] Đổi persist
- [ ] NULL → tone mặc định

⚠️ Migration này chặn issue 5.2 (broadcast cần cột `reengagement_broadcast_at`).

Epic: #962 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
