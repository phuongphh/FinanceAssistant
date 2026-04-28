# Phase 3A — Epic 1 Test Cases (Telegram-only)

> **Epic:** Asset Data Model & Manual Entry (Tuần 1)
> **Goal:** User nhập được 5 loại asset (cash, stock, real_estate, crypto, gold), xem tổng net worth tính đúng.
> **Issues covered:** P3A-6 → P3A-9 (các flow user thao tác qua Telegram bot)
> **Reference:** [`phase-3a-issues.md`](../phase-3a-issues.md) · [`phase-3a-detailed.md`](../phase-3a-detailed.md) §1.6–§1.7

---

## 📋 Cách dùng file này

- File này **chỉ giữ test cases mà user test trực tiếp qua Telegram bot** — wizard nhập asset (P3A-6/7/8) và onboarding "first asset" (P3A-9).
- Các test thuộc layer DB / model / service / calculator (P3A-1 → P3A-5) đã được tách ra khỏi file này vì chúng yêu cầu `psql`, `alembic`, hoặc `pytest`, không phải Telegram.
- Mỗi test có format: **ID** · **Mục tiêu** · **Bước thực hiện trong Telegram** · **Kết quả mong đợi (user thấy gì)** · **Maps to AC**.
- Cuối file: bảng map ngược về **Checklist Cuối Tuần 1** (`phase-3a-detailed.md` line 1003–1015).

### Pre-test setup chung

1. **Bot ready:** Backend + Telegram bot đã chạy, webhook subscribe xong.
2. **Test account:** Dùng 1 Telegram account đã onboard tới ít nhất `step_5_aha_moment` (cho P3A-9), hoặc đã onboard xong (cho P3A-6/7/8 chạy độc lập qua `/themtaisan`).
3. **Reset state khi cần:** Để test lại onboarding, nhờ admin reset `user.onboarding_step` về `AHA_MOMENT` và `onboarding_completed_at = NULL`.
4. **Cross-user tests:** Cần 2 Telegram account riêng biệt (User A + User B).

> **Lưu ý:** Một số TC tham chiếu hành vi internal (vd. metadata JSON, snapshot DB). Khi test qua Telegram, user verify thông qua **bot reply / dashboard / briefing tiếp theo** chứ không trực tiếp query DB. Test internal-only đã được lược bỏ.

---

# P3A-6 — Asset Entry Wizard: Cash Flow

**Maps to AC:** `start_cash_wizard()`, `handle_cash_subtype()`, `handle_cash_text_input()` parse flexible, save với `source="user_input"`, confirmation + net worth update, "Thêm tài sản khác" button, validation âm/zero, error parse → ask graceful.

> **Setup:** Onboard xong, gửi `/themtaisan` rồi chọn "💵 Tiền mặt / TK", hoặc đang trong onboarding step 6 và tap "💵 Tiền trong NH (5 giây)".

## Happy Path

### TC-1.6.H1 — Vào cash wizard show 4 subtype buttons
- **Mục tiêu:** Verify entry point của cash flow đúng spec.
- **Bước:** Gửi `/themtaisan` → tap "💵 Tiền mặt / TK".
- **Kết quả mong đợi (user thấy):**
  - Bot reply message "💵 Tiền ở đâu?" (hoặc tương đương theo spec line 749).
  - Inline keyboard có **đúng 4 buttons**:
    - "🏦 Tiết kiệm ngân hàng"
    - "💳 Tài khoản thanh toán"
    - "💵 Tiền mặt"
    - "📱 Ví điện tử"
  - Tap thử bất kỳ button nào không bị "loading" infinite — bot phản hồi <2s.

### TC-1.6.H2 — Tap "Tiết kiệm ngân hàng" → bot ask tên + số tiền
- **Bước:** Tap "🏦 Tiết kiệm ngân hàng".
- **Kết quả mong đợi (user thấy):**
  - Bot reply: "💬 Tên ngân hàng + số tiền\n\nVí dụ: 'VCB 100 triệu' hoặc 'Techcom 50tr'".
  - Bot **không** show keyboard nữa (chờ text input từ user).
  - User có thể gõ text bình thường — bot không reject input ngay.

### TC-1.6.H3 — Gõ "VCB 100 triệu" → bot save asset + show confirmation
- **Bước:** Sau khi chọn "Tiết kiệm ngân hàng", gửi text "VCB 100 triệu".
- **Kết quả mong đợi (user thấy):**
  - Bot reply confirmation message có icon ✅, tên "VCB", số tiền "100tr" (format ngắn VN).
  - Message có dòng net worth mới — vd "💎 Net worth: 100tr" (đúng = 100tr nếu user chưa có asset trước đó).
  - Inline keyboard 2 buttons: "➕ Thêm tài sản khác" + "✅ Xong rồi".
  - Asset xuất hiện trong dashboard / `/taisan` list.

### TC-1.6.H4 — Gõ "Techcom 50tr" (variant ngắn) → save thành công
- **Bước:** Subtype `bank_savings`, gửi "Techcom 50tr".
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị tên "Techcom" + giá trị "50tr".
  - Net worth tăng 50tr so với trước.

### TC-1.6.H5 — "MoMo 2tr" cho subtype Ví điện tử
- **Bước:** Tap "📱 Ví điện tử" → gửi "MoMo 2tr".
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị "MoMo" + "2tr".
  - Trong dashboard, asset này gán nhãn loại "Ví điện tử" (icon 📱) — phân biệt với bank savings (🏦).

### TC-1.6.H6 — Parse "Tiết kiệm 500 nghìn" (đơn vị "nghìn")
- **Bước:** Subtype bất kỳ, gửi "Tiết kiệm 500 nghìn".
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị tên "Tiết kiệm" + giá trị "500k" hoặc "500 nghìn".
  - Net worth tăng đúng 500.000đ (kiểm tra qua dashboard).

### TC-1.6.H7 — Sau save: confirm + net worth + offer "Thêm tài sản khác"
- **Bước:** Sau khi parse + save thành công bất kỳ asset cash nào.
- **Kết quả mong đợi (user thấy):**
  - Confirmation message có icon ✅ + tên asset + value formatted (vd "100tr").
  - Có dòng "💎 Net worth: …" với giá trị đã update bao gồm asset vừa thêm.
  - Inline keyboard có **đúng 2 buttons**: "➕ Thêm tài sản khác" và "✅ Xong rồi".

### TC-1.6.H8 — Subtype "Tiền mặt" không cần tên ngân hàng
- **Bước:** Tap "💵 Tiền mặt" → gửi "5 triệu" (chỉ số, không có tên).
- **Kết quả mong đợi (user thấy):**
  - Bot không hỏi lại tên — accept luôn.
  - Confirmation hiển thị tên fallback "Tiền mặt" hoặc "Tài khoản" + giá trị "5tr".
  - Save thành công, net worth tăng 5tr.

## Corner Cases

### TC-1.6.C1 — Số âm "VCB -100tr" → bot reject
- **Bước:** Subtype `bank_savings`, gửi "VCB -100 triệu".
- **Kết quả mong đợi (user thấy):**
  - Bot reply ấm áp đại loại "Số tiền phải lớn hơn 0 nhé 🙂".
  - Asset KHÔNG được tạo (dashboard không xuất hiện asset mới).
  - User có thể gõ lại ngay (vẫn còn ở cùng step) — KHÔNG phải tap subtype lại.

### TC-1.6.C2 — Số 0 "VCB 0" → bot reject
- **Bước:** Gửi "VCB 0".
- **Kết quả mong đợi (user thấy):**
  - Bot reject với message rõ ("Số tiền phải > 0" hoặc tương đương).
  - Asset KHÔNG được tạo.

### TC-1.6.C3 — Text vô nghĩa "abc xyz qwe" → bot ask graceful
- **Bước:** Gửi "abc xyz qwe".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Mình chưa hiểu lắm 😅 Bạn thử lại theo format 'Tên + số tiền' nhé?\nVí dụ: 'VCB 100 triệu'" (hoặc tương đương).
  - User gõ lại "VCB 100tr" → save thành công (state KHÔNG bị reset, không phải tap subtype lại).

