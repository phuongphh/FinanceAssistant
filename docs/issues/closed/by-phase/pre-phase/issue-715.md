# Issue #715

bug(action_delete_asset): NameError — build_callback not imported in asset_entry.py


## Nguyên nhân

Khi user gửi "Xoá tài sản HPG", handler `action_delete_asset` gọi `show_asset_delete_matches_list()` ở file:

**`backend/bot/handlers/asset_entry.py`** — dòng 691

Hàm này sử dụng `build_callback()` để tạo inline keyboard buttons, nhưng `build_callback` không được import trong file này.

File chỉ import `parse_callback` từ `backend.bot.keyboards.common` (dòng 80), nhưng commit mới thêm function gọi `build_callback` mà thiếu import tương ứng.

## Vị trí

- **File:** `backend/bot/handlers/asset_entry.py`
- **Dòng gây lỗi:** 691, 698, 703
- **Cần import:** `build_callback` từ `backend.bot.keyboards.common`

## Lỗi từ log

```
NameError: name "build_callback" is not defined. Did you mean: "parse_callback"?
```

## Tác động

User nhận message "Mình đang hơi rối, gặp lỗi khi xử lý 😔" thay vì danh sách tài sản cần xoá.

