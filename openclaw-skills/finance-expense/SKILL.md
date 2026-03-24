---
name: finance-expense
description: Ghi nhận chi tiêu cá nhân — thêm, xem, sửa, xóa expense
triggers:
  - thêm chi tiêu
  - ghi lại
  - tôi vừa xài
  - chi [số tiền]
  - xem chi tiêu
  - sửa chi tiêu
  - xóa chi tiêu
  - tổng chi tiêu
env:
  - FINANCE_API_URL
  - FINANCE_API_KEY
---

# Finance Expense Skill

## Khi nào dùng skill này
- User muốn thêm chi tiêu mới: "thêm chi tiêu 150k ăn trưa", "chi 50k grab"
- User muốn xem chi tiêu: "xem chi tiêu tháng này", "tổng chi tiêu"
- User muốn sửa/xóa chi tiêu
- User gửi ảnh → route sang finance-ocr skill

## Cách thực thi

### Thêm chi tiêu
1. Parse message để lấy: amount, merchant/description, date (mặc định hôm nay)
2. Gọi `POST {FINANCE_API_URL}/expenses?user_id={user_id}`
   Body: `{"amount": ..., "merchant": "...", "note": "...", "source": "manual"}`
3. Backend sẽ tự động categorize qua LLM
4. Trả về confirm cho user

### Xem chi tiêu
1. Xác định filter: tháng nào, category nào
2. Gọi `GET {FINANCE_API_URL}/expenses?user_id={user_id}&month=YYYY-MM`
3. Format danh sách trả về Telegram

### Tổng hợp chi tiêu
1. Gọi `GET {FINANCE_API_URL}/expenses/summary?user_id={user_id}&month=YYYY-MM`
2. Format bảng tổng hợp theo category

## Output format
```
✅ Đã ghi: 150,000₫ — ăn trưa (food_drink)
📅 24/03/2026
```
