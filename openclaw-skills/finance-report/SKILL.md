---
name: finance-report
description: >
  Báo cáo tài chính hàng tháng — tổng chi tiêu, phân tích theo danh mục,
  so sánh với tháng trước, tỷ lệ tiết kiệm.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# Finance Report Skill

## Khi nào dùng skill này
- "báo cáo tháng này / tháng trước"
- "tôi xài bao nhiêu tiền?"
- "so sánh chi tiêu"
- "tỷ lệ tiết kiệm của tôi"

## Cách thực thi

### Xem báo cáo tháng
1. Xác định tháng (mặc định: tháng hiện tại)
2. Chạy: `python3 scripts/report_cli.py monthly [YYYY-MM]`

### Xem lịch sử báo cáo
1. Chạy: `python3 scripts/report_cli.py history`

### Force regenerate
1. Chạy: `python3 scripts/report_cli.py generate [YYYY-MM]`
