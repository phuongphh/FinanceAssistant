# Issue #1061

Hóng hớt: data model + admin UI nhập tin thủ công (MXH/tech/economy)

## Problem
Bé Tiền cần tính năng mới "Hóng hớt" — bản tin hằng ngày tổng hợp tin hot MXH
(Threads, TikTok) và tin công nghệ/kinh tế. Phase 1: toàn bộ nội dung do admin
Nuitruc nhập tay qua portal (chưa có bot tự động quét MXH).

Hiện chưa có data model lẫn admin UI cho loại nội dung này. Bảng
`news_articles` hiện tại gắn chặt với RSS (source cố định cafef/vnexpress,
không có field cho category MXH/tech/economy hay ảnh).

## Expected behavior
1. Bảng DB mới lưu các mục "Hóng hớt" admin nhập tay.
2. Admin UI (trong `admin_spa.py` hiện có) có form CRUD: tạo/sửa/xoá/ẩn-hiện
   1 mục tin.
3. Mỗi mục tin có: tiêu đề, nội dung tóm tắt, link gốc (optional — tin MXH có
   thể không có link public), ảnh minh hoạ (optional), category, nguồn
   (thread/tiktok/khac), trạng thái active, thời gian tạo.

## Scope of change
- New model: `backend/models/social_buzz_item.py`
  - `id` (UUID), `title` (text, required), `summary` (text, optional),
    `url` (text, optional — không unique vì có thể trùng/không có),
    `image_url` (text, optional), `source_type` (enum: `thread`, `tiktok`,
    `manual`), `category` (enum: `social`, `tech`, `economy`),
    `is_active` (bool, default true), `created_by` (admin user ref),
    `created_at`, `updated_at`.
  - Index trên `(category, is_active, created_at)` để query nhanh "5 tin
    mới nhất theo category".
- Alembic migration tạo bảng mới (theo `alembic/` convention hiện có).
- Admin router mới: `backend/routers/admin_social_buzz.py` (theo pattern của
  `admin_zalo_quota.py`/`admin_agent_metrics.py` hiện có) — CRUD endpoints,
  bảo vệ bằng `admin_security.py` như các admin router khác.
- Admin SPA: thêm 1 trang/section quản lý "Hóng hớt" (list + form thêm/sửa)
  trong `backend/admin_spa.py` hoặc frontend tương ứng nếu admin SPA là
  React/Vue riêng — khảo sát cấu trúc admin SPA hiện có trước khi code.

## Out of scope
- Không tích hợp tự động quét Threads/TikTok (Phase 2, issue riêng).
- Không làm phần quán ăn/đồ handmade (Nuitruc partnership — epic riêng,
  issue riêng khi có dữ liệu NCC).
- Không đổi bảng `news_articles` hiện tại (RSS market news giữ nguyên).

## Acceptance Criteria
- [ ] Alembic migration chạy thành công, tạo bảng `social_buzz_items` đúng
      schema.
- [ ] Admin có thể tạo mới 1 mục Hóng hớt qua UI/API — lưu đúng DB.
- [ ] Admin có thể sửa, ẩn (is_active=false), xoá 1 mục đã tạo.
- [ ] API yêu cầu auth admin (dùng lại `admin_security.py`), không phải admin
      bị từ chối.
- [ ] Unit test cho model + router (CRUD happy path + unauthorized access).

## Test commands
(xác nhận sau khi khảo sát pattern test admin router hiện có, ví dụ)
pytest backend/tests/ -k admin_social_buzz -v

## Constraints
- Theo đúng layer contract trong CLAUDE.md (service flush only, router/worker
  commit).
- Dùng lại `admin_security.py` cho auth, không tạo cơ chế auth riêng.