### TC-1.6.C4 — Chỉ có số "100tr" (thiếu tên) → save với name fallback
- **Bước:** Gửi "100tr" (không có tên).
- **Kết quả mong đợi (user thấy):**
  - Asset được tạo với name fallback (vd "Tài khoản") + giá trị 100tr.
  - Confirmation hiển thị tên fallback đó. Không crash, không bot im lặng.

### TC-1.6.C5 — Chỉ có tên "VCB" (thiếu số) → bot reject
- **Bước:** Gửi "VCB" (không có amount).
- **Kết quả mong đợi (user thấy):**
  - Bot reply ask retry với hint format "Tên + số tiền".
  - Asset KHÔNG được tạo.

### TC-1.6.C6 — Số rất lớn "VCB 100 tỷ" → save thành công
- **Bước:** Gửi "VCB 100 tỷ".
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị "VCB · 100 tỷ" (format VN, không phải raw "100000000000").
  - Net worth tăng đúng 100 tỷ.

### TC-1.6.C7 — Số có dấu phân cách "VCB 1,500,000" và "1.500.000"
- **Bước:** Gửi lần lượt: "VCB 1,500,000" và "VCB 1.500.000" (kiểu VN).
- **Kết quả mong đợi (user thấy):**
  - Cả 2 đều save = 1.500.000đ.
  - Confirmation hiển thị "1.5tr" hoặc "1,500,000đ" — KHÔNG sai số (vd 1500 hoặc 1.5 nghìn).

### TC-1.6.C8 — Tap subtype 2 lần (race / double click)
- **Bước:** Tap "Tiết kiệm ngân hàng" → tap ngay "Ví điện tử" trước khi gửi text.
- **Kết quả mong đợi (user thấy):**
  - Bot show prompt mới cho "Ví điện tử" (ghi đè prompt cũ).
  - Khi user gửi "MoMo 2tr" → asset save với loại Ví điện tử (icon 📱), KHÔNG phải Tiết kiệm ngân hàng.

### TC-1.6.C9 — Abandon flow giữa chừng (timeout)
- **Bước:** Tap subtype, không gửi text trong 1 giờ. Sau đó gửi "VCB 100tr".
- **Kết quả mong đợi (user thấy):**
  - Hoặc state vẫn còn → save bình thường, hiển thị confirmation.
  - Hoặc state đã expire → bot reply "Bạn đang định thêm gì nhỉ? Gõ lại từ đầu giúp mình nhé" + có thể show menu chính.
  - **Không** lưu asset nửa vời, không crash.

### TC-1.6.C10 — Gửi sticker / photo trong cash_amount step
- **Bước:** Sau khi tap subtype, gửi sticker (hoặc photo bất kỳ) thay vì text.
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Mình chỉ hiểu text thôi nhé, gửi lại theo format 'Tên + số tiền'" (hoặc tương đương).
  - KHÔNG nhầm thành OCR receipt, KHÔNG crash, KHÔNG tạo asset rỗng.

### TC-1.6.C11 — Tên tiếng Việt có dấu "Vietcombank"
- **Bước:** Gửi "Vietcombank 100tr" (hoặc tên có dấu như "Á Châu 50tr").
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị tên đúng dấu (UTF-8 không bị mất).
  - Trong dashboard, tên asset cũng giữ đúng dấu.

### TC-1.6.C12 — Tên dài bất thường (>200 chars) → bot xử lý gracefully
- **Bước:** Gửi tên ~500 ký tự + số (vd "AAAAAAA…AAA 100tr").
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot lưu nhưng tên bị truncate (vd hiển thị 200 ký tự đầu trong confirmation).
  - Hoặc bot reject với message "Tên ngân hàng quá dài, ngắn lại giúp mình nhé".
  - **KHÔNG** crash bot (im lặng / không reply trong 5s = fail).

### TC-1.6.C13 — Số tiền cực nhỏ "VCB 1 đồng"
- **Bước:** Gửi "VCB 1".
- **Kết quả mong đợi (user thấy):**
  - Save thành công với value = 1đ.
  - Confirmation hiển thị "1đ" (hoặc tương đương). Edge case rare nhưng không crash.

### TC-1.6.C14 — Multiline "VCB\n100tr" (newline giữa tên và số)
- **Bước:** Gửi message 2 dòng: dòng 1 "VCB", dòng 2 "100tr".
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot parse được (hiểu newline như space) → save asset "VCB · 100tr".
  - Hoặc bot reject với hint format "Tên + số tiền cùng 1 dòng".
  - **KHÔNG** lưu asset có name = "VCB\n100tr" (literal newline trong tên).

### TC-1.6.C15 — Confirmation message format tiền đúng VN style
- **Bước:** Save asset 1.500.000đ.
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị "1.5tr" hoặc "1,500,000đ" — format ngắn/đầy đủ theo style VN.
  - **KHÔNG** raw "1500000" hay "1500000.00".

### TC-1.6.C16 — Tap "Thêm tài sản khác" → restart wizard từ đầu
- **Bước:** Sau khi save 1 cash asset, tap "➕ Thêm tài sản khác".
- **Kết quả mong đợi (user thấy):**
  - Bot quay về menu chọn loại asset (6 buttons: Cash, Stock, Real Estate, Crypto, Gold, Other).
  - Asset đã save trước đó **không** bị duplicate khi user chọn lại Cash + nhập asset mới.

### TC-1.6.C17 — Tap "✅ Xong rồi" → exit về main menu
- **Bước:** Sau khi save, tap "✅ Xong rồi".
- **Kết quả mong đợi (user thấy):**
  - Bot show main menu hoặc summary message (vd "Tổng net worth của bạn: …").
  - Gõ text bất kỳ sau đó bot không còn hiểu là trong wizard mode.

### TC-1.6.C18 — Cross-user: asset User A không lẫn vào User B
- **Bước:** User A đang giữa cash wizard. User B trên account khác cùng start cash wizard và nhập "BIDV 50tr".
- **Kết quả mong đợi:**
  - User B thấy confirmation "BIDV 50tr · Net worth: 50tr" (riêng B, không bao gồm asset của A).
  - User A khi gõ tiếp text ở wizard của mình, asset save vào account A — KHÔNG xuất hiện trong dashboard B.

### TC-1.6.C19 — Hủy giữa wizard bằng `/huy` hoặc `/cancel`
- **Bước:** Đang ở step nhập tên/số tiền, gửi `/huy` (hoặc `/cancel` nếu spec dùng).
- **Kết quả mong đợi (user thấy):**
  - Bot xác nhận hủy ("Đã hủy thêm tài sản 👌" hoặc tương đương).
  - Quay về main menu — gõ text sau đó không còn lưu thành asset.
  - Nếu spec chưa có cancel command, bot reply "Mình chưa hỗ trợ /huy" — document gap nhưng KHÔNG crash.

---

# P3A-7 — Asset Entry Wizard: Stock Flow

**Maps to AC:** `start_stock_wizard()`, `handle_stock_ticker()`, `handle_stock_quantity()`, `handle_stock_price()`, `handle_stock_current_price()` (same/new), metadata `{ticker, quantity, avg_price, exchange}`, support subtypes `vn_stock|fund|etf|foreign_stock`, ticker không tồn tại vẫn lưu (Phase 3B validate), normalize "VNM stocks" → "VNM", `initial_value = quantity * avg_price`, `current_value = quantity * current_price`.

> **Setup:** Onboard xong, gửi `/themtaisan` → tap "📈 Chứng khoán". Hoặc onboarding step 6 → tap "📈 Tôi có đầu tư".

## Happy Path

### TC-1.7.H1 — Vào stock wizard → bot ask ticker
- **Bước:** Trigger callback `asset_add:stock` (qua menu hoặc onboarding).
- **Kết quả mong đợi (user thấy):**
  - Bot reply "📈 Cổ phiếu / Quỹ mới\n\nMã cổ phiếu (ticker) là gì?\n\nVí dụ: VNM, VIC, HPG, E1VFVN30".
  - Bot không show keyboard (chờ user gõ ticker).

