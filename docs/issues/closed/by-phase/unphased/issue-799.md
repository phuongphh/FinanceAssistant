# Issue #799

[bug] Callback txsrc_wallet:* không gửi response — user stuck ở màn hình chọn nguồn


## Nguyên nhân

Khi user tạo money-in transaction text (vd: "+20 tỷ lương"), bot hỏi chọn nguồn tiền (e_wallet → Momo/VNPay/ZaloPay/ViettelPay). Sau khi user chọn ví cụ thể (callback data: `txsrc_wallet:zalopay`), bot xử lý DB thành công nhưng **không gửi message phản hồi** về Telegram.

## Evidence

Log backend 18:42:53:
```
18:42:53.118 — callback txsrc_wallet:zalopay received
18:42:53.126 — SELECT users
18:42:53.130 — SELECT assets (cash/zalopay/e_wallet)
18:42:53.138 — INSERT expense (money_in 20B, income, zalopay)
18:42:53.143 — SELECT assets
18:42:53.146 — UPDATE assets SET current_value
18:42:53.149 — SELECT expense
18:42:53.152 — SAVEPOINT
18:42:53.156 — SELECT streaks
18:42:53.158 — INSERT feature_events (transaction)
18:42:53.158 — INSERT events
18:42:53.161 — INSERT transactions
18:42:53.176 — UPDATE telegram_updates SET status='done'
```

DB ops thành công, nhưng **không có log gửi message về Telegram** sau đó. Error log trống — không throw exception.

User thấy màn hình chọn nguồn vẫn hiện ra, không có xác nhận → phải bấm lại lần khác (lúc 18:44 user chọn Momo).

## Files liên quan
- `backend/bot/handlers/asset_entry.py` (đã thay đổi +20 dòng trong commit 1244050)
- Có thể handler `txsrc_wallet:*` thiếu lệnh gửi message response sau khi xử lý DB

## Reproduce
1. Gõ "+20 tỷ lương" (hoặc bất kỳ money-in text nào)
2. Bot hỏi chọn nguồn tiền → chọn e_wallet → chọn ví cụ thể
3. Bot xử lý DB xong nhưng không gửi message xác nhận
