# Issue #76

[P3A-18] Build storytelling handler (text + voice input)

## Epic
Epic 3 — Storytelling Expense | **Week 3** | Depends: P3A-17 | Blocks: P3A-19

## Description
Handler cho storytelling mode. Nhận text hoặc voice, extract giao dịch, show confirmation. User nói chuyện tự nhiên — bot extract.

## Acceptance Criteria
- [ ] Handler `start_storytelling()` — enter storytelling mode, prompt user
- [ ] Handler `handle_storytelling_input()` — accept text OR voice message
- [ ] Voice flow: download audio → call Whisper → transcribe → show transcript "🎤 Mình nghe: ..."
- [ ] Call `extract_transactions_from_story()` với threshold từ user settings
- [ ] Store pending transactions in `context.user_data["pending_transactions"]`
- [ ] Build confirmation message với list rõ ràng
- [ ] Empty result: "Mình không thấy giao dịch nào vượt threshold {X}đ"
- [ ] needs_clarification: bot hỏi thêm từng item
- [ ] Auto-exit storytelling mode sau 10 phút không có input
- [ ] Error handling: API fail → ấm áp, đề nghị thử lại
- [ ] Command `/story` hoặc `/kechuyen` trigger mode

## Technical Notes
- Mode state: `context.user_data["storytelling_mode"] = True`
- Reuse `transcribe_vietnamese()` từ archive nếu có
- Voice file cleanup sau process

## Estimate
~1 day

## Reference
`docs/current/phase-3a-detailed.md` § 3.3