### TC-1.7.H2 — Gõ "VNM" → bot xác nhận + ask quantity
- **Bước:** Gửi text "VNM".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "✅ VNM\n\nBạn đang sở hữu bao nhiêu cổ phiếu?".
  - Bot chờ số lượng (next step).

### TC-1.7.H3 — Ticker lower-case "vnm" → bot tự upper-case
- **Bước:** Gửi "vnm" (lower).
- **Kết quả mong đợi (user thấy):**
  - Bot reply "✅ VNM" (chữ hoa) — confirm rằng bot đã normalize.
  - Sau khi save, dashboard hiển thị ticker "VNM" (không phải "vnm").

### TC-1.7.H4 — Ticker có whitespace "  HPG  " → bot strip
- **Bước:** Gửi "  HPG  " (có space ở đầu/cuối).
- **Kết quả mong đợi (user thấy):**
  - Bot reply "✅ HPG" (không có space).
  - Asset cuối cùng hiển thị ticker đúng "HPG", không có space leak.

### TC-1.7.H5 — Quantity "100" → bot xác nhận + ask giá mua
- **Bước:** Step ask quantity, gửi "100".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "✅ 100 cổ phiếu\n\nGiá mua trung bình mỗi cổ phiếu?\n(Ví dụ: '45000' hoặc '45k')".

### TC-1.7.H6 — Quantity với dấu phẩy "1,000"
- **Bước:** Gửi "1,000".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "✅ 1.000 cổ phiếu" (hoặc "1,000") — parse đúng = 1000, KHÔNG = 1.

### TC-1.7.H7 — Quantity dạng VN "1.000" (dấu chấm phân cách nghìn)
- **Bước:** Gửi "1.000".
- **Kết quả mong đợi (user thấy):**
  - Bot xác nhận "1.000 cổ phiếu" — parse đúng = 1000 (KHÔNG nhầm thành 1.0 = 1).

### TC-1.7.H8 — Giá "45000" → bot tính total + offer "Dùng giá mua / Nhập giá hiện tại"
- **Bước:** Step ask price, gửi "45000".
- **Kết quả mong đợi (user thấy):**
  - Bot reply có dòng "Tổng giá vốn: 4.500.000đ" (hoặc "4.5tr") — đúng = 100 × 45.000.
  - Inline keyboard 2 buttons: "Dùng 45,000đ (giá mua)" và "Nhập giá hiện tại".

### TC-1.7.H9 — Giá "45k" (dạng ngắn) → parse được
- **Bước:** Gửi "45k".
- **Kết quả mong đợi (user thấy):**
  - Bot tính tổng = 100 × 45.000 = 4.5tr (giống TC-1.7.H8). Format ngắn parse đúng.

### TC-1.7.H10 — Tap "Dùng giá mua" → save asset với current = avg price
- **Bước:** Tap button "Dùng 45,000đ (giá mua)".
- **Kết quả mong đợi (user thấy):**
  - Confirmation message: "✅ VNM × 100 cp · 4.5tr" (hoặc tương đương).
  - Net worth update tăng đúng 4.5tr.
  - Inline keyboard "➕ Thêm tài sản khác" + "✅ Xong rồi".

### TC-1.7.H11 — Tap "Nhập giá hiện tại" → bot ask, gõ "50000" → save với gain
- **Bước:**
  1. Tap "Nhập giá hiện tại".
  2. Bot ask "Giá hiện tại của cổ phiếu?".
  3. Gửi "50000".
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị "VNM × 100 cp · 5tr" (current value = 100 × 50.000).
  - Có thể có dòng gain "📈 +500k" (= 5tr - 4.5tr).
  - Net worth tăng = 5tr (KHÔNG phải 4.5tr).

### TC-1.7.H12 — Subtype mặc định = vn_stock (HOSE)
- **Bước:** Save VNM 100 × 45.000 (không chọn subtype rõ ràng).
- **Kết quả mong đợi (user thấy):**
  - Trong dashboard, asset VNM gán nhãn "Cổ phiếu VN" hoặc icon 📈 với exchange HOSE.
  - Phân biệt được với fund/ETF (nếu có nhãn riêng).

### TC-1.7.H13 — Confirmation hiển thị format VN
- **Bước:** Save 100 cp × 45.000.
- **Kết quả mong đợi (user thấy):**
  - Hiển thị "4.5tr" hoặc "4,500,000đ" — KHÔNG raw "4500000" hay "4500000.00".

### TC-1.7.H14 — Wizard support 4 subtypes: vn_stock, fund, etf, foreign_stock
- **Mục tiêu:** Verify wizard có thể nhánh sang fund/ETF/foreign nếu có sub-selection.
- **Bước:** Trigger các path sub-selection (nếu có menu chọn loại stock cụ thể) — vd thử ticker "E1VFVN30" (ETF) hoặc fund VFMVF1.
- **Kết quả mong đợi (user thấy):**
  - Cả 4 path (vn_stock / fund / etf / foreign_stock) đều dẫn đến save thành công.
  - Trong dashboard, asset có nhãn loại đúng (vd ETF có icon riêng hoặc tag "ETF").

## Corner Cases

### TC-1.7.C1 — Ticker không tồn tại "ZZZ999" → vẫn save (Phase 3B validate)
- **Bước:** Step ticker, gửi "ZZZ999".
- **Kết quả mong đợi (user thấy):**
  - Bot accept và đi tiếp các step (quantity, price).
  - Cuối cùng asset save bình thường với ticker "ZZZ999".
  - Phase 3A chưa validate ticker thật — Phase 3B sẽ check vnstock và warn.

### TC-1.7.C2 — Normalize "VNM stocks" → "VNM"
- **Bước:** Step ticker, gửi "VNM stocks" (user thêm chữ rác).
- **Kết quả mong đợi (user thấy):**
  - Bot reply "✅ VNM" — strip word "stocks", chỉ lấy ticker.
  - Nếu spec chỉ làm `.upper().strip()` mà không lọc word, bot có thể accept "VNM STOCKS" → document gap.

### TC-1.7.C3 — Ticker chứa số "E1VFVN30" (ETF)
- **Bước:** Step ticker, gửi "E1VFVN30".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "✅ E1VFVN30" — giữ nguyên cả số.
  - Save thành công, dashboard hiển thị đúng "E1VFVN30".

### TC-1.7.C4 — Ticker ký tự lạ "!@#$" hoặc quá dài "VNMVNMVNMVNM"
- **Bước:** Step ticker, gửi "!@#$" rồi gửi "VNMVNMVNMVNM" (15+ chars).
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot reject với message "Mã cổ phiếu không hợp lệ, gõ lại nhé".
  - Hoặc bot accept (Phase 3A để Phase 3B validate) — document chọn behavior.
  - **KHÔNG** crash bot.

### TC-1.7.C5 — Quantity "abc" (không phải số) → bot ask retry
- **Bước:** Step quantity, gửi "abc".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Nhập số thôi nhé, ví dụ: 100".
  - User vẫn ở step quantity — gõ "100" tiếp tục được (không phải tap subtype lại).

### TC-1.7.C6 — Quantity âm "-100" → bot reject
- **Bước:** Step quantity, gửi "-100".
- **Kết quả mong đợi (user thấy):**
  - Bot reject với message "Số cổ phiếu phải > 0" (hoặc tương đương).
  - Asset KHÔNG được tạo, user retry được.

### TC-1.7.C7 — Quantity = 0 → bot reject hoặc warning
- **Bước:** Step quantity, gửi "0".
- **Kết quả mong đợi (user thấy):**
  - Bot reject với message "Số cổ phiếu phải > 0".
  - Hoặc cho phép nhưng kèm cảnh báo. Document.

### TC-1.7.C8 — Quantity float "100.5" (mua phần lẻ ETF/fund)
- **Bước:** Step quantity, gửi "100.5".
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot parse như "1005" (strip dấu chấm theo logic VN-style) — sai → document gap.
  - Hoặc bot reject "Số cổ phiếu phải là số nguyên".
  - Hoặc bot accept fractional cho ETF/fund.
  - **Document chọn behavior nào** — không silent.

