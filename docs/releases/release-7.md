# Release 7 — Deploy Notes

> **Ngày deploy:** 2026-05-23
> **Branch:** `main` → `prod`
> **Diff:** `origin/prod..origin/main` (50 commits, trong đó 18 PR thay đổi code, còn lại là `docs(issues): sync …`)
> **Commit prod trước release:** `1a29766 Auto PR from Claude — Issue #779 (#773)`

## Tổng quan

Release 7 tập trung 3 hướng chính:

1. **Life Assurance (BHNT) flow** — inline wizard, sửa logic monthly/end-date, hiển thị annual premium, routing picker, regression tests.
2. **Onboarding & Twin polish** — bỏ trigger Twin với seed asset demo, show step (3/3) trước Twin narrative, fix causality cache-key direction mismatch, test name-capture.
3. **Robustness & dữ liệu** — sửa overflow `INT4` cho `transactions.amount`, fallback `send_message` khi edit `txsrc` callback fail, recurring-cost trong expense card, alembic chain readable, webhook 400 cho JSON invalid, undo wording.

Đồng thời harden CI lifecycle fetch fallback (#520) và thêm test coverage cho `onboarding_v2` + Life Assurance picker.

---

## Issues đã đóng

### Life Assurance (BHNT)

- **#786** Update life insurance list to show annual premium
- **#425** Life insurance monthly / end-date persistence and display
- **#813 (no issue)** Inline BHNT add flow trong asset wizard
- **#812** Unit tests cho Life Assurance asset picker routing

### Onboarding & Twin

- **#811** Show onboarding step (3/3) trước Twin narrative
- **#814** Skip Twin trigger cho demo-only seed asset
- **#804** Fix Twin causality cache key — prevent direction mismatch
- **#806** Unit tests cho `onboarding_v2` name-capture logic

### Robustness / Data integrity

- **#801** `transactions.amount` overflow INT4 — đổi sang NUMERIC(20,2)
- **#820** Restore readable alembic chain cho insurance backfill
- **#817 (no issue)** Monthly expense card include recurring costs
- **#800** Fallback `send_message` khi edit `txsrc` callback fail
- **#790** Align expired-undo wording với reverse flow
- **#794** Webhook trả 400 cho JSON invalid (thay vì silent 200)
- **#520** Harden issue lifecycle fetch fallback trong CI

### Misc auto-PRs

- **#797 / #6** Auto PR follow-up
- **#796** Auto PR follow-up
- **#791 / #792** Auto PR follow-up

---

## PRs trong release này

| PR | Mô tả | Closes |
|---|---|---|
| [#790](https://github.com/phuongphh/FinanceAssistant/pull/790) | `fix(callbacks)`: align expired-undo wording với reverse flow | — |
| [#792](https://github.com/phuongphh/FinanceAssistant/pull/792) | Auto PR — Issues #791, #792 | #791, #792 |
| [#794](https://github.com/phuongphh/FinanceAssistant/pull/794) | Handle invalid webhook JSON with 400 response | — |
| [#796](https://github.com/phuongphh/FinanceAssistant/pull/796) | Auto PR — Issue #796 | #796 |
| [#798](https://github.com/phuongphh/FinanceAssistant/pull/798) | Auto PR — Issues #6, #797 | #6, #797 |
| [#800](https://github.com/phuongphh/FinanceAssistant/pull/800) | `fix(callbacks)`: fall back to send_message khi `txsrc` edit fails | — |
| [#802](https://github.com/phuongphh/FinanceAssistant/pull/802) | `fix(transactions)`: make amount NUMERIC(20,2) để fix INT4 overflow | #801 |
| [#804](https://github.com/phuongphh/FinanceAssistant/pull/804) | Fix Twin causality cache key — prevent direction mismatch | — |
| [#806](https://github.com/phuongphh/FinanceAssistant/pull/806) | Add unit tests cho `onboarding_v2` name capture logic | — |
| [#808](https://github.com/phuongphh/FinanceAssistant/pull/808) | Harden issue lifecycle fetch fallback in CI | #520 |
| [#811](https://github.com/phuongphh/FinanceAssistant/pull/811) | Show onboarding step (3/3) trước Twin narrative | — |
| [#812](https://github.com/phuongphh/FinanceAssistant/pull/812) | Add unit tests cho Life Assurance asset picker routing | — |
| [#813](https://github.com/phuongphh/FinanceAssistant/pull/813) | Inline BHNT add flow trong asset wizard | — |
| [#814](https://github.com/phuongphh/FinanceAssistant/pull/814) | `fix(onboarding)`: skip Twin trigger cho demo-only seed asset | #811 |
| [#815](https://github.com/phuongphh/FinanceAssistant/pull/815) | Fix life insurance monthly / end-date persistence và display | #425 |
| [#817](https://github.com/phuongphh/FinanceAssistant/pull/817) | Update monthly expense card to include recurring costs | — |
| [#820](https://github.com/phuongphh/FinanceAssistant/pull/820) | `fix(db)`: restore readable alembic chain cho insurance backfill | — |
| [#821](https://github.com/phuongphh/FinanceAssistant/pull/821) | Update life insurance list to annual premium display | #786 |

---

## Thay đổi đáng chú ý

### Life Assurance (BHNT) end-to-end (#425, #786, #812, #813, #815, #820, #821)

- **Inline BHNT wizard (#813):** thay vì kick user ra modal riêng, BHNT add flow nằm inline trong asset wizard — chọn provider, gói, premium frequency, end date đều cùng một stream.
- **Monthly / end-date persistence (#425, #815):** trước đây `monthly_premium` và `end_date` bị mất khi user edit lại record (do model field không bind 2 chiều). Fix bằng cách normalize input ở service layer và persist đúng cột.
- **Annual premium display (#786, #821):** asset list cho BHNT giờ hiển thị premium quy đổi annual (×12 cho monthly, ×4 cho quarterly) thay vì chỉ in raw monthly — giúp user so sánh trực quan với các tài sản khác.
- **Picker routing (#812):** thêm regression tests cho Life Assurance picker để tránh nhầm route sang generic asset picker (gây mất các field BHNT-specific).
- **Alembic chain (#820):** insurance backfill migration vô tình tạo branch trên alembic chain → restore readable single-line chain để `alembic upgrade head` không hỏi resolve revision.

### Onboarding & Twin (#804, #806, #811, #814)

- **Step (3/3) trước Twin narrative (#811):** thêm explicit step indicator trước khi push Twin onboarding narrative, user biết còn bao nhiêu bước nữa.
- **Skip Twin cho demo asset (#814):** seed asset demo (welcome flow) không trigger Twin briefing nữa — tránh briefing rỗng / sai context khi user chưa thật sự add asset.
- **Causality cache-key (#804):** Twin causality result cache key giờ include direction (positive/negative) — fix lỗi hiển thị sai chiều khi user toggle assumption nhanh.
- **`onboarding_v2` name capture tests (#806):** thêm regression cho corner cases (tên Vietnamese có dấu, multi-word, capitalize đúng).

### `transactions.amount` INT4 overflow (#801, #802)

- Trước đây `transactions.amount` là `INTEGER` (INT4, max ~2.1 tỷ VND) → user nhập 5 tỷ giao dịch BĐS bị 500.
- Migration đổi sang `NUMERIC(20,2)` đúng chuẩn money column trong CLAUDE.md.
- Service layer dùng `Decimal` — không có float ở đâu, chỉ là column type sai. Backfill migration cast `INTEGER → NUMERIC` an toàn.

### Recurring cost trong monthly expense card (#817)

- Monthly expense card chỉ tính transaction một-lần → recurring (subscription, rent, utility auto-pay) bị bỏ qua → con số "chi tháng này" không match cảm nhận user.
- Fix: include `recurring_expense_service.get_monthly_total(user_id, month)` vào aggregate.

### `txsrc` edit fallback (#800)

- Khi callback `txsrc` (edit transaction source) gặp Telegram API error trên `edit_message_text` (message quá cũ / đã bị edit khác), trước đây swallow silently → user thấy nút bấm không phản hồi.
- Fix: catch `BadRequest` → fallback gửi `send_message` mới với cùng nội dung. UX nhất quán.

### Webhook JSON validation (#794)

- Trước đây webhook nhận JSON invalid trả 200 (per Telegram requirement) nhưng silently log → khó debug.
- Đổi sang trả 400 cho JSON parse error (vẫn 200 cho valid update có lỗi xử lý sau). Telegram sẽ không retry vì 400 ≠ 5xx.

### Expired-undo wording (#790)

- Wording khi user bấm Undo sau khi giao dịch đã expire không nhất quán với reverse flow (`"Quá hạn rồi"` vs `"Giao dịch này đã expire"`). Localize về cùng giọng văn Bé Tiền.

### CI lifecycle fetch fallback (#520, #808)

- CI workflow fetch issue lifecycle đôi khi rate-limited / network flaky → fail toàn build.
- Harden: retry 3 lần với exponential backoff, fallback gracefully nếu GitHub API down.

---

## Rollback

Nếu cần rollback nhanh:

```bash
git push origin 1a29766:prod --force-with-lease
```

Commit trước release này trên `prod`: `1a29766 Auto PR from Claude — Issue #779 (#773)`.

---

## Sanity checks sau deploy

- [ ] BHNT add flow inline trong asset wizard chạy end-to-end (provider → gói → premium → end date) không kick ra modal riêng
- [ ] Asset list hiển thị BHNT premium quy đổi annual đúng (monthly ×12, quarterly ×4)
- [ ] Edit BHNT record: monthly premium và end date được persist sau save
- [ ] Onboarding: thấy step (3/3) trước khi Twin narrative bắn
- [ ] Welcome seed asset demo không trigger Twin briefing
- [ ] Twin causality: toggle direction nhiều lần không bị stale result
- [ ] Transaction lớn (> 2.1 tỷ VND, ví dụ giao dịch BĐS) lưu thành công, không 500
- [ ] Monthly expense card tổng số bao gồm recurring costs
- [ ] `txsrc` edit callback trên message cũ vẫn gửi reply (fallback `send_message`)
- [ ] Webhook JSON invalid trả 400, không retry storm
- [ ] Expired undo wording match reverse flow
- [ ] `alembic upgrade head` chạy clean, không hỏi resolve revision
