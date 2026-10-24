# Issue #801

[bug] Money-in transaction fails with integer overflow when amount > 2.1 tỷ


## Nguyên nhân

Khi user tạo money-in với số tiền lớn hơn ~2.1 tỷ VND (giới hạn INTEGER 32-bit: 2,147,483,647), cột `transactions.amount` (kiểu INTEGER) bị tràn số → INSERT fail → toàn bộ transaction rollback → user không thấy phản hồi.

## Evidence

### Log backend 19:21:58:
```
19:21:55.149 — Bot nhận text "+3 tỷ"
19:21:55.159 — SELECT users (user Bệ hạ, wizard_state chứa draft)
19:21:55.164 — SELECT onboarding sessions
19:21:55.169 — UPDATE users SET wizard_state
19:21:55.581 — UPDATE telegram_updates status=done (text xử lý xong)
---
19:21:56.929 — Callback txsrc:e_wallet (chọn ví điện tử)
19:21:57.716 — UPDATE status=done
---
19:21:58.506 — Callback txsrc_wallet:viettelpay (chọn ViettelPay)
19:21:58.520 — SELECT assets (cash/viettelpay/e_wallet)
19:21:58.525 — INSERT expense (money_in 3,000,000,000 VND)
19:21:58.529 — SELECT assets
19:21:58.531 — UPDATE assets SET current_value
19:21:58.534 — SELECT expense
19:21:58.537 — SAVEPOINT
19:21:58.538 — SELECT streaks
19:21:58.542 — INSERT feature_events, events
19:21:58.544 — **INSERT INTO transactions (..., amount=, ...) VALUES (..., 3000000000, ...)**
19:21:58.581 — **UPDATE status=failed — lỗi:**
```

### Error message đầy đủ:
```
(sqlalchemy.dialects.postgresql.asyncpg.Error) <class 'asyncpg.exceptions.DataError'>: 
invalid input for query argument : 3000000000 (value out of range)
```

### Phân tích:
- `expenses.amount` là NUMERIC(15,2) → 20 tỷ vẫn OK
- `transactions.amount` là **INTEGER** (max 2,147,483,647) → 3 tỷ > 2.1 tỷ → **overflow**
-  trong INSERT INTO transactions là amount column
- Lỗi asyncpg ở 19:21:58.544 khi INSERT transactions với amount=3000000000

### So sánh:
- Lúc 18:42:40: amount 20,000,000,000 (20 tỷ) → INSERT expense OK nhưng **INSERT transactions bị lỗi tương tự** ở bước sau (không thấy log do update_id khác)
- Lúc 18:42:53: amount 20,000,000,000 → INSERT transactions với INTEGER overflow → lý do callback `txsrc_wallet:zalopay` không gửi response

## Hậu quả
1. Transaction bị rollback hoàn toàn
2. User không thấy message xác nhận
3. Tiền/dữ liệu không được lưu

## Files liên quan
- `backend/bot/handlers/callbacks.py` — handler txsrc_wallet tạo expense + transaction
- `backend/models/transactions.py` (hoặc migration file) — định nghĩa cột amount kiểu INTEGER
