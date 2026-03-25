---
name: finance-expense
description: >
  Ghi nhận chi tiêu cá nhân — thêm, xem, sửa, xóa expense.
  Tự động phân loại chi tiêu qua AI.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
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
2. Chạy: `python3 scripts/expense_cli.py add <amount> <note>`
3. Backend sẽ tự động categorize qua LLM
4. Trả về confirm cho user

### Xem chi tiêu
1. Xác định filter: tháng nào (format YYYY-MM)
2. Chạy: `python3 scripts/expense_cli.py list [YYYY-MM]`
3. Format danh sách trả về Telegram

### Tổng hợp chi tiêu
1. Chạy: `python3 scripts/expense_cli.py summary [YYYY-MM]`
2. Format bảng tổng hợp theo category

## Output format
```
Đã ghi: 150,000₫ — ăn trưa (food_drink)
24/03/2026
```
