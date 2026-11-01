# Issue #616

bug(miniapp): cache buster (?b=) in menu button URL prevents Telegram from injecting initData

## Bug
User sees "Không tải được dữ liệu" when opening Mini App from chat menu button.

## Log evidence
- `/miniapp/wealth` returns 200, HTML loads
- API calls return 422 (missing X-Telegram-Init-Data)
- Event `miniapp_opened` has `user_id: None`

## Root cause
Menu button URL (set by `setup_menu_button.py`) includes `?b=<git_sha>`. When Telegram opens a Mini App, it appends initData as query params. If the URL already has `?` (from cache buster), Telegram does NOT add initData — or it gets appended as `&` and the backend fails to parse it.

## File
`backend/bot/setup_menu_button.py`

## Environment
FinanceAssistant HEAD: bfd9fa2
Tunnel: cloudflare
Menu button global URL currently:
`https://worm-montreal-polished-enquiry.trycloudflare.com/miniapp/wealth?b=4d5ab3e36f`
