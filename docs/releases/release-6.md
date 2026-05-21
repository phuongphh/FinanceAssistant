# Release 6 — Deploy Notes

> **Ngày deploy:** 2026-05-21
> **Branch:** `main` → `prod`
> **Diff:** `origin/prod..origin/main` (50 commits, trong đó ~25 PR thay đổi code, còn lại là `docs(issues): sync …`)
> **Commit prod trước release:** `c3b3e45 5th release: promote main to prod (2026-05-19) (#699)`

## Tổng quan

Release 6 tập trung 3 hướng chính:

1. **Twin Dashboard UI/UX polish** — sửa back fallback, dd/mm/yyyy format, CTA contrast, comparison readability, causality direction, tech-detail card.
2. **Market data & stock menu** — thêm foreign quote provider (NVDA, IBM, ETF), fix VN stock providers, redesign stock menu, fix gold manual-price badge.
3. **NLU & intent robustness** — follow-up context carryover qua 3-tier NLU, time-range parsing cho asset/goal reports, validate category selection, expense-report routing, expense edit modal localization.

Đồng thời vá một số bug nhỏ (WebView cache, dashboard CSS reload, dashboard spinner) và bổ sung unit tests cho OCR receipt confirm callbacks và `parse_vietnamese_date`.

---

## Issues đã đóng

### Twin Dashboard (Epic #725)

- **#725** [Epic] Enhance Twin Dashboard — UI/UX Improvements
- **#730** [Story 5] Always show tech detail card + friendly labels — Twin Dashboard
- **#624** [Epic] Enhance UI/UX 4 — chat-first guidance, money-in, crypto date, date format, briefing fix (Twin back fallback + dd/mm/yyyy chuẩn hoá)
- **#742** Polish back-to-menu button trong Asset Dashboard
- **#123** Twin causality direction mismatch và stale cache; follow-up context carryover

### Market data & Stocks

- **#749** Fix VN stock price providers và redesign stock menu UI
- **#750** Add foreign stock provider (NVDA, IBM, ETF) — symbol-aware routing
- **#752 / #753** Fix gold portfolio manual-price badge sau market refresh

### NLU & Expense flow

- **#757** Improve NLU time-range report parsing cho assets/goals
- **#730 (intent)** Fix expense-report intent routing và report truncation
- **#761** Validate category selection against allowed list (callbacks)
- **#603** Add missing unit tests cho OCR receipt confirm callbacks
- **#758** Improve expense edit modal buttons, localize Reverse → Huỷ

### Dashboard / WebView

- **#762** Expense Dashboard hangs on loading spinner — API call không tới backend sau deploy
- **#765** Telegram WebView cache ignores query-string — JS stale sau deploy
- **#767 / #768 / #769** Extract shared dashboard helpers (`dashboard_common.js`) + register vào cache-bust hash
- **#770** Internal dashboard navigation không reload CSS — WebView dùng cached styles

### Misc

- **#739**, **#740** `/chitieu` slow response (16s+) và import error failures
- **#736** Bổ sung unit test cho `parse_vietnamese_date`
- **#771** Auto PR follow-up

---

## PRs trong release này

