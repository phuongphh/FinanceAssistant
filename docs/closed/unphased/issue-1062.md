# Issue #1062

Hóng hớt: thêm mục menu + hiển thị bản tin hằng ngày cho user (depends on #1061)

## Depends on
This issue depends on the data model + admin UI issue for "Hóng hớt"
(table `social_buzz_items`). Do NOT start until that issue is merged —
this issue needs real data to query against.

## Problem
Sau khi có data model + admin nhập tin, Bé Tiền cần hiển thị các
tin "Hóng hớt" này cho user qua menu, giống format title=link đã áp dụng ở
Morning Brief (issue #1053).

## Expected behavior
1. Main menu (`content/menu_copy.yaml` + `menu_formatter.py`) có thêm nút
   mới: "🔥 Hóng hớt" (hiện có 6 nút, layout 2 cột 3 hàng; thêm nút thứ 7 cần
   xem lại layout cho cân đối, có thể đổi sang 4 hàng).
2. Bấm vào mở submenu "Hóng hớt" với danh sách tin mới nhất, chia theo 2
   nhóm: "🔥 MXH hot" (category=social) và "📰 Tin Công nghệ/Kinh tế"
   (category=tech + economy).
3. Mỗi tin hiển thị dạng: `• [Title](url)` nếu có url, nếu không có url thì
   `• Title` (plain, không link giả).
4. Số lượng hiển thị: 5 tin mới nhất mỗi nhóm (có thể điều chỉnh qua config).

## Scope of change
- `content/menu_copy.yaml`: thêm `submenu_buzz` theo đúng convention hiện có
  (title, intro theo wealth-level, buttons, hint) + thêm button vào
  `main_menu.buttons`.
- `backend/bot/formatters/menu_formatter.py`: không cần đổi logic (category
  mới tự động support qua `format_submenu`), chỉ cần YAML đúng key.
- New service: `backend/services/social_buzz_service.py` (hoặc đặt cùng
  thư mục phù hợp theo khảo sát) — query N tin mới nhất theo category từ
  `social_buzz_items`.
- New handler action trong `backend/bot/handlers/menu_handler.py` (hoặc file
  tương ứng) — xử lý callback khi user bấm vào "Hóng hớt" / từng nhóm tin,
  gọi service + format giống `_news_lines()` pattern đã dùng ở Morning Brief.

## Out of scope
- Không làm personalization (Phase sau, theo roadmap đã nêu).
- Không làm phần quán ăn/đồ handmade.
- Không đổi Morning Brief hiện tại.

## Acceptance Criteria
- [ ] Main menu hiển thị nút "🔥 Hóng hớt" mới, bấm vào mở đúng submenu.
- [ ] Submenu hiển thị tin chia 2 nhóm (MXH / Tech-Kinh tế), mỗi nhóm tối đa
      5 tin mới nhất (is_active=true).
- [ ] Tin có url hiển thị dạng link bấm được; tin không url hiển thị plain
      text, không tạo link rỗng/lỗi.
- [ ] Trường hợp chưa có tin nào (DB rỗng) hiển thị fallback message thân
      thiện, không lỗi/crash.
- [ ] Nút "◀️ Quay về" hoạt động đúng, quay lại main menu.
- [ ] Unit test cho service (query đúng N tin, đúng category, đúng thứ tự
      mới nhất) + test cho handler/callback.

## Test commands
(xác nhận theo pattern test hiện có cho menu_handler, ví dụ)
pytest backend/tests/ -k menu_handler -v
pytest backend/tests/ -k social_buzz -v

## Constraints
- Giữ nguyên layout convention: button label ≤16 ký tự, callback_data ≤64
  bytes, intro ≤200 từ.
- Copy 100% tiếng Việt theo convention menu_copy.yaml.

