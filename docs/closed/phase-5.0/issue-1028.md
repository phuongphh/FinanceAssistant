# Issue #1028

[Phase 5.0 — chặn gate] Lời mời Telegram từ Zalo không mang danh tính → tạo user thứ hai, tách đôi dữ liệu tài chính

Tách ra từ review của Codex trên PR #1026 (release 11). Severity **P1**. Code nằm sau flag `ZALO_CHANNEL_ENABLED=false` nên **không ảnh hưởng prod hiện tại**, nhưng đây là blocker phải đóng **trước khi bật flag**.

Nguồn: https://github.com/phuongphh/FinanceAssistant/pull/1026#discussion_r3773465713
Vị trí: `backend/bot/handlers/zalo_onboarding.py:487`

## Vấn đề

Với user Zalo-first, nút mời sang Telegram chỉ mở `telegram_bot_url` dùng chung — **không mang payload định danh nào**. Khi user bấm và `/start` bên Telegram:

1. Đường `/start` gọi `dashboard_service.get_or_create_user()` chỉ với Telegram ID mới.
2. Không tìm thấy row nào → **tạo `User` thứ hai**, thay vì điền `telegram_id` vào row Zalo đang có.
3. Thử link thủ công sau đó cũng hỏng: `zalo_user_id` đó đã thuộc về row gốc.

Kết quả: cross-channel handoff — thứ đang được quảng cáo trong onboarding — làm **tách đôi dữ liệu tài chính của cùng một người** thành hai account. Đây là loại lỗi rất khó dọn sau khi đã có giao dịch ở cả hai bên.

## Hướng sửa đề xuất

Cần một đường merge tường minh, chọn một trong hai:

- **Deep link mang token dùng một lần:** sinh token ngắn hạn gắn với `user_id`, nhúng vào `https://t.me/<bot>?start=<token>`; `/start` đọc payload, resolve token → điền `telegram_id` vào đúng row Zalo, đánh dấu token đã dùng. Cần TTL + single-use để không thành đường chiếm tài khoản.
- **Hoặc** giữ link dùng chung nhưng bổ sung luồng link tường minh hai chiều (nhập mã hiển thị bên Zalo vào Telegram), kèm xử lý va chạm khi `zalo_user_id` đã thuộc row khác.

Bắt buộc kèm test: Zalo-first → mời → `/start` → assert **đúng một** row `User`, có cả `zalo_user_id` lẫn `telegram_id`.

## Ghi chú phạm vi

Cố ý không sửa trong PR promotion #1026 (delta tích luỹ `main` → `prod`, không phải nơi thêm code mới). Sửa trên `main` trước gate G1 / trước khi bật `ZALO_CHANNEL_ENABLED`.
