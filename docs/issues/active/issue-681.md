# Issue #681

[Story 3.3] Action Suggestion Embedded in Twin Flow — Phase 4.3

## Story 1.1 — Rename P10/P50/P90 → Weather Vocabulary

**Parent Epic:** #670 | **Estimate:** 1 day | **Priority:** P0 | **Surface:** Telegram

### User Story
> Là một mass affluent user mới dùng Bé Tiền lần đầu, tôi muốn thấy 3 kịch bản tương lai của mình bằng từ ngữ thân thuộc (thời tiết) thay vì jargon kỹ thuật, để tôi hiểu Twin trong vài giây mà không cần học khái niệm mới.

### Requirements
- [ ] P10 → "🌧️ Khiêm tốn" (kịch bản thận trọng nhất)
- [ ] P50 → "⛅ Bình thường" (kịch bản trung tính, được Bé Tiền tin tưởng nhất)
- [ ] P90 → "☀️ Lạc quan" (kịch bản tốt nhất)
- [ ] Mapping table `twin_label_mapping` với Vietnamese label, emoji, English fallback, internal P-code
- [ ] Power user toggle in Settings: "Hiển thị thuật ngữ kỹ thuật (P10/P50/P90)" — OFF by default
- [ ] Backend response/log vẫn dùng P10/P50/P90 (chỉ presentation layer thay)
- [ ] Migration 4.3.01: tạo `twin_label_mapping` table

### Files Touched
- `content/twin/twin_label_mapping.yaml` (new)
- `apps/twin_renderer/label_resolver.py` (new)
- `apps/twin_renderer/views/scenario_card.py` (modify)
- `db/migrations/4.3.01_twin_label_mapping.sql` (new)

### Definition of Done
- [ ] All AC met
- [ ] Tested on Telegram iOS + Android + Web
- [ ] Content reviewer approved
- [ ] PR closes #674

