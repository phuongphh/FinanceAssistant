---
name: finance-menu
description: >
  Hiển thị menu chính của Finance Assistant với tất cả tính năng.
  Cho phép người dùng chọn tính năng qua inline keyboard buttons.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# Finance Menu Skill

## Khi nào dùng skill này
- User gửi "/menu" hoặc "menu"
- User hỏi "có tính năng gì?", "giúp tôi", "help"
- User bắt đầu chat lần đầu

## Cách thực thi
1. Chạy: `python3 scripts/menu_cli.py`
2. Hiển thị menu với danh sách tính năng

## Output format
Trả về đúng text sau cho Telegram:

```
🏦 Finance Assistant — Menu

Chọn tính năng bạn muốn sử dụng:

📧 Quét hóa đơn Gmail — "quét gmail" hoặc "scan gmail"
📸 Nhận diện hóa đơn — Gửi ảnh hóa đơn/receipt
✍️ Thêm chi tiêu — "thêm chi tiêu 150k ăn trưa"
📊 Báo cáo chi tiêu — "báo cáo tháng này"
📈 Thông tin thị trường — "thị trường hôm nay?"
🎯 Mục tiêu tài chính — "mục tiêu" hoặc "tiến độ"
💰 Cập nhật thu nhập — "thu nhập tháng này 20tr"
💡 Gợi ý đầu tư — "nên đầu tư gì?"

Nhập lệnh hoặc mô tả nhu cầu bằng tiếng Việt tự nhiên.
```