### TC-1.7.C9 — Quantity rất lớn "1.000.000" (1 triệu cp)
- **Bước:** Step quantity, gửi "1000000" hoặc "1.000.000".
- **Kết quả mong đợi (user thấy):**
  - Bot accept và tính tổng = 1.000.000 × 45.000 = 45 tỷ.
  - Confirmation hiển thị "45 tỷ" (format ngắn) — không raw "45000000000".

### TC-1.7.C10 — Avg price "xyz" → bot ask retry
- **Bước:** Step price, gửi "xyz".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Nhập giá giúp mình nhé, ví dụ '45k' hoặc '45000'".
  - User vẫn ở step price.

### TC-1.7.C11 — Avg price = 0 hoặc âm → bot reject
- **Bước:** Gửi "0" rồi gửi "-1000" lần lượt ở step price.
- **Kết quả mong đợi (user thấy):**
  - Bot reject cả 2 với message "Giá phải > 0".
  - Asset KHÔNG được tạo với initial_value = 0.

### TC-1.7.C12 — Avg price decimal nhỏ "0.5" (penny stock)
- **Bước:** Step price, gửi "0.5".
- **Kết quả mong đợi (user thấy):**
  - Bot accept và tính total = 100 × 0.5 = 50.
  - Edge case rare nhưng không crash, không round về 0.

### TC-1.7.C13 — Current price < avg price (lỗ)
- **Bước:** Avg = 50000, tap "Nhập giá hiện tại" → 30000.
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị value = 3tr (= 100 × 30k).
  - Có dòng gain/loss âm: "📉 -2tr" (= 3tr - 5tr).
  - Net worth tăng đúng 3tr (current value), KHÔNG 5tr.

### TC-1.7.C14 — Current price >> avg price (10x lời)
- **Bước:** Avg = 10000, current = 100000.
- **Kết quả mong đợi (user thấy):**
  - Confirmation: value = 10tr, gain "📈 +9tr".
  - Net worth tăng đúng 10tr.

### TC-1.7.C15 — Tap "Dùng giá mua" 2 lần liên tiếp (double tap)
- **Bước:** Tap nhanh button "Dùng 45,000đ (giá mua)" 2 lần.
- **Kết quả mong đợi (user thấy):**
  - Chỉ **1 confirmation** message hiện ra.
  - Trong dashboard chỉ có **1 asset VNM** — KHÔNG duplicate 2 lần.

### TC-1.7.C16 — Abandon giữa wizard (đóng app ở step quantity)
- **Bước:** Nhập ticker xong, đóng Telegram, mở lại sau 1 ngày → gõ text bất kỳ.
- **Kết quả mong đợi (user thấy):**
  - Hoặc state vẫn còn → bot tiếp tục từ step quantity (text được hiểu là quantity).
  - Hoặc state expire → bot show main menu hoặc ask "Bạn đang muốn gì?".
  - **KHÔNG** có asset rỗng (chưa đủ data) bị lưu trong dashboard.

### TC-1.7.C17 — Gửi sticker / photo trong stock_ticker step
- **Bước:** Step ticker, gửi photo ngẫu nhiên (vd ảnh meme).
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Mình cần text mã cổ phiếu thôi, ví dụ 'VNM'" (hoặc tương đương).
  - KHÔNG crash, KHÔNG nhầm thành OCR.

### TC-1.7.C18 — Cross-user: A và B cùng nhập stock không lẫn data
- **Bước:** User A đang ở step price (đã có ticker VNM). User B trên account khác cùng start stock wizard, nhập "FPT 50 cp × 100k".
- **Kết quả mong đợi:**
  - User B thấy confirmation "FPT × 50 · 5tr" cho riêng B.
  - User A khi tap "Dùng giá mua" → asset save vào account A là VNM (KHÔNG bị lẫn FPT).
  - Net worth của A và B độc lập.

### TC-1.7.C19 — Wealth level update trong briefing/dashboard sau save lớn
- **Bước:** User starter (5tr cash). Save VNM 100 × 300.000 = 30tr stock.
- **Kết quả mong đợi (user thấy):**
  - Net worth ngay sau save: 35tr.
  - Briefing buổi sáng hôm sau (hoặc dashboard) phản ánh wealth level mới = "Young Professional" (đã vượt mốc 30tr).
  - Trước save: tone briefing là Starter; sau save: tone là Young Professional.

### TC-1.7.C20 — Confirmation format số nguyên không thừa decimal
- **Bước:** Save 100 cp × 45.000 (số tròn).
- **Kết quả mong đợi (user thấy):**
  - Hiển thị "4.5tr" hoặc "4,500,000đ".
  - **KHÔNG** có "4500000.00" (trailing zeros) hay ".0" thừa.

### TC-1.7.C21 — Hủy giữa wizard bằng `/huy`
- **Bước:** Đang ở step quantity hoặc price, gửi `/huy`.
- **Kết quả mong đợi (user thấy):**
  - Bot xác nhận hủy + về main menu.
  - Asset KHÔNG được tạo (dashboard không có VNM mới).
  - Nếu spec chưa có cancel command → document gap (tương tự P3A-6 TC-1.6.C19).

### TC-1.7.C22 — Foreign stock với ticker "AAPL" và USD
- **Bước:** Nếu wizard có sub-selection foreign_stock, chọn → ticker "AAPL", quantity 10, avg_price 150 (USD).
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot accept và lưu raw value (user tự quy đổi sang VND trước).
  - Hoặc bot reply "Phase 3A chỉ support cổ phiếu VN, foreign stock sẽ có sau".
  - Document chọn behavior — KHÔNG silent save với currency mơ hồ.

### TC-1.7.C23 — Decimal precision không bị float drift
- **Bước:** quantity = 333, avg_price = 12.345.
- **Kết quả mong đợi (user thấy):**
  - Tổng = 4.110.885đ exact (= 333 × 12.345).
  - Confirmation hiển thị "4.1tr" hoặc "4,110,885đ" — KHÔNG "4110884.99…" (float drift).

### TC-1.7.C24 — Net worth dùng current_value (không phải initial_value)
- **Bước:** Save VNM với avg=45k, current=50k (qua "Nhập giá hiện tại"). 100 cp.
- **Kết quả mong đợi (user thấy):**
  - Net worth tăng đúng 5tr (= 100 × 50k = current_value), KHÔNG 4.5tr (initial_value).
  - Trên dashboard, asset hiển thị giá trị 5tr; có thể có sub-text "Mua 4.5tr → +500k".

---

# P3A-8 — Asset Entry Wizard: Real Estate Flow

**Maps to AC:** `start_real_estate_wizard()`, ask subtype (`house_primary`, `land`), ask name + address (optional) + `initial_value` + `acquired_at` + `current_value`, metadata `{address, area_sqm, year_built}`, warning rental → Phase 4, parse "2 tỷ" / "2.5 tỷ" / "2500tr". Phase 3A chỉ cover **Case A (nhà ở)** và **Case C (đất)**, Case B (cho thuê) ở Phase 4.

> **Setup:** Onboard xong, gửi `/themtaisan` → tap "🏠 Bất động sản". Hoặc onboarding step 6 → tap "🏠 Tôi có BĐS".

## Happy Path

### TC-1.8.H1 — Vào RE wizard show 2 subtype buttons (Phase 3A scope)
- **Mục tiêu:** Verify entry point chỉ show Case A + C, KHÔNG show "cho thuê".
- **Bước:** Trigger callback `asset_add:real_estate`.
- **Kết quả mong đợi (user thấy):**
  - Bot reply message "🏠 Bất động sản\n\nLoại nào?" (hoặc tương đương).
  - **Đúng 2 inline buttons:** "🏡 Nhà ở (Case A)" và "🌾 Đất (Case C)".
  - **KHÔNG** có button "🏘️ Cho thuê" (Case B chỉ Phase 4).

### TC-1.8.H2 — Tap "Nhà ở" → bot ask tên BĐS
- **Bước:** Tap "🏡 Nhà ở".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Đặt tên cho BĐS này nhé?\nVí dụ: 'Nhà Mỹ Đình', 'Căn hộ Vinhomes'" (hoặc tương đương).
  - Bot không show keyboard (chờ text input).

