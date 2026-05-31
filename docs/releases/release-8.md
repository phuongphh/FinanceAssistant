# Release 8 — Deploy Notes

> **Ngày deploy:** 2026-05-31
> **Phiên bản app:** `1.4.4.00` (trước: `1.3.8.01`)
> **Branch:** `main` → `prod`
> **Diff:** `origin/prod..origin/main` (105 commits, trong đó ~50 PR thay đổi code, còn lại là `docs(issues): sync …`) — 164 files, +11.407 / −665
> **Commit prod trước release:** `c8feec5 Merge pull request #836 from phuongphh/main`

## Tổng quan

Release 8 là bản lớn (gom toàn bộ work kể từ release 7), tập trung 5 hướng:

1. **Phase 4.4 — First-5-Minutes WOW** — salutation (anh/chị/bạn), onboarding bằng screenshot số dư, proactive companion nudge, làm phẳng flow `goal → asset → Twin` (gỡ bỏ "The Reading").
2. **Nguồn chi tiêu & default source** — thiết lập nguồn chi mặc định trong Profile, canonical-hoá danh sách nguồn, provider-style picker cho bank / thẻ tín dụng, áp default source xuyên suốt quick-tx / OCR / confirm.
3. **Thẻ tín dụng** — thêm `credit_limit`, sửa chiều ghi nợ khi edit/reverse, harden quick credit-card source flow.
4. **Asset list & wealth (live quote)** — YTD & so-với-tháng-trước render thành comparison block, live-quote cổ phiếu + vàng intraday để tổng asset-list khớp YTD, sửa crash picker sửa tài sản.
5. **VN time + miniapp robustness + NLU** — render mọi timestamp theo giờ VN (UTC+7), thoát poisoned WebView cache, HMAC/​session diagnostics, bắt thêm cấu trúc câu chi tiêu khẩu ngữ ở Tier 1.

Kèm theo: runbook soft-launch tháng 6, đồng bộ trạng thái Phase 4.2.5 / 4.3 / 4.4, và tech-debt i18n + gỡ env-read khỏi service layer.

---

## ⚠️ Schema migrations trong release này

Release này **có 3 migration** — chạy `alembic upgrade head` khi deploy:

| Revision | Mô tả |
|---|---|
| `20260527creditlimit` | Thêm `credit_cards.credit_limit` `NUMERIC(15,2)` (backfill = `debt_balance`, sau đó `NOT NULL` + check constraint) |
| `20260528defaultexpsource` | Thêm cột default expense source vào user profile |
| `20260529salutation` | Thêm `users.salutation` (nullable: anh/chị/bạn) **đồng thời gộp 2 alembic head** (`20260523_insurance_backfill` + `20260528defaultexpsource`) về single head |

> `20260529salutation` revise cả 2 head đang mở → sau release `alembic upgrade head` (singular, dùng trong `scripts/deploy_admin.sh`) không còn báo "Multiple head revisions".

---

## PRs đáng chú ý trong release này

