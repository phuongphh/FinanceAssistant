# Issue #1029

[Phase 5.0 — chặn gate] 4 lỗ robustness Zalo cần đóng trước khi bật ZALO_CHANNEL_ENABLED

Tách ra từ review của Codex trên PR #1026 (release 11). Cả 4 finding đều **P2**, đều nằm sau flag `ZALO_CHANNEL_ENABLED=false` → **không ảnh hưởng prod hiện tại**. Gom chung vì cùng một chủ đề: đường Zalo chưa chịu được đồng thời / lỗi transport.

Blocker P1 riêng của kênh Zalo: #1028.

---

### 1. Tạo account Zalo-first chưa race-safe
`backend/services/zalo_linking_service.py:272` · [comment](https://github.com/phuongphh/FinanceAssistant/pull/1026#discussion_r3773465723)

Người gửi mới nhắn 2 tin liên tiếp (chào + tên) trước khi background task đầu commit → **cả hai** task đều thấy "chưa có user" và cùng insert. Partial unique index trên `users.zalo_user_id` làm flush thứ hai fail sau khi chờ transaction đầu; update đó bị đánh `failed`, mà orphan recovery chỉ retry row `processing` → **tin nhắn thứ hai mất vĩnh viễn**.

→ Dùng atomic upsert, hoặc bắt unique conflict rồi load lại row thắng cuộc và tiếp tục.

### 2. Trust step nhảy trước khi card được gửi
`backend/bot/handlers/zalo_onboarding.py:375` · [comment](https://github.com/phuongphh/FinanceAssistant/pull/1026#discussion_r3773465727)

Khi windowed notifier trả `None` (transport fail hoặc bị quota từ chối), code vẫn ghi nhận card privacy/trust là "đã hiển thị". Session đã ở `STEP_TRUST_PRIVACY`, và `_handle_trust_step` coi mọi tin kế tiếp là **chấp nhận** → user bị đẩy sang bước thu thập tài sản mà **chưa từng đọc lời cam kết bảo mật**. Với nội dung là trust promise thì đây không chỉ là lỗi UX.

→ Kiểm tra receipt gửi; fail thì giữ nguyên state (hoặc rollback) để lần sau gửi lại card.

### 3. Token đang refresh bị coi như refresh hỏng
`backend/adapters/zalo_oa.py:662` · [comment](https://github.com/phuongphh/FinanceAssistant/pull/1026#discussion_r3773465733)

Multi-worker: worker chạy refresh hàng giờ commit marker `refresh_pending` rồi mới gọi Zalo. Mọi worker khác cần token trong khoảng đó nhận `ZaloTokenRefreshInFlight`, và nhánh này xử lý nó **giống hệt** refresh failed/stuck — trả token rỗng → bỏ luôn reply outbound trong khi vẫn đánh dấu event inbound đã xử lý xong. User nhắn mà không nhận được trả lời, không có retry.

→ Với riêng case in-flight: retry ngắn / poll token vừa commit. Giữ nguyên fail-closed cho refresh thật sự hỏng hoặc quá hạn.

### 4. Reset window xoá mất reservation đang bay
`backend/services/zalo_window_service.py:235` · [comment](https://github.com/phuongphh/FinanceAssistant/pull/1026#discussion_r3773465745)

Một send đã giữ slot, rồi có inbound mới tới trước khi request OA hoàn tất → reset cửa sổ xoá reservation, nhưng request cũ vẫn có thể thành công và **vẫn được Zalo tính**. Row local khi đó cho phép thêm 8 send nữa → **9+ tin trong cùng cửa sổ**, phá đúng cái guarantee quota 8 tin/48h mà service này sinh ra để giữ.

→ Rotation phải giữ lại reservation chưa kết thúc, hoặc reconcile các send cũ thành công vào counter mới.

---

## Ghi chú phạm vi

Cố ý không sửa trong PR promotion #1026: PR đó là delta tích luỹ `main` → `prod`, thêm code chưa review trên `main` vào đó là sai quy trình (`docs/conventions/production-deployment.md`). Cả 4 mục sửa trên `main`, trước khi bật `ZALO_CHANNEL_ENABLED`.