| PR | Mô tả | Closes |
|---|---|---|
| [#731](https://github.com/phuongphh/FinanceAssistant/pull/731) | Auto PR — Issue #725 (Twin Dashboard polish) | #725 |
| [#733](https://github.com/phuongphh/FinanceAssistant/pull/733) | Fix Twin back fallback và standardize dd/mm/yyyy UI dates | #624 |
| [#735](https://github.com/phuongphh/FinanceAssistant/pull/735) | Improve Twin Dashboard CTA contrast và uncertainty spacing | #725 |
| [#736](https://github.com/phuongphh/FinanceAssistant/pull/736) | `test(bot)`: bổ sung unit test cho `parse_vietnamese_date` | #736 |
| [#738](https://github.com/phuongphh/FinanceAssistant/pull/738) | Improve Twin mini-app comparison readability, remove build footer | — |
| [#739](https://github.com/phuongphh/FinanceAssistant/pull/739) | Auto PR — Issue #739 (`/chitieu` slow + import error) | #739 |
| [#741](https://github.com/phuongphh/FinanceAssistant/pull/741) | Auto PR follow-up | — |
| [#742](https://github.com/phuongphh/FinanceAssistant/pull/742) | Auto PR — Issue #742 | #742 |
| [#743](https://github.com/phuongphh/FinanceAssistant/pull/743) | Auto PR — Issue #740 | #740 |
| [#745](https://github.com/phuongphh/FinanceAssistant/pull/745) | Auto PR follow-up | — |
| [#746](https://github.com/phuongphh/FinanceAssistant/pull/746) | Fix Twin causality direction mismatch và stale cache | #123 |
| [#747](https://github.com/phuongphh/FinanceAssistant/pull/747) | Auto PR follow-up | — |
| [#748](https://github.com/phuongphh/FinanceAssistant/pull/748) | Polish back-to-menu button trong Asset Dashboard | #742 |
| [#749](https://github.com/phuongphh/FinanceAssistant/pull/749) | Fix VN stock price providers và redesign stock menu UI | #749 |
| [#751](https://github.com/phuongphh/FinanceAssistant/pull/751) | `feat(stock)`: foreign quote provider với symbol-aware routing | #750 |
| [#752](https://github.com/phuongphh/FinanceAssistant/pull/752) / [#753](https://github.com/phuongphh/FinanceAssistant/pull/753) | Fix gold portfolio manual-price badge sau market refresh | — |
| [#754](https://github.com/phuongphh/FinanceAssistant/pull/754) | Fix follow-up context carryover across 3-tier NLU | #123 |
| [#757](https://github.com/phuongphh/FinanceAssistant/pull/757) | Fix expense-report intent routing và report truncation | #730 |
| [#758](https://github.com/phuongphh/FinanceAssistant/pull/758) | Improve expense edit modal buttons + localize Reverse → Huỷ | — |
| [#759](https://github.com/phuongphh/FinanceAssistant/pull/759) | Improve NLU time-range report parsing cho assets/goals | #757 |
| [#761](https://github.com/phuongphh/FinanceAssistant/pull/761) | Add missing unit tests cho OCR receipt confirm callbacks | #603 |
| [#763](https://github.com/phuongphh/FinanceAssistant/pull/763) | `fix(callbacks)`: validate category selection against allowed list | #761 |
| [#764](https://github.com/phuongphh/FinanceAssistant/pull/764) | Auto PR — Issue #762 (expense dashboard spinner) | #762 |
| [#766](https://github.com/phuongphh/FinanceAssistant/pull/766) | Auto PR — Issue #765 (WebView cache query-string) | #765 |
| [#767](https://github.com/phuongphh/FinanceAssistant/pull/767) | Auto PR — Issue #767 (dashboard helpers) | #767 |
| [#768](https://github.com/phuongphh/FinanceAssistant/pull/768) | Extract shared dashboard helpers vào `dashboard_common.js` | #767 |
| [#769](https://github.com/phuongphh/FinanceAssistant/pull/769) | Register `dashboard_common.js` trong cache-bust hash | #767 |
| [#771](https://github.com/phuongphh/FinanceAssistant/pull/771) | Auto PR — Issue #771 (dashboard CSS reload) | #770 |

---

## Thay đổi đáng chú ý

### Twin Dashboard UI/UX (#725, #624, #123)

- **Back fallback chuẩn hoá:** khi user bấm Back trong Twin mini-app mà không có history, fallback về Dashboard chính thay vì trắng màn hình.
- **Date format dd/mm/yyyy** xuyên suốt UI Twin (trước đây trộn mm/dd/yyyy ở vài chỗ).
- **CTA contrast** và spacing cho uncertainty bands rõ ràng hơn.
- **Comparison readability:** loại bỏ build footer, polish layout so sánh giữa kịch bản.
- **Causality direction mismatch** + stale cache: kết quả Twin hiển thị đúng chiều nhân quả; clear cache khi assumption đổi.
- **Tech detail card** luôn show với friendly labels (Story 5 của #725 epic).

### Foreign stock provider (#750)

Thêm `foreign_quote_provider` với symbol-aware routing:
- Symbol pattern `^[A-Z]{1,5}$` (NVDA, IBM, AAPL…) → foreign provider.
- Symbol pattern VN (3 ký tự ALL CAPS hoặc ETF VN) → SSI/VNDIRECT như trước.
- Fallback graceful nếu foreign API down.

### VN stock providers + stock menu redesign (#749)

- Fix lỗi parsing response từ SSI/VNDIRECT khi format đổi.
- Redesign stock menu: chia rõ "VN Stocks" và "Foreign Stocks" sau khi thêm #750.
- Inline quotes hiển thị provider source + timestamp last-known khi stale.

### Gold portfolio manual-price badge (#752, #753)

Badge "manual price" bị mất sau khi market refresh do gold service overwrite manual entry → fix bằng cách check `price_source='manual'` trước khi refresh.

### NLU time-range parsing cho assets/goals (#757, #759)

- Thêm rule patterns cho câu hỏi time-range trên asset/goal report (`"tài sản tháng trước"`, `"mục tiêu năm nay"`…).
- Extract `time_range` trên `query_assets` / `query_goals`.
- Map sub-asset hints (`land`, `apartment`, `fund`, `etf`).
- Thêm regression fixtures cho #757 scenarios.

### Expense-report intent routing + report truncation (#730/#757)

- Fix routing: expense-report bị nhầm thành quick-transaction trong vài câu utterance.
- Fix truncation: report dài > 4096 chars không bị cắt giữa số liệu, chia trang đúng.

### Callback category validation (#761)

`select_category` callback từ Telegram inline keyboard không validate input → nếu user gửi callback giả (debug/manual) có thể inject category không tồn tại. Fix: validate against `allowed_categories` per wealth-level.

### OCR receipt confirm callbacks (#603, #761)

Thêm unit tests coverage cho confirm/edit/cancel callbacks sau OCR — bao gồm path expired hash, replay attempt, multi-receipt session.

### Dashboard WebView cache (#762, #765, #770, #767-#769)

- **#762**: dashboard hang spinner — fetch URL thiếu `tg_init_data` query param sau deploy, backend reject silently.
- **#765**: Telegram WebView cache query-string — JS stale sau deploy. Fix: append content hash vào query-string.
- **#770**: internal dashboard navigation không reload CSS. Fix: cache-bust CSS riêng từng route.
- **#767-#769**: refactor common JS thành `dashboard_common.js` + register vào cache-bust hash list.

### `/chitieu` slowness + import error (#739, #740)

- 16s+ response do synchronous expensive query — chuyển sang background task với loading state.
- Import error: circular import giữa `expense_service` và `report_service` → tách helper module.

---

## Rollback

Nếu cần rollback nhanh:

```bash
git push origin c3b3e45:prod --force-with-lease
```

Commit trước release này trên `prod`: `c3b3e45 5th release: promote main to prod (2026-05-19) (#699)`.

---

## Sanity checks sau deploy

- [ ] Twin Dashboard: Back button fallback đúng, dd/mm/yyyy hiển thị nhất quán, tech detail card luôn show
- [ ] Stock menu: tách VN/Foreign rõ, query NVDA / IBM trả về quote real-time
- [ ] Gold portfolio: badge "manual price" giữ nguyên sau market refresh
- [ ] NLU: utterance `"tài sản tháng trước"` route đúng query_assets với time_range
- [ ] Callback validate: category lạ bị reject với message thân thiện
- [ ] `/chitieu`: response < 5s, không còn import error trong logs
- [ ] Dashboard WebView: hard reload không hiển thị CSS/JS stale sau deploy
- [ ] Expense edit modal: nút hiển thị "Huỷ" thay vì "Reverse"