| PR | Mô tả |
|---|---|
| [#905](https://github.com/phuongphh/FinanceAssistant/pull/905) / [#906](https://github.com/phuongphh/FinanceAssistant/pull/906) | Phase 4.4 First-5-Minutes WOW (salutation, screenshot onboarding, proactive companion) + follow-up fixes |
| [#911](https://github.com/phuongphh/FinanceAssistant/pull/911) | Phase 4.4: gỡ "The Reading", làm phẳng flow `goal → asset → Twin` |
| [#908](https://github.com/phuongphh/FinanceAssistant/pull/908) | Fix onboarding resume va chạm với name/salutation sub-steps |
| [#913](https://github.com/phuongphh/FinanceAssistant/pull/913) | Tech-debt: i18n 6 chuỗi onboarding + gỡ env-read khỏi service |
| [#881](https://github.com/phuongphh/FinanceAssistant/pull/881) | Default expense source trong Profile (Closes #440) |
| [#879](https://github.com/phuongphh/FinanceAssistant/pull/879) / [#880](https://github.com/phuongphh/FinanceAssistant/pull/880) | Canonical-hoá nguồn chi + provider-style picker bank / thẻ tín dụng |
| [#888](https://github.com/phuongphh/FinanceAssistant/pull/888) / [#889](https://github.com/phuongphh/FinanceAssistant/pull/889) | Sort nguồn chi theo type+name; money-in income labels trong mini app |
| [#892](https://github.com/phuongphh/FinanceAssistant/pull/892) / [#894](https://github.com/phuongphh/FinanceAssistant/pull/894) | Áp default source vào expense confirmation + signed/quick-tx (Closes #891) |
| [#883](https://github.com/phuongphh/FinanceAssistant/pull/883) / [#885](https://github.com/phuongphh/FinanceAssistant/pull/885) / [#886](https://github.com/phuongphh/FinanceAssistant/pull/886) | Sửa alembic revision/down_revision + test cho expense-source (Closes #884) |
| [#877](https://github.com/phuongphh/FinanceAssistant/pull/877) | Harden quick credit-card source flow + debt consistency |
| [#896](https://github.com/phuongphh/FinanceAssistant/pull/896) | Fix crash subtype trong list sửa tài sản (Closes #893) |
| [#893](https://github.com/phuongphh/FinanceAssistant/pull/893) / [#895](https://github.com/phuongphh/FinanceAssistant/pull/895) | Refine picker sửa tài sản + compact nút xoá + test ngưỡng truncate |
| [#890](https://github.com/phuongphh/FinanceAssistant/pull/890) | YTD asset follow-up cho mọi wealth level |
| [#909](https://github.com/phuongphh/FinanceAssistant/pull/909) | Live-quote vàng intraday trong net worth + asset list |
| [#898](https://github.com/phuongphh/FinanceAssistant/pull/898) / [#899](https://github.com/phuongphh/FinanceAssistant/pull/899) | tx-confirm icon-only action row + ✅ Đồng ý + VN time; default source khi save & OCR |
| [#904](https://github.com/phuongphh/FinanceAssistant/pull/904) | Render mọi timestamp user-facing theo giờ VN (UTC+7) |
| [#878](https://github.com/phuongphh/FinanceAssistant/pull/878) | Tier-1 bắt thêm cấu trúc câu chi tiêu khẩu ngữ VN |
| [#875](https://github.com/phuongphh/FinanceAssistant/pull/875) / [#876](https://github.com/phuongphh/FinanceAssistant/pull/876) | Nhãn tiếng Việt cho `SJC_GOLD` (Closes #354) + refine copy briefing đầu tiên |
| [#870](https://github.com/phuongphh/FinanceAssistant/pull/870)–[#874](https://github.com/phuongphh/FinanceAssistant/pull/874) | Miniapp: initData verify logging, HMAC signature-in/out variants, phân biệt session missing vs rejected, source param thoát poisoned WebView cache, diagnostic menu-button |
| [#903](https://github.com/phuongphh/FinanceAssistant/pull/903) | Runbook soft-launch tháng 6 (technical + business/go-to-market) |
| [#900](https://github.com/phuongphh/FinanceAssistant/pull/900) | Mark Phase 4.2.5 + 4.3 done, sync roadmap |

---

## Thay đổi đáng chú ý

### Phase 4.4 — First-5-Minutes WOW (#905, #906, #908, #911)

- **Salutation (anh/chị/bạn):** thêm `users.salutation` để Bé Tiền xưng hô đúng với từng người ngay từ onboarding.
- **Screenshot onboarding:** user gửi ảnh chụp số dư → trích xuất; **reject balance không phải VND** và fallback khi edit "Reading" fail.
- **Làm phẳng flow (#911):** gỡ bỏ màn "The Reading" trung gian, flow đi thẳng `goal → asset → Twin` cho bớt rườm rà.
- **Proactive companion (#906):** nudge tới được user *đã* onboard và đếm twin-return đúng.
- **Resume fix (#908):** sửa lỗi onboarding resume va chạm với name/salutation sub-steps; bump session activity khi advance để không bị treo.

### Nguồn chi tiêu & default source (#879, #880, #881, #888, #889, #892, #894)

- **Default expense source trong Profile (#881, Closes #440):** user đặt nguồn chi mặc định một lần, các luồng quick-tx / OCR / confirm tự áp.
- **Canonical-hoá nguồn (#879):** giới hạn nguồn chi về tập type chuẩn xuyên suốt bot và mini app, tránh nguồn rác/trùng.
- **Provider-style picker (#880):** chọn bank / thẻ tín dụng theo kiểu provider thay vì free-text.
- **Sort + money-in labels (#888, #889):** sắp nguồn theo type+name; mini app category dropdown hỗ trợ nhãn thu nhập (money-in).

### Thẻ tín dụng (#877, credit_limit migration)

- **`credit_limit` column:** thêm hạn mức thẻ (`NUMERIC(15,2)`), backfill bằng `debt_balance` cho record cũ.
- **Debt direction trên edit/reverse:** sửa chiều ghi nợ khi user edit / reverse giao dịch thẻ + đảm bảo ordering "latest" deterministic.
- **Harden quick credit-card source flow (#877):** tránh lệch nợ khi tạo nhanh giao dịch thẻ.

### Asset list & wealth — live quote (#890, #893, #896, #909)

- **Comparison block YTD / tháng trước:** tap YTD hoặc so-với-tháng-trước giờ render block so sánh, bỏ Portfolio detail cũ.
- **Live-quote khớp tổng:** `QueryAssetsHandler` live-quote cổ phiếu và vàng intraday để **tổng asset-list khớp** với YTD/comparison (trước đây lệch do dùng giá lưu).
- **Crash fix (#896, Closes #893):** sửa crash subtype trong list sửa tài sản + refine picker + compact nút xoá.
- **YTD follow-up mọi wealth level (#890):** trước chỉ một số tier thấy follow-up YTD.

### VN time + miniapp robustness + NLU (#870–#874, #878, #898, #904)

- **Giờ VN (UTC+7) (#904):** render **mọi** timestamp user-facing theo giờ Việt Nam thay vì UTC.
- **tx-confirm (#898):** action row icon-only + nút "✅ Đồng ý" + hiển thị giờ VN.
- **Miniapp diagnostics (#870–#874):** logging initData verify, chấp nhận cả 2 biến thể HMAC signature-in/out, phân biệt session **missing** vs **rejected**, thêm `source` param vào URL menu button để **thoát poisoned WebView cache**.
- **Tier-1 NLU (#878):** bắt thêm các cấu trúc câu chi tiêu khẩu ngữ VN ngay tầng phân loại nhanh.
- **`SJC_GOLD` (#875, Closes #354):** hiển thị nhãn tiếng Việt trong market text + refine copy briefing đầu tiên.

### Tech-debt & docs (#900, #903, #913)

- **i18n + env-read (#913):** chuyển 6 chuỗi onboarding sang `content/*.yaml` và **gỡ env-read khỏi service layer** (đúng layer contract).
- **June soft-launch runbook (#903):** runbook hợp nhất technical + business/go-to-market.
- **Roadmap sync (#900):** đánh dấu Phase 4.2.5 + 4.3 done, hoàn tất auto-sync flow trạng thái phase.

---

## Rollback

Nếu cần rollback nhanh:

```bash
git push origin c8feec5:prod --force-with-lease
```

Commit trước release này trên `prod`: `c8feec5 Merge pull request #836 from phuongphh/main`.

> ⚠️ Release này có schema migration. Rollback code **không** tự revert migration — nếu cần hạ schema phải `alembic downgrade` thủ công về `20260523_insurance_backfill` (head trước release). Các cột mới (`credit_cards.credit_limit`, `users.salutation`, default expense source) là **additive**, an toàn để giữ lại nếu chỉ rollback code.

---

## Sanity checks sau deploy

- [ ] `alembic upgrade head` chạy clean, **single head** (không báo "Multiple head revisions")
- [ ] `/about` hiển thị `Phiên bản: 1.4.4.00`
- [ ] Onboarding mới: Bé Tiền xưng hô đúng salutation (anh/chị/bạn)
- [ ] Onboarding bằng screenshot số dư: balance VND parse được; ảnh non-VND bị reject lịch sự
- [ ] Flow onboarding đi thẳng `goal → asset → Twin`, không còn màn "The Reading"
- [ ] Proactive nudge tới được user đã onboard; twin-return count đúng
- [ ] Profile: đặt default expense source → quick-tx / OCR / confirm tự áp đúng nguồn
- [ ] Thêm thẻ tín dụng có `credit_limit`; edit/reverse giao dịch thẻ ghi nợ đúng chiều
- [ ] Asset list: tổng khớp YTD/comparison khi có cổ phiếu + vàng (live quote)
- [ ] Sửa tài sản: list không crash với subtype; nút xoá compact
- [ ] Mọi timestamp user-facing hiển thị giờ VN (UTC+7)
- [ ] Mini app mở được sau khi đổi build (không dính poisoned WebView cache); HMAC verify pass
- [ ] Market text hiển thị "Vàng SJC" thay vì `SJC_GOLD`