### TC-1.8.H3 — Gõ tên "Nhà Mỹ Đình" → bot ask địa chỉ (có option skip)
- **Bước:** Step name, gửi "Nhà Mỹ Đình".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Địa chỉ? (có thể bỏ qua)".
  - Inline keyboard có button "⏭ Bỏ qua" (cho phép skip).
  - User vẫn có thể gõ address text.

### TC-1.8.H4 — Gõ địa chỉ "Số 1 ABC, Mỹ Đình, HN" → bot ask giá mua
- **Bước:** Step address, gửi "Số 1 ABC, Mỹ Đình, HN".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Mua giá bao nhiêu? (giá gốc)\n\nVí dụ: '2 tỷ', '2.5 tỷ', '2500tr'".
  - Address được lưu (sẽ thấy lại trong dashboard hoặc confirmation cuối).

### TC-1.8.H5 — Tap "⏭ Bỏ qua" address → bot vẫn đi tiếp
- **Bước:** Step address, tap "⏭ Bỏ qua".
- **Kết quả mong đợi (user thấy):**
  - Bot ask "Mua giá bao nhiêu?" (cùng prompt như H4).
  - Trong dashboard cuối, asset không có địa chỉ (hoặc field empty).
  - **KHÔNG** block flow.

### TC-1.8.H6 — Parse "2 tỷ" → save initial_value = 2 tỷ
- **Bước:** Step initial_value, gửi "2 tỷ".
- **Kết quả mong đợi (user thấy):**
  - Bot accept và chuyển sang step "Năm mua?".
  - Cuối flow, dashboard hiển thị giá gốc = 2 tỷ.

### TC-1.8.H7 — Parse "2.5 tỷ"
- **Bước:** Gửi "2.5 tỷ".
- **Kết quả mong đợi (user thấy):**
  - Bot accept (chuyển step), giá gốc = 2.500.000.000đ.
  - Confirmation cuối hiển thị "2.5 tỷ" (không "2.5tr" hoặc raw).

### TC-1.8.H8 — Parse "2500tr" (= 2.5 tỷ)
- **Bước:** Gửi "2500tr".
- **Kết quả mong đợi (user thấy):**
  - Cùng kết quả với "2.5 tỷ" — giá gốc = 2.500.000.000đ.
  - Confirmation hiển thị "2.5 tỷ" (chuẩn hoá unit lớn nhất).

### TC-1.8.H9 — Step năm mua → gõ "2020"
- **Bước:** Step `acquired_at`, gửi "2020".
- **Kết quả mong đợi (user thấy):**
  - Bot accept và chuyển sang "Giá ước tính hiện tại?\n(Nếu chưa biết, để bằng giá mua)".
  - Trong confirmation cuối, năm mua = 2020 (hoặc 01/2020).

### TC-1.8.H10 — Nhập current_value khác initial_value → save với gain
- **Bước:** Initial = 2 tỷ (mua 2020), current = 3 tỷ.
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị: "✅ Nhà Mỹ Đình · 3 tỷ" + dòng gain "📈 +1 tỷ".
  - Net worth tăng đúng 3 tỷ (current_value), KHÔNG 2 tỷ.

### TC-1.8.H11 — Note "update giá trị khi có thay đổi"
- **Bước:** Sau save thành công.
- **Kết quả mong đợi (user thấy):**
  - Confirmation có thêm dòng hint: "💡 Bạn có thể update giá trị BĐS khi có thay đổi (qua /capnhat hoặc dashboard)".
  - Vì BĐS không auto-update từ market, user cần biết cách self-update.

### TC-1.8.H12 — Tap "Đất (Case C)" → flow tương tự nhưng prompt khác
- **Bước:** Tap "🌾 Đất".
- **Kết quả mong đợi (user thấy):**
  - Bot ask name với ví dụ "Đất Ba Vì", "Đất Hòa Lạc" (khác với "Nhà Mỹ Đình").
  - Các step sau (address, initial_value, acquired_at, current_value) tương tự house_primary.
  - Trong dashboard, asset gán nhãn "Đất" (icon riêng).

### TC-1.8.H13 — Sau save: offer "Thêm tài sản khác"
- **Bước:** Sau confirmation BĐS.
- **Kết quả mong đợi (user thấy):**
  - Inline keyboard 2 buttons: "➕ Thêm tài sản khác" và "✅ Xong rồi" (giống P3A-6 H7).

### TC-1.8.H14 — Net worth/dashboard sau save dùng current_value
- **Bước:** Save BĐS 2 tỷ initial / 3 tỷ current. Mở dashboard / `/taisan`.
- **Kết quả mong đợi (user thấy):**
  - Asset hiển thị giá trị 3 tỷ (current), KHÔNG 2 tỷ (initial).
  - Net worth tổng cộng = 3 tỷ + các asset khác.
  - Có thể có sub-text "Mua 2 tỷ (2020) → +1 tỷ".

## Corner Cases

### TC-1.8.C1 — User mention "cho thuê" trong tên/địa chỉ → warning Phase 4
- **Bước:** Step name, gửi "Nhà cho thuê Mỹ Đình"; hoặc step address "... cho thuê 5tr/tháng".
- **Kết quả mong đợi (user thấy):**
  - Bot reply warning ấm áp: "Cho thuê (Case B) sẽ có ở Phase 4 nhé! Hiện tại mình lưu như BĐS thường 🙂".
  - Asset vẫn được save bình thường (Case A), không block flow.

### TC-1.8.C2 — Case B (cho thuê) chưa có button trong subtype list
- **Bước:** Tap "🏠 Bất động sản" trong menu chính. Quan sát keyboard.
- **Kết quả mong đợi (user thấy):**
  - **Đúng 2 buttons** (Nhà ở + Đất). KHÔNG có button "🏘️ Cho thuê".
  - Nếu user hỏi "tôi có nhà cho thuê", bot trả lời "Phase 4 sẽ hỗ trợ rental".

### TC-1.8.C3 — Parse "2ty" / "2tỷ" (không space) → vẫn work
- **Bước:** Step initial_value, gửi lần lượt "2ty" và "2tỷ".
- **Kết quả mong đợi (user thấy):**
  - Cả 2 đều save = 2.000.000.000đ.
  - Confirmation hiển thị "2 tỷ" (chuẩn hoá format).

### TC-1.8.C4 — Parse "2,5 tỷ" (dấu phẩy VN style)
- **Bước:** Gửi "2,5 tỷ".
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot accept = 2.5 tỷ (parse VN-style).
  - Hoặc bot reject + ask "Ghi là '2.5 tỷ' hoặc '2500tr' nhé".
  - **KHÔNG** parse nhầm thành 25 tỷ hoặc 2 tỷ.

### TC-1.8.C5 — Parse "2 tỷ rưỡi" (cách nói VN)
- **Bước:** Gửi "2 tỷ rưỡi".
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot parse = 2.5 tỷ.
  - Hoặc bot reject với hint "Ghi là '2.5 tỷ' nhé".
  - Document chọn behavior.

### TC-1.8.C6 — Năm mua = năm tương lai "2030"
- **Bước:** Step `acquired_at`, gửi "2030".
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot reject "Năm mua không thể trong tương lai".
  - Hoặc bot accept (user kế hoạch mua) — document chọn behavior.

### TC-1.8.C7 — Năm mua quá xa "1900"
- **Bước:** Gửi "1900".
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot reject với cảnh báo "Năm mua có vẻ quá lâu, bạn chắc không?".
  - Hoặc accept (sane validation tuỳ spec). KHÔNG crash.

### TC-1.8.C8 — Năm mua dạng "10/2020" (có tháng)
- **Bước:** Gửi "10/2020".
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot accept và lưu acquired = 10/2020.
  - Hoặc fallback chỉ lấy năm 2020.
  - Confirmation cuối hiển thị đúng theo behavior chọn.

### TC-1.8.C9 — initial_value âm hoặc 0 → bot reject
- **Bước:** Step initial_value, gửi "-1 tỷ" rồi "0".
- **Kết quả mong đợi (user thấy):**
  - Cả 2 đều bị reject với message "Giá phải > 0".
  - Asset KHÔNG được tạo, user retry được.

