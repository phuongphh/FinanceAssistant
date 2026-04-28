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
2. **Test account:** Dùng 1 Telegram account đã onboard tới ít nhất `step_5_aha_moment` (cho P3A-9), hoặc đã onboard xong (cho P3A-6/7/8 chạy độc lập qua `/them_tai_san`).
3. **Reset state khi cần:** Để test lại onboarding, nhờ admin reset `user.onboarding_step` về `AHA_MOMENT` và `onboarding_completed_at = NULL`.
4. **Cross-user tests:** Cần 2 Telegram account riêng biệt (User A + User B).

> **Lưu ý:** Một số TC tham chiếu hành vi internal (vd. metadata JSON, snapshot DB). Khi test qua Telegram, user verify thông qua **bot reply / dashboard / briefing tiếp theo** chứ không trực tiếp query DB. Test internal-only đã được lược bỏ.

---

# P3A-6 — Asset Entry Wizard: Cash Flow

**Maps to AC:** `start_cash_wizard()`, `handle_cash_subtype()`, `handle_cash_text_input()` parse flexible, save với `source="user_input"`, confirmation + net worth update, "Thêm tài sản khác" button, validation âm/zero, error parse → ask graceful.

> **Setup:** Onboard xong, gửi `/them_tai_san` rồi chọn "💵 Tiền mặt / TK", hoặc đang trong onboarding step 6 và tap "💵 Tiền trong NH (5 giây)".

## Happy Path

### TC-1.6.H1 — Vào cash wizard show 4 subtype buttons
- **Mục tiêu:** Verify entry point của cash flow đúng spec.
- **Bước:** Gửi `/them_tai_san` → tap "💵 Tiền mặt / TK".
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

> **Setup:** Onboard xong, gửi `/them_tai_san` → tap "📈 Chứng khoán". Hoặc onboarding step 6 → tap "📈 Tôi có đầu tư".

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

