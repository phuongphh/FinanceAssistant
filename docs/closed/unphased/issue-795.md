# Issue #795

Intent classifier slow — Deepseek API takes ~10 seconds per classify call

# Issue: Intent classifier latency cao — Deepseek mất ~10 giây mỗi lần classify

**Nguyên nhân:** Khi user gửi text command (ví dụ "tạo tài sản", "tạo tài khoản tiết kiệm"), backend gọi Deepseek API để classify intent. Log cho thấy latency trung bình ~9.8 giây (9.894s trong log gần nhất).

**Log:**
```
intent_classify: {"latency_ms": 9894, "classifier": "agent_tier1"}
```

**Tác động:** Bot phản hồi rất chậm (10 giây) khi user gõ text thay vì bấm nút. Gây trải nghiệm tệ cho user — AI wizard thì nhanh nhưng text command thì chậm.

**Các vấn đề liên quan:**
1. Deepseek model `deepseek-chat` có latency cao từ phía API
2. Không có timeout/caching cho intent classification
3. User có thể tưởng bot bị treo và gửi lại message → gây thêm request