### TC-1.8.C10 — current_value < initial_value (BĐS xuống giá)
- **Bước:** Initial = 3 tỷ, current = 2.5 tỷ.
- **Kết quả mong đợi (user thấy):**
  - Save thành công.
  - Confirmation hiển thị "✅ … · 2.5 tỷ" + dòng loss "📉 -500tr".
  - Net worth tăng đúng 2.5 tỷ.

### TC-1.8.C11 — Tên rỗng hoặc chỉ whitespace → bot reject
- **Bước:** Step name, gửi "" hoặc "   " (chỉ space).
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Đặt tên giúp mình nhé" hoặc tương đương.
  - User vẫn ở step name, gõ tên thật là tiếp tục được.

### TC-1.8.C12 — Tên dài bất thường (>200 chars)
- **Bước:** Gửi tên 500 ký tự.
- **Kết quả mong đợi (user thấy):**
  - Hoặc bot truncate về 200 ký tự (confirmation hiển thị tên ngắn lại).
  - Hoặc bot reject "Tên quá dài, ngắn lại giúp mình".
  - **KHÔNG** crash bot (giống P3A-6 TC-1.6.C12).

### TC-1.8.C13 — Địa chỉ chứa ký tự đặc biệt + tiếng Việt có dấu
- **Bước:** Address: "Số 1, Đường Trần Phú, P. Mỹ Đình 1, Q. Nam Từ Liêm, Hà Nội".
- **Kết quả mong đợi (user thấy):**
  - Save thành công.
  - Trong dashboard / confirmation cuối, address hiển thị đúng dấu đầy đủ (UTF-8 không bị mất).

### TC-1.8.C14 — Skip address → asset trong dashboard không có địa chỉ
- **Bước:** Tap "⏭ Bỏ qua" ở step address. Hoàn tất wizard.
- **Kết quả mong đợi (user thấy):**
  - Asset save thành công.
  - Trong dashboard, field address của asset này empty / không hiển thị.
  - **KHÔNG** lưu literal "skip" hay "Bỏ qua" làm địa chỉ.

### TC-1.8.C15 — Phase 3A KHÔNG hỏi `area_sqm` / `year_built`
- **Bước:** Hoàn tất wizard từ đầu đến cuối, đếm số câu hỏi bot đặt.
- **Kết quả mong đợi (user thấy):**
  - Bot chỉ hỏi: subtype, name, address (skip-able), initial_value, acquired_at (năm), current_value.
  - **KHÔNG** hỏi diện tích (m²) hay năm xây dựng — Phase 3B/4 mới có.

### TC-1.8.C16 — current_value = initial_value (chưa có info)
- **Bước:** Step current_value, gõ "như giá mua" hoặc tap "Dùng giá mua" (nếu có button) hoặc copy initial_value.
- **Kết quả mong đợi (user thấy):**
  - Hoặc có button "Dùng giá mua" tương tự P3A-7 stock flow.
  - Hoặc bot parse "như giá mua" / "same".
  - Cuối cùng asset save với gain = 0; confirmation không có dòng "+/-".

### TC-1.8.C17 — Số rất lớn "100 tỷ" (biệt thự HNW)
- **Bước:** Step initial_value, gửi "100 tỷ".
- **Kết quả mong đợi (user thấy):**
  - Save thành công với giá = 100.000.000.000đ.
  - Confirmation hiển thị "100 tỷ" (chuẩn hoá).

### TC-1.8.C18 — Abandon flow giữa chừng (đóng app ở step initial_value)
- **Bước:** Đã có name + address, đóng app. Mở lại sau 1 ngày.
- **Kết quả mong đợi (user thấy):**
  - Hoặc state vẫn còn → bot tiếp tục từ step initial_value.
  - Hoặc state expire → bot ask lại từ đầu hoặc về main menu.
  - **KHÔNG** có asset rỗng / partial trong dashboard.

### TC-1.8.C19 — User gửi photo (vd ảnh sổ đỏ) trong wizard
- **Bước:** Step address, gửi photo.
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Mình cần text địa chỉ thôi, hoặc bỏ qua bằng nút ⏭".
  - **KHÔNG** nhầm thành OCR receipt, KHÔNG crash.

### TC-1.8.C20 — Cross-user: A's BĐS draft KHÔNG ảnh hưởng B
- **Bước:** A đang ở step initial_value (Nhà Mỹ Đình). B trên account khác cùng start RE wizard và nhập "Đất Ba Vì 1 tỷ".
- **Kết quả mong đợi:**
  - User B thấy confirmation "Đất Ba Vì · 1 tỷ" cho riêng B.
  - User A khi tiếp tục flow của mình → asset Nhà Mỹ Đình save vào account A.
  - Net worth của A và B độc lập.

### TC-1.8.C21 — Wealth level update sau save BĐS lớn (multi-level jump)
- **Bước:** User starter (5tr cash). Save BĐS 2 tỷ.
- **Kết quả mong đợi (user thấy):**
  - Net worth ngay sau save: ~2 tỷ.
  - Briefing hôm sau (hoặc dashboard) phản ánh wealth level mới = "High Net Worth" (jump 3 cấp từ Starter).
  - Tone của briefing chuyển sang HNW (sophisticated content).

### TC-1.8.C22 — Decimal precision không bị mất với số tỷ
- **Bước:** initial = 2.345.678.901,50đ (chính xác đến đồng).
- **Kết quả mong đợi (user thấy):**
  - Confirmation hiển thị "2.35 tỷ" (rounded ở UI), nhưng dashboard chi tiết hiển thị giá trị đầy đủ "2,345,678,901đ" — KHÔNG lệch float (vd 2.345.678.901,49).

### TC-1.8.C23 — Hủy giữa wizard bằng `/huy`
- **Bước:** Đang ở step `re_address`, gửi `/huy`.
- **Kết quả mong đợi (user thấy):**
  - Bot xác nhận hủy + về main menu.
  - Asset KHÔNG được tạo. Nếu spec chưa có cancel → document gap (giống P3A-6/P3A-7).

### TC-1.8.C24 — Format số tỷ đúng VN style
- **Bước:** Save BĐS 2.500.000.000đ.
- **Kết quả mong đợi (user thấy):**
  - Hiển thị "2.5 tỷ" (qua format VN).
  - **KHÔNG** raw "2500000000" hay "2,500tr" (vì >1 tỷ thì dùng "tỷ").

### TC-1.8.C25 — Tap "Thêm tài sản khác" sau save BĐS → restart wizard sạch
- **Bước:** Sau save BĐS, tap "➕ Thêm tài sản khác".
- **Kết quả mong đợi (user thấy):**
  - Bot quay về menu 6 buttons (Cash, Stock, Real Estate, Crypto, Gold, Other).
  - BĐS cũ KHÔNG bị duplicate khi user chọn lại Real Estate + nhập asset mới.

---

# P3A-9 — Integrate "First Asset" Step into Onboarding

**Maps to AC:** Onboarding step `step_6_first_asset` ngay sau `step_5_aha_moment`, keyboard 4 options (Cash / Invest / Real Estate / Skip), tap → route đúng wizard, "Skip" set `onboarding_skipped_asset=True` + reminder sau 3 ngày, sau complete → congrats + first net worth, **reuse existing wizards** không duplicate.

> **Setup:** User test account đã onboard tới ít nhất `step_5_aha_moment`. Nhờ admin reset `user.onboarding_step = AHA_MOMENT` và `onboarding_completed_at = NULL` nếu cần test lại.

## Happy Path

### TC-1.9.H1 — Sau `step_5_aha_moment` → bot trigger step_6_first_asset
- **Bước:** Đang ở `AHA_MOMENT`, tap button "🚀 Bắt đầu" (callback hoàn tất step_5).
- **Kết quả mong đợi (user thấy):**
  - Bot KHÔNG nhảy thẳng về main menu (chứng tỏ chưa graduate).
  - Bot reply message: "💎 Bước quan trọng cuối cùng {tên}!\n\nHãy thêm ít nhất 1 tài sản của bạn..." (theo spec line 979-987).

