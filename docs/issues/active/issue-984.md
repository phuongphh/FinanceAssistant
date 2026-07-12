# Issue #984

[Phase 4.6][E2] Sửa đường rơi "chưa từng kích hoạt" — first-message tự nổ + đo tỉ lệ kích hoạt

## Epic E2 — Sửa Đường Rơi "Chưa Từng Kích Hoạt"

Phase 4.6 (Onboarding Reset cho segment mới). Detail: `docs/current/phase-4.6/phase-4.6-detailed.md` · Issues: `docs/current/phase-4.6/phase-4.6-issues.md`.

Đường rơi lớn nhất của cohort 6/2026 là **"0 tin nhắn"**: user mở bot / bấm `/start` rồi im, không bao giờ gõ lời đầu tiên. E2 để Bé Tiền chủ động mở lời — không chờ user gõ trước — tái dùng nền proactive companion (Phase 4.4 E3): empathy engine + cooldown + quiet hours có sẵn, **không xây scheduler mới**. Toàn bộ nằm sau flag `ACTIVATION_NUDGE_ENABLED` default `false`, đọc ở worker/job edge (KHÔNG service/engine).

### Child issues
- **#2.1** First-message tự nổ: trigger empathy env-free `never_activated` cho user đã `/start` nhưng chưa hoàn tất onboarding và chưa có hoạt động nào ngoài lần mở bot, trong cửa sổ kích hoạt ngắn. Job hourly đọc `ACTIVATION_NUDGE_ENABLED` và truyền `include_activation_nudge` vào engine; ứng viên (user chưa onboard, chưa có expense) được fold thêm vào vòng quét. Copy ở `content/empathy_messages.yaml`, persona warm 22-35, salutation-aware.
- **#2.2** Đo hiệu quả: tag `activation_nudge_sent` (first-message-fired) khi gửi nudge + `activation_first_reply` (user-first-reply) khi user được nudge gõ tin nhắn đầu tiên → dashboard tính tỉ lệ kích hoạt cohort mới. Hook ở worker edge, gated bởi flag (off → zero cost).

### Success criteria
- [ ] Flag off (default) → không gửi nudge, byte-identical hành vi cũ; mọi empathy trigger có sẵn vẫn fire.
- [ ] Flag on → user "0 tin nhắn" nhận first-message tự nổ, tôn trọng cooldown + quiet hours + daily cap.
- [ ] Đo được tỉ lệ kích hoạt: `activation_nudge_sent` vs `activation_first_reply`.
- [ ] Flag đọc ở worker/job edge, KHÔNG trong service/engine; engine env-free.
- [ ] 0 chuỗi tiếng Việt hardcode trong code; 0 term "Decision Engine/CFO/GPS tài chính" user-facing.
- [ ] Toàn bộ test xanh; ruff + layer-contract-checker sạch.
