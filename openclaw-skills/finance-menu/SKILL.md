---
name: finance-menu
description: >
  Hiển thị menu chính của Finance Assistant với tất cả tính năng.
  Menu data được lấy từ backend API (single source of truth).
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# Finance Menu Skill

## Khi nào dùng skill này
- User gửi "/menu" hoặc "menu"
- User hỏi "có tính năng gì?", "giúp tôi", "help"

## Cách thực thi
1. Chạy: `python3 scripts/menu_cli.py`
2. Script gọi `GET {FINANCE_API_URL}/telegram/menu` để lấy menu text
3. Hiển thị kết quả cho user
