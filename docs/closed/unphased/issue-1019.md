# Issue #1019

Bug: Twin first open takes ~25s on cache miss

Nguyên nhân từ log dev Mac Mini ngày 2026-08-05: lần callback Telegram update_id=489296207 với data menu:twin:view_current được nhận lúc 16:18:51.927 và mark done lúc 16:19:17.423, tổng 25.496s. Trong request này cache miss ở llm_cache cho key twin_narrative, sau đó DeepSeek operation twin_narrative dùng model deepseek-v4-flash ghi llm_cost_log latency_ms=15715, tokens_in=361, tokens_out=1952. Sau đó tiếp tục cache miss shared:twin_life_outcome, insert cache lúc 16:19:15.030. Lần gọi lại update_id=489296209 ngay sau đó dùng cache và chỉ mất 1.758s. Không thấy exception trong backend-error.log tại thời điểm này.
