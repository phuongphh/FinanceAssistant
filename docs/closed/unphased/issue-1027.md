# Issue #1027

[Bug] stock_updater: snapshot fallback ghi đè baseline live → cảnh báo "biến động 15 phút" sai

Tách ra từ review của Codex trên PR #1026 (release 11). **Đây là finding duy nhất trong nhóm đó KHÔNG nằm sau flag `ZALO_CHANNEL_ENABLED`** — code này active ngay khi release 11 lên prod.

Nguồn: https://github.com/phuongphh/FinanceAssistant/pull/1026#discussion_r3773465720

## Hiện trạng

`backend/market_data/jobs/stock_updater.py` (`update_all_held_stocks`):

```python
await check_movements(quotes, cache=cache)
quotes.extend(snapshot_quotes.values())
for quote in quotes:
    await cache.set(quote)
    await cache.set_last_known(quote)   # ← snapshot (is_stale=True) cũng ghi vào đây
```

`snapshot_quotes` được tạo trong `_latest_snapshot_quotes` với `source="market_snapshot"`, `is_stale=True` — đó là giá cuối phiên, có thể cũ hơn nhiều so với `last_known` đang nằm trong Redis. `PriceCache.set_last_known` (`backend/market_data/cache/price_cache.py:55`) **không** so sánh `fetched_at` và **không** kiểm tra `is_stale`, nên nó ghi đè vô điều kiện.

## Hậu quả

1. Run N: provider fail (hoặc trả batch thiếu) → symbol X rơi vào nhánh snapshot → `last_known[X]` bị hạ xuống giá cuối phiên cũ.
2. Run N+1: provider hồi phục, trả giá live.
3. `check_movements()` so giá live mới với baseline cũ → gửi cảnh báo *"biến động trong 15 phút"* cho một chênh lệch thực chất là qua đêm hoặc lâu hơn.

Người dùng nhận cảnh báo sai — đúng loại lỗi làm mất niềm tin vào alert nói chung.

## Hướng sửa đề xuất

Snapshot fallback **vẫn nên** ghi vào cache giá thường (`cache.set`) để UI có số hiển thị, nhưng **không** được đụng tới baseline alert:

- Bỏ qua `set_last_known()` cho quote có `is_stale=True` khi `get_last_known()` trả về entry mới hơn (so `fetched_at`), hoặc
- Đơn giản hơn và bảo thủ hơn: không bao giờ gọi `set_last_known()` cho quote nguồn snapshot — baseline giữ nguyên giá live cuối cùng biết được, đúng ngữ nghĩa "last **known**".

Kèm test: run 1 live → run 2 snapshot fallback → run 3 live, assert không phát sinh alert biến động.

## Ghi chú phạm vi

Cố ý **không** sửa trong PR promotion #1026: PR đó là delta tích luỹ `main` → `prod`, thêm code chưa từng review trên `main` vào đó là sai quy trình (`docs/conventions/production-deployment.md`). Sửa ở đây, merge vào `main`, đi kèm release sau.
