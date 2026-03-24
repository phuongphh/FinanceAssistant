---
name: finance-goals
description: Quản lý mục tiêu tài chính — tạo, xem, cập nhật tiến độ
triggers:
  - tôi muốn tiết kiệm
  - mục tiêu
  - cập nhật tiến độ
  - thu nhập tháng này
  - tiến độ
env:
  - FINANCE_API_URL
  - FINANCE_API_KEY
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
2. Gọi `POST {FINANCE_API_URL}/goals?user_id={user_id}`
3. Confirm cho user

### Xem mục tiêu
1. Gọi `GET {FINANCE_API_URL}/goals?user_id={user_id}`
2. Format danh sách với progress bar

### Cập nhật thu nhập
1. Parse amount
2. Gọi `POST {FINANCE_API_URL}/users/income?user_id={user_id}`

## Output format
```
🎯 Mục tiêu: Mua xe
   Tiến độ: 10,000,000₫ / 50,000,000₫ (20%)
   ████░░░░░░░░░░░░░░░░ 20%
   Deadline: 01/09/2026
```
