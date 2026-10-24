# Issue #638

Bug: KeyError 'vip' in menu_formatter.py khi user VIP nhấn /menu

## Nguyên nhân

`menu_formatter.py:58` — hàm `format_main_menu()` gọi `config["title"][band]` với band=`"vip"`, nhưng trong config không tồn tại khóa `"vip"`.

## Log lỗi

```
route_update failed: update_id=489291432
Traceback (most recent call last):
  File "backend/workers/telegram_worker.py", line 876, in process_update_safely
    await route_update(data)
  File "backend/workers/telegram_worker.py", line 106, in route_update
    user_id = await _handle_message(...)
  File "backend/workers/telegram_worker.py", line 290, in _handle_message
    await cmd_menu(db, chat_id, resolved_user)
  File "backend/bot/handlers/menu_handler.py", line 155, in cmd_menu
    text, keyboard = format_main_menu(user, level=level)
  File "backend/bot/formatters/menu_formatter.py", line 58, in format_main_menu
    title = config["title"][band].format(name=name)
KeyError: 'vip'
```

## Tác động

- User VIP (hoặc user có wealth_level="vip") không thể dùng menu
- Bot crash mỗi lần gọi /menu hoặc welcome_back
- Telegram tự động retry → crash loop gây chậm response

## File liên quan

- `backend/bot/formatters/menu_formatter.py` (dòng ~58)
- `backend/bot/handlers/menu_handler.py`

