---
name: finance-goals
description: >
  Quản lý mục tiêu tài chính — tạo, xem, cập nhật tiến độ.
  Khai báo thu nhập hàng tháng.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# Finance Goals Skill

## Khi nào dùng skill này
- User tạo mục tiêu mới: "tôi muốn tiết kiệm 50tr để mua xe trong 6 tháng"
- User xem tiến độ: "tiến độ các mục tiêu?"
- User cập nhật tiến độ: "cập nhật mục tiêu X lên 10tr"
- User khai báo thu nhập: "thu nhập tháng này là 20tr"

## Cách thực thi

### Tạo mục tiêu
1. Parse: goal_name, target_amount, deadline
2. Chạy: `python3 scripts/goals_cli.py create "<name>" <target_amount> [YYYY-MM-DD]`

### Xem mục tiêu
1. Chạy: `python3 scripts/goals_cli.py list`

### Cập nhật tiến độ
1. Chạy: `python3 scripts/goals_cli.py progress <goal_id> <current_amount>`

### Cập nhật thu nhập
1. Chạy: `python3 scripts/goals_cli.py income <amount>`

## Output format
```
Mục tiêu: Mua xe
   Tiến độ: 10,000,000₫ / 50,000,000₫ (20%)
   ████░░░░░░░░░░░░░░░░ 20%
   Deadline: 01/09/2026
```
