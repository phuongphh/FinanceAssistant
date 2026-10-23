# Issue #891

Expense confirmation: use default_expense_source + final-confirm UX

## Mục tiêu

Thống nhất luồng ghi nhận **chi tiêu** (quick transaction + manual wizard) để:

1. Lấy nguồn tiền từ `UserProfile.default_expense_source` đã cấu hình.
   - Trừ vào `current_value` của cash / bank_account / e_wallet.
   - Cộng vào `debt_balance` nếu là credit_card.
2. Tin nhắn xác nhận:
   - Tiêu đề: `✅ Đã ghi xong!` (thay cho `✅ Ghi xong!`).
   - Thêm dòng `Chi từ: [tên nguồn]`.
   - Thêm chú thích cuối: *"Nếu bạn cần sửa/xóa giao dịch này thì hãy vào mục Quản lý chi tiêu trong menu Chi tiêu"*.
   - Bỏ hoàn toàn inline buttons (Đổi danh mục / Sửa / Xóa / Hủy 5s) — coi đây là final confirmation.
3. Quick transaction: nếu không bắt được danh mục → mặc định `Khác` (thay vì `needs_review`).
4. Giao dịch money-in: giữ nguyên luồng hiện tại.

## Acceptance

- [ ] Cả quick transaction và signed/wizard expense đều dùng `default_expense_source`.
- [ ] Tin nhắn confirm đúng format mới, không còn inline keyboard.
- [ ] Credit card → tăng debt_balance; asset khác → giảm current_value.
- [ ] Money-in flow không bị ảnh hưởng.
- [ ] Unit tests phủ các nhánh source + uncategorized fallback.

