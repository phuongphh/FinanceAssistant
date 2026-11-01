# Issue #129

[Story] P3.5-S16: Handle voice queries through intent pipeline

**Parent Epic:** #112 (Epic 3: Personality & Advisory)

## User Story
As a user, khi tôi gửi voice message hỏi "tài sản của tôi có gì", tôi muốn Bé Tiền transcribe và answer — không chỉ treat nó là storytelling input.

## Acceptance Criteria
- [ ] Update voice handler từ Phase 3A:
  1. Transcribe audio → text (existing)
  2. Send transcribed text qua intent pipeline (**mới**)
  3. Nếu intent là `unclear` VÀ user trong storytelling mode → fallback to storytelling
  4. Otherwise → dùng intent pipeline result
- [ ] Show transcript trước khi process: "🎤 Mình nghe: ..." (existing behavior)
- [ ] Handle voice queries với same accuracy as text
- [ ] **Test: Voice "tài sản của tôi có gì" → query_assets → response**
- [ ] **Test: Voice trong storytelling mode → vẫn extract transactions**
- [ ] **Test: Bad transcription → graceful "didn't catch that"**

### Order Check (CRITICAL)
- Storytelling mode check FIRST, THEN intent pipeline

## Estimate: ~0.5 day
## Depends on: Phase 3A voice infrastructure
