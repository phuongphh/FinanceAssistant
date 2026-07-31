# Release 9 — Deploy Notes (1.4.4.10)

> **Ngày deploy:** 2026-06-04
> **Branch:** `claude/release-9th-prod-deploy-nq2Bh` → `prod` (qua PR)
> **Diff:** `origin/prod..origin/main` (60 commits, ~20 PR thay đổi code, còn lại `docs(issues): sync …`)
> **Commit prod trước release:** `01b5f34 Merge pull request #914 from phuongphh/claude/merge-prod-release-8-bTCgU`
> **APP_VERSION:** `1.4.4.00` → `1.4.4.10` (hiển thị ở `/about`)

## Tổng quan

Release 9 gom toàn bộ work kể từ release 8, tập trung 6 hướng chính:

1. **Ghi thu nhập (money-in) end-to-end** — intent `action_add_income` + wizard, NLU nhận diện "được thưởng / lì xì / nhặt được / tìm được", `default_money_in_source` trong profile (mirror `default_expense_source`), money-in-aware edit pickers, dọn nút money-in khỏi expense menu.
2. **NLU nhận diện ngày trong câu nói** — extract transaction date từ free-text ở mọi path Tier-1/1.5/2, accept ISO strings trong Vietnamese date helper.
3. **Hỏi dư nợ thẻ tín dụng** — intent `query_credit_card_debt` cho "dư nợ tín dụng" + unit tests.
4. **Voice / STT** — thay Whisper bằng hạ tầng self-hosted `stt.nuitruc.ai` (nhanh hơn, dữ liệu không qua bên thứ ba).
5. **Localization báo cáo & dashboard** — Tier 2/Tier 3 report thuần tiếng Việt (bỏ English jargon), nhãn vàng (SJC/PNJ) tiếng Việt, MoM delta khớp cuối tháng dương lịch, redesign asset edit cards.
6. **UX polish & robustness** — thu gọn edit hint sau "Đồng ý", "Theo loại" mở category picker, bỏ "Portfolio analytics" shortcut, market-data primary/secondary batch quote fallback.

---

## PRs trong release này

