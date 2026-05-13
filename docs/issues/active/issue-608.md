# Issue #608

fix(miniapp): wealth dashboard returns 302 redirect which Telegram Mini App cannot follow

## Bug
Opening the wealth dashboard in Telegram Mini App shows blank page.

## Root cause
Route `/miniapp/wealth` returns HTTP 302 redirect (for cache busting). Telegram Mini App WebView does NOT follow 302 redirects automatically.

## Fix needed
Return 200 OK directly. Cache busting should happen via JS after page load.

## File
`backend/miniapp/routes.py`
