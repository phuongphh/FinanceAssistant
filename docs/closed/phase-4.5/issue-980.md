# Issue #980

[Phase 4.5 / E5] 5.2 — Broadcast script one-time

`scripts/send_reengagement_broadcast.py`: cohort dormant (extract `_classify_status` từ `api/admin/users.py` ra service dùng chung), Notifier port, copy "Bé Tiền giờ trả lời được câu này…" ở content YAML, set `reengagement_broadcast_at`. `--dry-run` bắt buộc có (in số đếm, không gửi); chạy thật cần `--confirm`.

**DoD:**
- [ ] Dry-run đếm đúng
- [ ] Chạy 2 lần không gửi trùng
- [ ] Copy pass vi-localization-checker
- [ ] **CHỈ chạy thật sau khi E1-E3 live** (ghi rõ trong runbook đầu script)

⚠️ Chặn bởi issue 4.2 (migration mang cột `reengagement_broadcast_at`) và E1+E2+E3 live.

Epic: #963 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
