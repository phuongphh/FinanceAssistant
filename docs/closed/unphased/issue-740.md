# Issue #740

🐌 /chitieu command: slow response (16s+) and import error failures

## Hiện tượng

Khi chạy `/chitieu` trên Bé Tiền Test bot, phản hồi rất chậm (~16 giây) và đôi khi bị lỗi không trả kết quả.

Test gần nhất lúc ~11:20 ngày 20/05/2026:
- Update ID #489293383: received=21:20:04, processed=21:20:21 → **17 giây**
- Update ID #489292960: text="/chitieu" → **failed** với lỗi import
- Một số update khác (lộ trình mua nhà) cũng mất ~33s

## Evidence từ server logs

### 1. LLM routing cascade chậm (~16s)
Server log ghi nhận:
```
agent_tier_used: {
  "tier": "tier2",
  "routing_reason": "cascade_from_tier1",
  "latency_ms": 16063
}
```
→ Tier 1 mất ~14s (timeout/fail), tier 2 xử lý thực tế chỉ ~2s → tổng ~16s

### 2. Import error (/chitieu failed)
```
Error: No module named "backend.adapters.telegram_service"
```
→ Các lệnh bị fail gần đây gồm: `/chitieu`, `sửa cổ phiếu FPT thành 200 cổ`, `sửa cổ phiếu FPT thành 55 cổ`

### 3. Stock API errors
```
Primary provider failed for DCDS, falling back to secondary: SSI server error 502
Primary provider failed for E120, falling back to secondary: SSI server error 502
Primary provider failed for FLC, falling back to secondary: SSI server error 502
```
→ Nhiều mã chứng khoán bị fail 502 từ SSI server, phải fallback

### 4. Database unique violation
```
IntegrityError: duplicate key value violates unique constraint "llm_cache_cache_key_key"
```
→ Race condition trong LLM cache insert

## Thông tin thêm

- **Database size**: expenses=141, income_records=0, telegram_updates=3,636, users=9, assets=122
- **Có 2 updates bị stalled tới 113-120 giây** (update ID #489289267, #489289264)
- **Tổng số failed updates**: 44
- **Server**: FastAPI @ port 8002, Python 3.13.11, fastapi 0.135.2
- **LLM providers**: tier1 + tier2 (cascade config)