### TC-1.9.H2 — Step_6 hiển thị đúng 4 inline buttons
- **Bước:** Sau khi step_6 trigger.
- **Kết quả mong đợi (user thấy):** Inline keyboard có **đúng 4 buttons**:
  - "💵 Tiền trong NH (5 giây)"
  - "📈 Tôi có đầu tư"
  - "🏠 Tôi có BĐS"
  - "⏭ Skip, thêm sau"

### TC-1.9.H3 — Tap "💵 Tiền trong NH" → vào cash wizard (reuse)
- **Bước:** Tap "💵 Tiền trong NH (5 giây)".
- **Kết quả mong đợi (user thấy):**
  - Bot show prompt giống P3A-6 TC-1.6.H1: "💵 Tiền ở đâu?" + 4 subtype buttons.
  - Flow tiếp theo y hệt cash wizard thường (chứng tỏ reuse, không duplicate code).

### TC-1.9.H4 — Tap "📈 Tôi có đầu tư" → vào stock wizard
- **Bước:** Tap "📈 Tôi có đầu tư".
- **Kết quả mong đợi (user thấy):**
  - Bot ask ticker giống P3A-7 TC-1.7.H1: "📈 Cổ phiếu / Quỹ mới\n\nMã cổ phiếu (ticker) là gì?...".

### TC-1.9.H5 — Tap "🏠 Tôi có BĐS" → vào real estate wizard
- **Bước:** Tap "🏠 Tôi có BĐS".
- **Kết quả mong đợi (user thấy):**
  - Bot show 2 subtype buttons (Nhà ở + Đất) giống P3A-8 TC-1.8.H1.

### TC-1.9.H6 — Tap "⏭ Skip" → bot xác nhận + sẽ nhắc sau 3 ngày
- **Bước:** Tap "⏭ Skip, thêm sau".
- **Kết quả mong đợi (user thấy):**
  - Bot reply ấm áp: "OK, mình ghi nhớ rồi. 3 ngày nữa mình sẽ nhắc nhẹ nhé 💚" (hoặc tương đương).
  - Bot return về main menu (graduated khỏi onboarding dù skip).
  - Gõ `/start` sau đó → KHÔNG hiện step_6 nữa (đã skip rõ ràng).

### TC-1.9.H7 — Sau save first asset → congrats + show first net worth
- **Bước:**
  1. Vào step_6 → tap "💵 Tiền trong NH" → save "VCB 100tr".
- **Kết quả mong đợi (user thấy):**
  - Bot reply congrats: "🎉 Tài sản đầu tiên của bạn: VCB 100tr\n💎 Net worth: 100tr".
  - Net worth hiển thị đúng = giá trị asset vừa save (100tr), không phải 0 hay double-count.
  - Format theo VN style ("100tr"), không raw "100000000".
  - Bot return về main menu (đã graduate).

### TC-1.9.H8 — `onboarding_completed_at` chỉ set sau khi có asset HOẶC skip rõ
- **Mục tiêu:** Verify graduation gate đúng AC (qua user-observable transition).
- **Bước:**
  1. Đang ở step_6, gõ `/start` (chưa làm gì) → bot quay lại step_6.
  2. Save asset → gõ `/start` lại → KHÔNG hiện step_6 nữa.
  3. (Hoặc) Tap skip → gõ `/start` → KHÔNG hiện step_6 nữa.
- **Kết quả mong đợi (user thấy):**
  - Trước khi save/skip: `/start` luôn quay về step_6 (chưa graduate).
  - Sau khi save asset HOẶC tap skip: `/start` về main menu / help (đã graduate).

### TC-1.9.H9 — Reminder sau 3 ngày fire đúng nội dung + idempotent
- **Bước:**
  1. Tap skip ngày D.
  2. Đợi đến ngày D+3 (hoặc nhờ admin advance time).
- **Kết quả mong đợi (user thấy):**
  - Đúng ngày D+3, user nhận message từ bot (không cần thao tác): "3 ngày trước bạn skip thêm tài sản — giờ thêm 1 cái thử nhé? 💎".
  - Có 2 inline buttons: "💵 Thêm ngay" và "⏭ Để sau".
  - Reminder **chỉ fire 1 lần** trong ngày — không spam.

## Corner Cases

### TC-1.9.C1 — Skip → KHÔNG bị stuck ở step_6
- **Bước:** Tap skip. Hôm sau gõ `/start`.
- **Kết quả mong đợi (user thấy):**
  - `/start` về main menu, KHÔNG quay lại step_6 nữa.
  - User được coi là đã graduate (dù không add asset).

### TC-1.9.C2 — Abandon giữa wizard sau khi tap "Cash" → vẫn ở step_6 khi quay lại
- **Bước:**
  1. Tap "💵 Tiền trong NH" → vào cash wizard.
  2. Đóng app, không gửi text trong 1 ngày.
  3. Mở lại + gửi `/start`.
- **Kết quả mong đợi (user thấy):**
  - Bot trigger lại step_6 (4 buttons), KHÔNG nhảy về step cũ hơn (như AHA_MOMENT).
  - Hoặc bot tiếp tục từ cash wizard nếu state vẫn còn.
  - **KHÔNG** tạo asset rỗng / partial.

### TC-1.9.C3 — Sau save asset → `/start` lại KHÔNG quay về step_6
- **Bước:** Save xong asset đầu tiên. Gõ `/start`.
- **Kết quả mong đợi (user thấy):**
  - Bot route về main menu / help.
  - **KHÔNG** hiển thị step_6 lần 2.
  - Asset đầu tiên KHÔNG bị duplicate khi user thử thao tác lại.

### TC-1.9.C4 — Tap "Skip" 2 lần liên tiếp (double tap)
- **Bước:** Tap skip, ngay lập tức tap lại button skip cũ trong message lịch sử.
- **Kết quả mong đợi (user thấy):**
  - Lần 1: bot xác nhận skip + về main menu.
  - Lần 2: hoặc bot im lặng, hoặc reply "Bạn đã skip rồi 😊". KHÔNG hiển thị message confirm skip lần 2.
  - Reminder vẫn chỉ schedule 1 lần (D+3 ngày).

### TC-1.9.C5 — Tap "Skip" sau khi đã save asset (race / button cũ)
- **Bước:**
  1. Tap "Cash" → save asset thành công.
  2. Cuộn lên message cũ của step_6, tap lại "⏭ Skip, thêm sau".
- **Kết quả mong đợi (user thấy):**
  - Bot reply "Bạn đã thêm tài sản rồi 😊" (hoặc tương đương — detect đã graduate).
  - **KHÔNG** mark `onboarding_skipped_asset` (vì user thực sự không skip).

### TC-1.9.C6 — User vẫn ở step_5 (chưa tap "Bắt đầu") → step_6 KHÔNG hiện
- **Bước:** User đang ở `AHA_MOMENT`, chưa tap callback hoàn tất. Gõ text bừa.
- **Kết quả mong đợi (user thấy):**
  - Bot vẫn ở step_5 prompt — KHÔNG bypass sang step_6.
  - User phải tap "🚀 Bắt đầu" rõ ràng mới tới step_6.

### TC-1.9.C7 — Cross-user: A's onboarding step không ảnh hưởng B
- **Bước:** A đang `FIRST_ASSET`. B vừa tạo account mới (NOT_STARTED). Cả 2 cùng gõ `/start`.
- **Kết quả mong đợi:**
  - A → bot show step_6 (4 buttons).
  - B → bot show step_1 (welcome flow đầu).
  - Hoàn toàn độc lập, không có data leak.

### TC-1.9.C8 — Save asset thất bại (lỗi backend) trong wizard từ onboarding
- **Bước:** Tạo điều kiện DB / network lỗi (nhờ admin tắt DB tạm). Vào step_6 → Cash → "VCB 100tr".
- **Kết quả mong đợi (user thấy):**
  - Bot reply gracefully: "Có chút lỗi, bạn thử lại nhé 🙏" — KHÔNG leak stack trace, KHÔNG im lặng.
  - User vẫn ở step_6 (chưa graduate) — gõ `/start` quay lại step_6.
  - Khi backend hồi phục, user thử lại → save thành công và graduate đúng.

### TC-1.9.C9 — Reminder 3 ngày: user đã thêm asset trong khoảng đó → KHÔNG nhắc
- **Bước:**
  1. Ngày D: tap skip.
  2. Ngày D+1: user manual thêm asset qua `/themtaisan` (ngoài onboarding).
  3. Đợi đến ngày D+3.