| PR | Mô tả | Closes |
|---|---|---|
| [#915](https://github.com/phuongphh/FinanceAssistant/pull/915) | Update label `sjc_gold` → "Vàng SJC" (nhãn vàng tiếng Việt) | — |
| [#916](https://github.com/phuongphh/FinanceAssistant/pull/916) | Expense transaction enhancements | — |
| [#917](https://github.com/phuongphh/FinanceAssistant/pull/917) | Remove money-in foot button khỏi expense menu | #200 |
| [#918](https://github.com/phuongphh/FinanceAssistant/pull/918) | `fix(briefing)`: localize gold quick insight labels | — |
| [#920](https://github.com/phuongphh/FinanceAssistant/pull/920) | `fix(expense-confirm)`: clarify editable default source | #897 |
| [#921](https://github.com/phuongphh/FinanceAssistant/pull/921) | `fix(market-data)`: secondary fallback khi primary batch empty/partial + giữ primary khi secondary lỗi non-retryable | — |
| [#923](https://github.com/phuongphh/FinanceAssistant/pull/923) | `feat(nlu)`: detect "được … cho/thưởng/lì xì X" là money-in | — |
| [#925](https://github.com/phuongphh/FinanceAssistant/pull/925) | `feat(nlu)`: detect found-money "tìm/nhặt được X" là money-in | — |
| [#926](https://github.com/phuongphh/FinanceAssistant/pull/926) | Update goals tip guidance | #125 |
| [#928](https://github.com/phuongphh/FinanceAssistant/pull/928) | Strip English jargon từ Tier 3 reports — Vietnamese-only output | — |
| [#929](https://github.com/phuongphh/FinanceAssistant/pull/929) | Replace Whisper STT với self-hosted `stt.nuitruc.ai` | — |
| [#930](https://github.com/phuongphh/FinanceAssistant/pull/930) | `feat(intent)`: add `query_credit_card_debt` cho "dư nợ tín dụng" + tests | — |
| [#931](https://github.com/phuongphh/FinanceAssistant/pull/931) | `feat(profile)`: add `default_money_in_source` + money-in-aware edit pickers | — |
| [#932](https://github.com/phuongphh/FinanceAssistant/pull/932) | `feat(intent)`: `action_add_income` tier1 rule + wizard launch + guards | — |
| [#933](https://github.com/phuongphh/FinanceAssistant/pull/933) | `feat(nlu)`: extract transaction date từ free-text (Tier-1/1.5/2) + ISO date helper | — |
| [#934](https://github.com/phuongphh/FinanceAssistant/pull/934) | `fix(intent)`: drop "Portfolio analytics" shortcut khỏi net-worth view | — |
| [#935](https://github.com/phuongphh/FinanceAssistant/pull/935) | Redesign asset edit cards: full-width content + ✏️/🗑 action row | — |
| [#936](https://github.com/phuongphh/FinanceAssistant/pull/936) | `fix(intent)`: align asset-list MoM delta với calendar end-of-month | — |
| [#937](https://github.com/phuongphh/FinanceAssistant/pull/937) | `feat(callbacks)`: collapse edit hint → "Chi tiêu đã được ghi lại" sau Đồng ý | — |
| [#938](https://github.com/phuongphh/FinanceAssistant/pull/938) | `feat(intent)`: "Theo loại" follow-up mở category picker + localize labels | — |

---

## Migrations

| Revision | Mô tả |
|---|---|
| `20260530defaultmoneyinsource` | Add cột `default_money_in_source VARCHAR(120) NULL` vào `user_profiles` (down_revision: `20260529salutation`) |

Chạy `alembic upgrade head` sau deploy. Migration thuần additive (add nullable column) → an toàn, không cần backfill.

---

## Thay đổi đáng chú ý

### Ghi thu nhập (money-in) end-to-end (#917, #920, #923, #925, #931, #932)

- **Intent + wizard (#932):** thêm tier-1 rule `action_add_income` → bấm "Ghi thu nhập" từ menu chính vào thẳng wizard. Guard chống nhầm pattern khi câu có trailing amount.
- **NLU money-in (#923, #925):** Bé Tiền tự hiểu "được thưởng 2tr", "lì xì 500k", "nhặt được / tìm được 200k" là tiền vào — không phải chi tiêu. Tighten edge cases của từ "được" để tránh false positive.
- **Default money-in source (#931):** thêm `default_money_in_source` vào profile (mirror `default_expense_source`) — lần sau ghi thu nhập 1 chạm. Edit pickers chỉ hiện ví/TK phù hợp tiền vào, loại generic e-wallet default; giữ income category + clear default marker khi user edit source.
- **Dọn menu (#917):** bỏ nút money-in lạc chỗ khỏi expense menu (Closes #200).
- **Expense confirm (#920):** làm rõ default source có thể chỉnh sửa (Closes #897).

### NLU nhận diện ngày trong câu nói (#933)

- Extract transaction date từ free-text ("hôm qua đổ xăng 200k", "thứ hai tuần trước ăn lẩu 450k") ở **mọi** path Tier-1/1.5/2 — không còn phải sửa ngày tay.
- Vietnamese date helper accept ISO strings để interop với upstream extractor.

### Hỏi dư nợ thẻ tín dụng (#930)

- Intent mới `query_credit_card_debt` cho "dư nợ tín dụng" / "thẻ còn nợ bao nhiêu" → trả lời ngay từ `credit_limit` data, không phải mở app ngân hàng.
- Kèm unit tests cho `QueryCreditCardDebtHandler` + fix review comments.

### Voice / STT self-hosted (#929)

- Thay OpenAI Whisper API bằng hạ tầng nhận diện tiếng Việt self-hosted `stt.nuitruc.ai`.
- **Lợi:** nhanh hơn, ổn định hơn cho tiếng Việt, dữ liệu voice không đi qua bên thứ ba.
- ⚠️ **Deploy check:** đảm bảo env/config trỏ đúng endpoint STT mới trên prod (xem sanity checks).

### Localization báo cáo & dashboard (#915, #918, #928, #935, #936)

- **Tier 2/Tier 3 Vietnamese-only (#928):** strip English jargon khỏi report output; HNW/report prompt thuần Việt + backward-compat labels.
- **Nhãn vàng tiếng Việt (#915, #918):** `sjc_gold` → "Vàng SJC", localize gold quick insight labels trong briefing.
- **Asset edit cards redesign (#935):** tên tài sản chiếm trọn dòng (tap-to-edit), nút ✏️/🗑 gọn lại thành action row, delete behind mode toggle.
- **MoM delta (#936):** biến động tài sản tháng khớp đúng cuối tháng dương lịch.

### UX polish & robustness (#921, #926, #934, #937, #938)

- **Edit hint collapse (#937):** sau khi bấm "Đồng ý", gợi ý chỉnh sửa thu gọn về "Chi tiêu đã được ghi lại" → màn hình đỡ rối.
- **"Theo loại" category picker (#938):** bấm "Theo loại" sau khi xem chi tiêu mở thẳng bảng chọn danh mục; localize follow-up button labels.
- **Bỏ Portfolio analytics shortcut (#934):** dọn shortcut khỏi net-worth view.
- **Market-data fallback (#921):** fall back sang secondary khi primary batch quote empty/partial; giữ primary khi secondary báo lỗi non-retryable → giá thị trường ổn định hơn khi 1 nguồn lỗi.
- **Goals tip (#926):** cập nhật guidance (Closes #125).

---

## Rollback

Nếu cần rollback nhanh:

```bash
git push origin 01b5f34:prod --force-with-lease
```

Commit trước release này trên `prod`: `01b5f34 Merge pull request #914 from phuongphh/claude/merge-prod-release-8-bTCgU` (APP_VERSION 1.4.4.00).

> ⚠️ Migration `20260530defaultmoneyinsource` chỉ add nullable column — rollback code KHÔNG bắt buộc downgrade DB (column thừa vô hại). Nếu vẫn muốn revert: `alembic downgrade -1`.

---

## Sanity checks sau deploy

- [ ] `/about` hiển thị version `1.4.4.10`
- [ ] `alembic upgrade head` chạy clean (`default_money_in_source` xuất hiện trên `user_profiles`)
- [ ] Menu chính có nút "Ghi thu nhập" → vào wizard
- [ ] "được thưởng 2tr" / "lì xì 500k" / "nhặt được 200k" được nhận diện là tiền vào (không phải chi tiêu)
- [ ] Set default money-in source → lần sau ghi thu nhập 1 chạm; edit picker chỉ hiện ví/TK phù hợp tiền vào
- [ ] "hôm qua đổ xăng 200k" / "thứ hai tuần trước ăn lẩu 450k" bắt đúng ngày, không cần sửa tay
- [ ] "dư nợ tín dụng" / "thẻ còn nợ bao nhiêu" trả lời đúng số dư nợ
- [ ] Tin nhắn thoại chuyển qua `stt.nuitruc.ai` thành công (env STT endpoint đúng), transcript tiếng Việt chính xác
- [ ] Báo cáo Tier 2/Tier 3 thuần tiếng Việt, không lẫn English jargon
- [ ] Nhãn vàng hiển thị "Vàng SJC" (không phải `sjc_gold`)
- [ ] Asset edit card: tên tài sản trọn dòng, nút ✏️/🗑 gọn
- [ ] Biến động tài sản tháng (MoM) khớp cuối tháng dương lịch
- [ ] Sau "Đồng ý" giao dịch → hint thu gọn "Chi tiêu đã được ghi lại"
- [ ] "Theo loại" mở category picker
- [ ] Giá thị trường vẫn hiển thị khi 1 nguồn quote lỗi (primary/secondary fallback)
