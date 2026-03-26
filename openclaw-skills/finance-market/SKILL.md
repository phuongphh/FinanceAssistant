---
name: finance-market
description: >
  Thông tin thị trường tài chính Việt Nam — VN-Index, quỹ đầu tư,
  gợi ý đầu tư cá nhân dựa trên tình hình tài chính.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# Finance Market Skill

## Khi nào dùng skill này
- "thị trường hôm nay thế nào?"
- "VN-Index đang ở đâu?"
- "nên đầu tư gì?"
- "phân tích tài chính của tôi"

## Cách thực thi

### Xem snapshot thị trường
1. Chạy: `python3 scripts/market_cli.py snapshot`

### Xem lịch sử giá
1. Chạy: `python3 scripts/market_cli.py history <ASSET_CODE>`

### Gợi ý đầu tư
1. Chạy: `python3 scripts/market_cli.py advice`
