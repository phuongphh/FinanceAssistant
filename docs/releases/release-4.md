# Release 4 — Deploy Notes

> **Ngày deploy:** 2026-05-15
> **Branch:** `main` → `prod`
> **Diff:** `origin/prod..origin/main` (30 commits, trong đó 5 PR thay đổi code, còn lại là `docs(issues): sync …`)

## Tổng quan

Release 4 tập trung vào 2 hướng chính:

1. **Hoàn thiện UI/UX 5** cho Asset menu và Cashflow view — privacy toggle, tone chat-first của Bé Tiền, sửa logic recurring income.
2. **Mở rộng NLU intent layer** — thêm clarifier, intent handlers mới (quick transaction, add/edit asset, add goal, nav expense dashboard), amount parser.

Đồng thời vá 2 bug production (KeyError `vip` trong menu formatter, morning briefing không bắn cho user mới / asset-only) và bổ sung test coverage.

---

## Issues đã đóng

### Epic — UI/UX 5

- **#641** [Epic] Enhance UI/UX 5 — Asset privacy, Bé Tiền tone, natural language, cashflow fixes
  - **#642** Hide/show total asset amount với eye button
  - **#643** Reword Bé Tiền note với natural chat tone
  - **#644** Thêm asset category note trong Asset Management
  - **#645** Đổi foot button `BĐS cho thuê` → `Cho thuê BĐS`
  - **#646** Đổi `Hủy` → `Quay về menu` trong form thêm asset
  - **#647** Đổi icon land asset từ 🏠 sang 🌳
  - **#648** Reorder guidance trong Expense Management — chat-first
  - **#649** Thêm date hôm nay vào title cashflow
  - **#650** Fix recurring income calculation logic trong cashflow view

### Bug fixes

- **#635** Bug: `KeyError 'vip'` trong `menu_formatter.format_main_menu` khi `wealth_level='vip'`
- **#638** Bug: `KeyError 'vip'` trong `menu_formatter.py` khi user VIP nhấn `/menu` (crash loop)

### NLU & Briefing

- **#640** Morning briefing không bắn cho user mới + user chỉ có asset (no expense yet)
- **#662** NLU bugs epic — clarifier, intent dispatcher, thêm các action handlers còn thiếu

---

## PRs trong release này

| PR | Mô tả | Closes |
|---|---|---|
| [#639](https://github.com/phuongphh/FinanceAssistant/pull/639) | `test(menu)`: cover VIP wealth-level qua full render path | #635, #638 |
| [#640](https://github.com/phuongphh/FinanceAssistant/pull/640) | `fix(briefing)`: include new users và asset-only users vào morning briefing; loại trừ demo placeholder asset | #640 |
| [#651](https://github.com/phuongphh/FinanceAssistant/pull/651) | `improve`: enhance UI/UX 5 — asset và cashflow polish | #641 |
| [#662](https://github.com/phuongphh/FinanceAssistant/pull/662) | NLU bugs epic — clarifier + 5 intent handlers mới + amount parser | #662 |
| [#663](https://github.com/phuongphh/FinanceAssistant/pull/663) | Fix UI/UX polish cho asset và cashflow menus (follow-up of #651) | #641 |

---

## Thay đổi đáng chú ý

### Bug `KeyError 'vip'` trong menu_formatter (#635, #638)

`menu_formatter.format_main_menu()` lookup `config["title"][band]` với `band="vip"`, nhưng
`content/menu_copy.yaml` không có khóa `vip` → crash mỗi lần user VIP gọi `/menu`,
Telegram retry tạo crash loop làm chậm response.

- Fix: bổ sung khóa `vip` trong `content/menu_copy.yaml` (đã có từ trước trong main, ở release này #639 bổ sung test coverage để chặn regression).
- Thêm test `test_menu_v2.py` cover VIP wealth-level qua full render path.

### Morning briefing cho new users + asset-only users (#640)

Gate "30-day expense activity" trước đây loại trừ user mới đăng ký (chưa có expense) và user chỉ có asset → welcome-briefing UPS không bắn được. Sửa thành predicate inclusive:

> Opted-in users qualify nếu có recent expense **HOẶC** có active portfolio asset **HOẶC** account created trong 30 ngày qua.

Sau review của Codex bot trên PR #640, bổ sung loại trừ `is_placeholder_asset=True` và `is_confirmed=False` (mirror logic của `asset_service.get_user_assets` + index `idx_assets_real`). Thêm unit tests cho `_get_briefing_candidates` cover 3 nhánh OR và override `profile_briefing_time`.

### UI/UX 5 — Asset & Cashflow polish (#651, #663)

- Asset Management: thêm eye toggle để hide/show total asset amount, asset category note, đổi tên/icon các foot button.
- Asset form: đổi `Hủy` → `Quay về menu` trigger return về main menu.
- Expense menu: di chuyển natural-language guidance lên đầu (chat-first positioning).
- Cashflow view: thêm date hôm nay vào title, fix logic recurring income (lương 50tr/th, rent 10tr/th hiển thị đúng fixed amount).
- Tone toàn bộ text changes dùng Bé Tiền's natural friendly tone (Vietnamese).

### NLU intent layer mở rộng (#662)

Thêm:

- `backend/intent/clarifier.py` — clarification flow khi intent ambiguous.
- `backend/intent/dispatcher.py` — mở rộng dispatcher với fallback paths.
- Intent handlers mới:
  - `action_add_asset.py`
  - `action_add_goal.py`
  - `action_edit_asset.py`
  - `action_quick_transaction.py`
  - `nav_expense_dashboard.py`
- `backend/wealth/amount_parser.py` — parse amount với các format VN (`50tr`, `1.5 tỷ`, `45k`…).
- `content/clarification_messages.yaml`, `content/intent_patterns.yaml` — content YAML cho clarifier + pattern matching.
- Test coverage: `test_amount_parser.py`, `test_action_quick_transaction_handler.py`, `fixtures/query_examples.yaml`.

---

## Rollback

Nếu cần rollback nhanh:

```bash
git push origin <commit-of-previous-prod>:prod --force-with-lease
```

Commit trước release này trên `prod`: `1d1c9d4 docs(issues): sync #635 (closed, state=closed)`.

---

## Sanity checks sau deploy

- [ ] `/menu` hoạt động cho user VIP, không còn KeyError trong logs
- [ ] Morning briefing fire cho user mới đăng ký (< 30 ngày) và user chỉ có asset
- [ ] Asset Management: eye toggle hide/show hoạt động, button labels đúng
- [ ] Cashflow view: title có date hôm nay, recurring income hiển thị fixed amount đúng
- [ ] NLU: clarifier kích hoạt khi intent ambiguous, các quick-transaction utterances được route đúng handler
