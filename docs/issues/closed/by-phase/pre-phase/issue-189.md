# Issue #189

[Story] P3.7-S7: Implement Telegram streaming for long responses

**Parent Epic:** #181 (Epic 2: Premium Reasoning & Orchestrator)

## User Story
As a user đang chờ trả lời "Có nên bán FLC?", tôi muốn immediate feedback (typing indicator + initial message) trong 2 giây, rồi xem response build dần — không phải nhìn frozen screen 10 giây.

## Acceptance Criteria
- [ ] File `app/agent/streaming/telegram_streamer.py` với `TelegramStreamer` class
- [ ] **`start()` method:**
  - Send typing indicator (`bot.send_chat_action(..., "typing")`)
  - Send initial placeholder: "⏳ Đang phân tích..."
  - Store message_id cho later edits
- [ ] **`send_chunk(text)` method:**
  - Accumulate text trong buffer
  - Flush khi buffer ≥50 chars **AND** last flush ≥0.8s ago, HOẶC stream ended
  - Edit message in-place via `bot.edit_message_text(message_id, ...)`
- [ ] **`finish()` method:** final flush remaining buffer
- [ ] **Error handling:**
  - edit_message_text fails (rate limit) → fallback to new message
  - Message too long (>4096 chars) → split tại sentence boundary
  - Network error → log and continue
- [ ] **First chunk latency <2 seconds**
- [ ] Updates không quá frequent (spam) hoặc quá rare (frozen feeling)
- [ ] Markdown parse_mode supported

## Test Plan
```python
async def test_streaming_first_chunk_under_2s():
    start_time = time.time()
    await streamer.start()
    assert time.time() - start_time < 2.0

async def test_streaming_long_response_splits():
    await streamer.start()
    # Simulate 5000-char streaming
    for chunk in chunked_text(long_text, 100):
        await streamer.send_chunk(chunk)
    await streamer.finish()
    # Verify: split into 2+ messages, no errors
```

## Implementation Notes
- Telegram rate limits edits: ~30/min per chat → flush_interval ≥0.8s
- Typing indicator sent ONCE at start, auto-clears sau 5s

## Estimate: ~1 day
## Depends on: P3.7-S6
## Reference: `docs/current/phase-3.7-detailed.md` § 2.3