- **Kết quả mong đợi (user thấy):**
  - Ngày D+3 user **KHÔNG** nhận reminder ("Bạn đã thêm tài sản rồi…" v.v.).
  - Tránh spam user đã action.

### TC-1.9.C10 — Reminder fire xong 1 lần, không nhắc nữa
- **Bước:** Ngày D+3 nhận reminder. Đợi đến ngày D+6 hoặc D+10, không thêm asset.
- **Kết quả mong đợi (user thấy):**
  - Bot **KHÔNG** gửi reminder lần 2 ở D+6/D+10.
  - Theo spec: "nhắc sau 3 ngày" (số ít) → chỉ 1 lần.
  - Nếu spec change muốn nhắc nhiều lần → document.

### TC-1.9.C11 — Tap "Cash" rồi `/huy` giữa wizard → quay về step_6
- **Bước:** Step_6 → tap Cash → đang ở step nhập tên/số tiền → gửi `/huy`.
- **Kết quả mong đợi (user thấy):**
  - Bot xác nhận hủy.
  - Bot quay về step_6 (4 buttons) — chưa graduate, user có thể chọn lại Cash/Stock/RE/Skip.
  - **KHÔNG** vô tình mark skipped, **KHÔNG** mắc kẹt giữa wizard sau cancel.

### TC-1.9.C12 — Net worth hiển thị sau save = đúng giá trị asset đầu tiên
- **Bước:** User mới (0 đồng), save VCB 100tr qua step_6 Cash.
- **Kết quả mong đợi (user thấy):**
  - Congrats message: "💎 Net worth: 100tr" — đúng = giá trị asset, không phải 0, không double-count.
  - Format VN ngắn ("100tr", không "100000000").

### TC-1.9.C13 — Admin reset onboarding → step_6 hiện lại
- **Bước:** Nhờ admin set `user.onboarding_step = FIRST_ASSET` + `onboarding_completed_at = NULL`. Gõ `/start`.
- **Kết quả mong đợi (user thấy):**
  - Bot trigger lại step_6 đầy đủ (4 buttons).
  - Giúp dev test re-onboarding flow dễ dàng.

### TC-1.9.C14 — Wealth level đúng sau save từ onboarding
- **Bước:** User starter (0 đồng) → step_6 → Cash → save "VCB 100tr".
- **Kết quả mong đợi (user thấy):**
  - Sau save, dashboard / briefing tiếp theo phản ánh wealth level = "Young Professional" (100tr ∈ [30tr, 200tr)).
  - Tone briefing (hôm sau) phù hợp Young Prof, không còn Starter.

### TC-1.9.C15 — Skip xong, vào lại `/themtaisan` → flow normal
- **Bước:**
  1. Tap skip → graduate.
  2. Sau đó user `/themtaisan`.
- **Kết quả mong đợi (user thấy):**
  - Bot vào menu chọn loại asset (6 buttons normal — Cash/Stock/RE/Crypto/Gold/Other).
  - **KHÔNG** quay lại step_6 (4 buttons "Tôi có…").
  - Asset save qua path này hoạt động bình thường.

### TC-1.9.C16 — Decimal precision xuyên suốt onboarding
- **Bước:** Save "VCB 1,234,567" qua step_6 Cash → ngay lập tức query net worth qua congrats message.
- **Kết quả mong đợi (user thấy):**
  - Net worth hiển thị đúng "1,234,567đ" hoặc "1.23tr" — KHÔNG "1234566.99…" (float drift).
  - Round-trip qua wizard không mất precision.

---

## ✅ Map ngược về Checklist Cuối Tuần 1

> Liên kết các test trên đây tới `phase-3a-detailed.md` line 1003-1015. Chỉ list checklist items có Telegram-testable coverage.

| Checklist Item (phase-3a-detailed.md) | Issue | Tests cover |
|---|---|---|
| Asset entry wizard cho Cash | P3A-6 | TC-1.6.H1-H8 + Corner C1-C19 |
| Asset entry wizard cho Stock | P3A-7 | TC-1.7.H1-H14 + Corner C1-C24 |
| Asset entry wizard cho Real Estate | P3A-8 | TC-1.8.H1-H14 + Corner C1-C25 |
| Onboarding flow có step "first asset" | P3A-9 | TC-1.9.H1-H9 + Corner C1-C16 |
| Tự test: tạo nhiều asset đa loại, net worth tính đúng | Cross-issue | TC-1.6.H7, TC-1.7.H10/H11, TC-1.8.H10/H14, TC-1.9.H7 |
| Wealth level adapt theo asset thay đổi | P3A-7, P3A-8, P3A-9 | TC-1.7.C19, TC-1.8.C21, TC-1.9.C14 |
| Cross-user isolation | All wizards | TC-1.6.C18, TC-1.7.C18, TC-1.8.C20, TC-1.9.C7 |
| Cancel / hủy giữa flow | All wizards | TC-1.6.C19, TC-1.7.C21, TC-1.8.C23, TC-1.9.C11 |

> **Note:** Checklist items thuộc DB / model / service / calculator (migrations, AssetService, NetWorthCalculator, WealthLevel detection) đã được tách ra file test internal layer riêng — không cover qua Telegram.

### Gaps & Open Questions (chỉ những điểm user có thể quan sát)

Các điểm sau spec chưa rõ ràng — cần product confirm trước khi implement, vì bot behavior khác nhau sẽ ảnh hưởng UX:

1. **Wizard `/cancel` / `/huy`** (TC-1.6.C19, TC-1.7.C21, TC-1.8.C23, TC-1.9.C11) — spec có command hủy không?
2. **Timeout policy** cho wizard state (TC-1.6.C9, TC-1.7.C16, TC-1.8.C18) — bao lâu thì expire?
3. **Parse VN style "2,5 tỷ" vs "2.5 tỷ"** (TC-1.8.C4) — accept dấu phẩy?
4. **Năm mua tương lai/quá xa** (TC-1.8.C6, C7) — accept hay reject?
5. **Foreign stock currency** (TC-1.7.C22) — chỉ VND hay support USD?
6. **Skip button sau save (race)** (TC-1.9.C5) — bot detect graduated đúng?
7. **Reminder lặp lại** (TC-1.9.C10) — chỉ 1 lần hay theo policy n lần?
8. **Quantity float "100.5"** (TC-1.7.C8) — accept fractional cho ETF/fund?
9. **Skip address hiển thị thế nào** (TC-1.8.C14) — empty hay "Không có"?

→ Trước khi merge implementation, các gap trên cần được resolve trong phase-3a-detailed.md hoặc inline doc của handler.

---

## 📊 Tổng kết Epic 1 (Telegram-only test cases)

- **Issues covered (qua Telegram bot):** P3A-6, P3A-7, P3A-8, P3A-9 (4 wizards/onboarding flows)
- **Tổng test cases:** ~117 tests
  - P3A-6 (Cash wizard): 8H + 19C = 27
  - P3A-7 (Stock wizard): 14H + 24C = 38
  - P3A-8 (RE wizard): 14H + 25C = 39
  - P3A-9 (Onboarding first asset): 9H + 16C = 25 (skip ~8 internal-only TCs)
- **Test bị lược bỏ khỏi file này (không Telegram-testable):**
  - Toàn bộ P3A-1 → P3A-5 (DB, model, service, calculator, wealth level — chỉ test qua psql/pytest)
  - Một số corner cases internal-only trong P3A-6 → P3A-9 (vd inspect `context.user_data`, analytics event firing, callback data corruption replay, code inspection cho duplicate logic, UTC timestamp internals)

> **Cách dùng:** Chạy file này khi cần verify UX/wizard hoạt động đúng từ phía user. Để verify layer DB/service, dùng file test internal riêng (sẽ bổ sung).

> **Next:** Khi Epic 2 (P3A-10 → P3A-15 — Morning Briefing) start, tạo file `phase-3a-epic-2.md` cùng cấu trúc — chỉ giữ TC user test qua Telegram (vd nhận briefing 7h sáng, tap inline buttons).
