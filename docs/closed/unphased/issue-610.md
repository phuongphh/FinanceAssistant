# Issue #610

bug(miniapp): menu button Mini App URL with cache buster (?b=) fails to open in Telegram

## Bug
Menu button "💰 Tài sản" opens wealth dashboard Mini App, but shows blank/white screen. Dashboard works when accessed via inline keyboard button (Menu → Tài sản → Báo cáo → 📊 Mở dashboard tài sản).

## Log analysis
- Backend route `/miniapp/wealth` returns ~~302~~ → ✅ Now 200 OK (fixed in #609)
- Static files serve correctly (CSS/JS 200)
- API endpoints respond 200 (with proper auth)
- No backend errors in logs
- Front-end JS bootstrap script with `location.replace()` runs on page load

## Key observation
The menu button URL includes a cache-buster: `?b=b1d840b`
Removing `?b=` from the URL + restarting Telegram client did NOT fix the issue.

## Environment
- FinanceAssistant HEAD: b1d840b
- Tunnel: requirement-louisiana-jokes-volvo.trycloudflare.com (quick tunnel)
- Telegram client: mobile (iOS/Android)

## Root cause needed
Why does the Mini App open successfully via inline keyboard callback but fail via the persistent menu button? Both use the same URL.
