# Phase 3.9 — Telegram Manual Test Cases

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

> **Dành cho:** Owner tự test trên Telegram chat — không cần chạy code, không cần DB, không cần API tool.
> **Cách dùng:** Gửi đúng tin nhắn ghi trong Steps vào chat bot → kiểm tra bot trả lời đúng Expected Results.
> **Tổng:** 38 test cases

---

## Ký hiệu

- ✅ **PASS** — Bot trả đúng như Expected Results
- ⚠️ **PASS WITH NOTES** — Đúng nhưng có chi tiết nhỏ khác
- ❌ **FAIL** — Bot không trả như mong đợi
- 🚫 **BLOCKED** — Không thể test (vd: ngoài giờ giao dịch)

---

## Personas

Trước khi test, cần có 2 account Telegram với data đã setup:

- **Hà** — holdings: VNM (200cp), HPG (100cp), VIC (50cp), FPT (30cp), BTC (0.05), ETH (0.5), Vàng 2 chỉ SJC, Cash 50tr VCB
- **Phương** — holdings: 8 mã cổ phiếu, BTC+ETH+SOL, Vàng 5 lượng, Cash 500tr MB, BĐS Q7 1.5 tỷ
- **BrandNew** — vừa onboard, chưa có holdings nào

---

# Phần 1: Briefing sáng

## TC-T001: Briefing đủ section — Hà
**Persona:** Hà | **Trigger:** Gửi lệnh hoặc đợi briefing tự động sáng

**Steps:**
1. Gửi: `/briefing`

**Expected Results:**
- Bot gửi 1 tin nhắn (hoặc nhiều tin liên tiếp) có đủ 5 phần:
  - Tổng tài sản hôm nay vs hôm qua (có số cụ thể, VD: "142tr (+1.2tr)")
  - Thị trường: VN-Index, Giá vàng, BTC — đều có số thực, không phải "N/A"
  - Danh mục: 4 cổ phiếu hiển thị với giá hiện tại
  - Tin tức: 3 tin liên quan VNM/HPG/VIC/FPT
  - Insight: ít nhất 1 nhận xét có nghĩa (vd: "HPG tăng 2% hôm nay")
- Gọi tên "Hà" trong tin nhắn
- Không có lỗi JSON hay text kỹ thuật lộ ra
- Persona ấm áp, không cứng nhắc

---

## TC-T002: Briefing portfolio rỗng — BrandNew
**Persona:** BrandNew

**Steps:**
1. Gửi: `/briefing`

**Expected Results:**
- Bot vẫn gửi briefing (không báo lỗi)
- Phần danh mục: "Bạn chưa có holdings nào" hoặc tương đương — KHÔNG crash
- Phần thị trường vẫn hiển thị (VN-Index, vàng, BTC)
- Tin tức: 3 tin thị trường chung
- Persona khuyến khích: "Hãy bắt đầu nhập tài sản đầu tiên" hoặc tương đương

---

## TC-T003: Briefing đa dạng — Phương
**Persona:** Phương

**Steps:**
1. Gửi: `/briefing`

**Expected Results:**
- Danh mục breakdown hiển thị đủ 5 loại: cổ phiếu, crypto, vàng, BĐS, tiền mặt
- Tổng tài sản > 2 tỷ (sanity check, không phải stub 0)
- Insight nhắc đến ít nhất 1 holding cụ thể (vd: "HPG", "BTC")
- Không có text "placeholder", "stub", "test data"

---

## TC-T004: Briefing — giá không phải dữ liệu cũ/fake
**Persona:** Hà (giờ giao dịch 9:00–15:00 T2–T6)

**Steps:**
1. Gửi: `/briefing` lúc khoảng 10:00 sáng ngày thường
2. Mở SSI app hoặc CafeF.vn — ghi nhận giá VNM cùng lúc

**Expected Results:**
- Giá VNM trong briefing khớp với SSI app ± 500 VND
- Giá BTC khớp với CoinGecko.com ± 0.5%
- Giá vàng khớp với SJC.com.vn ± 0

---

# Phần 2: Truy vấn tài sản

## TC-T005: Xem toàn bộ tài sản — Hà
**Persona:** Hà

**Steps:**
1. Gửi: `tài sản của tôi`

**Expected Results:**
- Bot liệt kê 4 cổ phiếu với: số cp, giá hiện tại, tổng giá trị, % lãi/lỗ so giá mua
- Ví dụ format: "VNM: 200cp × 72,500 = 14.5tr (+3.6%)"
- Crypto (BTC, ETH) hiển thị giá VND
- Vàng: "2 chỉ × [giá SJC] = [tổng]tr"
- Cash: "50tr tại VCB"
- Tổng cuối cùng có số cụ thể

---

## TC-T006: Xem tài sản khi provider không có giá
**Persona:** Hà (test ngoài giờ giao dịch hoặc lúc thị trường đóng)

**Steps:**
1. Gửi: `tài sản` lúc tối hoặc cuối tuần

**Expected Results:**
- Bot vẫn trả kết quả (không báo lỗi)
- Có chú thích nhỏ kiểu: "(Giá cổ phiếu là dữ liệu cũ từ phiên trước)"
- % lãi/lỗ hoặc không hiển thị hoặc hiển thị "—"
- Phần crypto vẫn có giá real-time (vì 24/7)

---

## TC-T007: Xem crypto
**Persona:** Phương

**Steps:**
1. Gửi: `crypto của tôi`

**Expected Results:**
- 3 holdings: BTC, ETH, SOL
- Mỗi dòng: số lượng × giá VND = tổng
- Cross-check: tổng BTC khớp với (0.5 × giá BTC hiện tại trên CoinGecko)

---

## TC-T008: Xem vàng
**Persona:** Phương

**Steps:**
1. Gửi: `vàng của tôi`

**Expected Results:**
- "5 lượng SJC × [giá/lượng] = [tổng]"
- Giá/lượng > 70 triệu (sanity check)
- Có ghi rõ nguồn/thời gian cập nhật

---

# Phần 3: Truy vấn thị trường

## TC-T009: Hỏi VN-Index
**Steps:**
1. Gửi: `VN-Index hôm nay thế nào?`

**Expected Results:**
- Bot trả điểm VN-Index cụ thể (vd: "1,287.45")
- Có thay đổi so hôm qua: "+12.3 (+0.97%)" hoặc tương đương
- Không có text "chưa có dữ liệu", "stub", hay số 0

---

## TC-T010: Hỏi giá Bitcoin
**Steps:**
1. Gửi: `Bitcoin bao nhiêu rồi?`

**Expected Results:**
- Giá BTC bằng VND (> 2 tỷ VND, sanity check)
- Có giá USD kèm theo
- Có % thay đổi 24h
- Ghi nguồn: "CoinGecko" hoặc tương đương

---

## TC-T011: Hỏi giá vàng SJC
**Steps:**
1. Gửi: `vàng SJC hôm nay bao nhiêu?`

**Expected Results:**
- Giá mua và giá bán của SJC (hai con số khác nhau, giá bán > giá mua)
- Giá > 70 triệu/lượng (sanity)
- Có thời gian cập nhật

---

## TC-T012: Hỏi lãi suất ngân hàng
**Steps:**
1. Gửi: `lãi suất ngân hàng tốt nhất hiện nay?`

**Expected Results:**
- Bot liệt kê top 3–5 ngân hàng lãi suất cao nhất (kỳ hạn 12 tháng)
- Mỗi dòng: tên ngân hàng + % lãi suất
- Tất cả % trong khoảng 3–10% (sanity check)
- Có ngày cập nhật

---

## TC-T013: Hỏi lãi suất ngân hàng cụ thể
**Steps:**
1. Gửi: `Lãi suất gửi 12 tháng VCB?`

**Expected Results:**
- Bot trả lãi suất VCB kỳ hạn 12 tháng cụ thể (số %)
- Có thể có so sánh: "VCB thấp hơn / cao hơn ngân hàng X"
- Không trả về số 0 hay "không có dữ liệu"

---

## TC-T014: Hỏi giá cổ phiếu cụ thể
**Steps:**
1. Gửi: `HPG giá bao nhiêu?`

**Expected Results:**
- Giá HPG hiện tại (VND, > 20,000 sanity)
- % thay đổi hôm nay
- Khối lượng hoặc metadata cơ bản

---

# Phần 4: Input thông minh (edge cases)

## TC-T015: Symbol chữ thường
**Steps:**
1. Gửi: `vnm giá bao nhiêu?`
2. Gửi: `Vnm hôm nay?`

**Expected Results:**
- Cả 2 tin nhắn đều trả giá VNM đúng (không báo "không tìm thấy")
- Kết quả giống nhau như khi gửi "VNM"

---

## TC-T016: Symbol có khoảng trắng thừa
**Steps:**
1. Gửi: `BTC ` (có dấu cách cuối)
2. Gửi: ` btc` (có dấu cách đầu)

**Expected Results:**
- Bot hiểu và trả giá BTC bình thường
- Không báo lỗi vì khoảng trắng

---

## TC-T017: Symbol không tồn tại
**Steps:**
1. Gửi: `giá cổ phiếu XYZNOTREAL?`

**Expected Results:**
- Bot trả lời lịch sự: "Mình không tìm thấy mã XYZNOTREAL" hoặc tương đương
- KHÔNG crash hay im lặng
- Persona vẫn ấm áp, không cứng

---

# Phần 5: Nhận alert giá (passive — chờ điều kiện thị trường)

> Phần này không thể trigger chủ động từ Telegram. Chờ khi thị trường biến động > 5% trong ngày.

## TC-T018: Alert khi cổ phiếu tăng/giảm mạnh
**Precondition:** Hà đang giữ HPG; HPG biến động > 5% trong 1 phiên

**Expected Results (nhận từ bot):**
- Bot gửi tin chủ động (không cần hỏi)
- Format: "HPG [tăng/giảm] X% trong 15 phút qua (từ A → B)"
- Không nhận quá 3 alert/ngày từ bot
- Không nhận 2 alert cùng 1 mã trong vòng 30 phút

---

# Phần 6: Hội thoại tự do với agent

## TC-T019: Câu hỏi tổng hợp nhiều nguồn
**Steps:**
1. Gửi: `So sánh BTC và vàng SJC 3 tháng qua, cái nào lời hơn?`

**Expected Results:**
- Bot trả lời có dữ liệu thực, không phải "tôi không có thông tin"
- Có số % hoặc giá trị tăng/giảm
- Ngôn ngữ dễ hiểu, persona ấm

---

## TC-T020: Gợi ý tài chính
**Persona:** Phương (có 500tr tiền mặt tại MB)

**Steps:**
1. Gửi: `Mình đang để 500tr tiền mặt ở MB, nên làm gì để sinh lời hơn?`

**Expected Results:**
- Bot gợi ý cụ thể: so sánh lãi suất các ngân hàng, hoặc nhắc đến kênh đầu tư khác
- Có số liệu thực (lãi suất % của ngân hàng cụ thể)
- Tone advisory, không phán xét, không hối thúc
- KHÔNG trả về câu chung chung kiểu "bạn nên tham khảo chuyên gia tài chính"

---

## TC-T021: Hỏi tin tức liên quan holding
**Persona:** Hà (holds HPG)

**Steps:**
1. Gửi: `Có tin gì về Hòa Phát không?`

**Expected Results:**
- Bot lấy tin tức liên quan HPG (nếu có trong hệ thống)
- Tin nhắn ngắn gọn, dễ đọc
- Nếu không có tin mới: "Chưa có tin mới về HPG hôm nay" — KHÔNG crash

---

## TC-T022: Câu hỏi ngoài phạm vi
**Steps:**
1. Gửi: `Hôm nay thời tiết thế nào?`

**Expected Results:**
- Bot từ chối lịch sự, giải thích mình chỉ hỗ trợ tài chính
- Persona ấm, không cụt lủn
- Gợi ý câu hỏi tài chính có thể hỏi

---

# Phần 7: Các tính năng cũ vẫn hoạt động (Regression)

## TC-T023: Xem hồ sơ cá nhân
**Steps:**
1. Gửi: `/profile` hoặc `thông tin của tôi`

**Expected Results:**
- Bot hiển thị: tên, mức tài sản (wealth level badge), ngày tham gia
- Không có lỗi

---

## TC-T024: Gửi feedback
**Steps:**
1. Gửi: `/feedback Bot rất hữu ích!`

**Expected Results:**
- Bot xác nhận đã nhận feedback
- Không báo lỗi

---

## TC-T025: Query chi tiêu tháng này
**Steps:**
1. Gửi: `tháng này tôi chi bao nhiêu?`

**Expected Results:**
- Bot trả tổng chi tiêu tháng hiện tại
- Có breakdown theo category nếu có data
- Số hợp lý (không âm, không vô hạn)

---

## TC-T026: Nhập giao dịch mới
**Steps:**
1. Gửi: `tôi vừa mua cà phê 45k`

**Expected Results:**
- Bot xác nhận đã ghi: "Đã ghi nhận chi 45,000 VND — Cà phê" (hoặc tương đương)
- Persona ấm, không cứng nhắc

---

## TC-T027: Xem mục tiêu tài chính
**Steps:**
1. Gửi: `mục tiêu của tôi`

**Expected Results:**
- Bot liệt kê goals đang có (nếu đã setup)
- Hoặc: "Bạn chưa có mục tiêu nào, muốn tạo không?" nếu chưa có
- Không crash

---

## TC-T028: Intent classifier — câu hỏi đa dạng
**Steps:** Gửi lần lượt 5 câu sau (mỗi câu riêng):
1. `tài sản của tôi có gì?`
2. `tôi đang lãi hay lỗ?`
3. `tiết kiệm của tôi`
4. `dòng tiền tháng này`
5. `mục tiêu mua nhà của tôi đến đâu rồi?`

**Expected Results:**
- Mỗi câu bot hiểu đúng ý định và trả đúng loại thông tin
- Không câu nào bị nhầm sang intent khác
- Không câu nào bot im lặng hoặc báo lỗi

---

# Phần 8: Tone & Persona

## TC-T029: Không có ngôn ngữ harsh khi chi tiêu nhiều
**Steps:**
1. Gửi: `tháng này tôi xài quá nhiều, vượt budget`

**Expected Results:**
- Bot KHÔNG dùng: "bạn đã tiêu xài quá mức", "cần kiểm soát chi tiêu ngay", hay từ ngữ phán xét
- Tone: đồng cảm, hỗ trợ — "Ổn thôi, tháng sau mình tính cùng nhé" hoặc tương đương
- Vẫn có thông tin hữu ích (so sánh với tháng trước, gợi ý điều chỉnh nhẹ)

---

## TC-T030: Tiếng Việt tự nhiên (không dịch máy)
**Steps:**
1. Đọc 3 responses của bot trong briefing, advisory, query
2. Đọc to thử từng câu

**Expected Results:**
- Không có câu nào nghe cứng như dịch từ tiếng Anh
- Không có từ như: "Tôi xin lỗi vì sự bất tiện này", "Hãy liên hệ chuyên gia", "Portfolio của bạn đang được optimize"
- Ngôn ngữ thân mật, đúng cách người Việt nói chuyện bình thường

---

## TC-T031: Gọi tên người dùng đúng
**Persona:** Hà và Phương

**Steps:**
1. Trigger briefing cho Hà → kiểm tra bot gọi "Hà"
2. Trigger briefing cho Phương → kiểm tra bot gọi "Phương"

**Expected Results:**
- Bot gọi đúng tên, không gọi "bạn" suốt hoặc không có tên
- Không gọi tên người kia

---

# Phần 9: Smoke Test tổng thể

## TC-T032: Toàn bộ flow trong 10 phút
**Persona:** Owner (real account)

**Steps:** Gửi lần lượt trong 10 phút:
1. `/briefing`
2. `tài sản của tôi`
3. `VN-Index hôm nay?`
4. `vàng SJC bao nhiêu?`
5. `lãi suất tốt nhất hiện tại?`
6. `Bitcoin bao nhiêu?`
7. `HPG hôm nay?`

**Expected Results:**
- Tất cả 7 tin nhắn nhận được response trong < 5 giây
- Không tin nào báo lỗi
- Tất cả số liệu có vẻ thực tế (không phải 0, không phải placeholder)
- Persona nhất quán, ấm áp xuyên suốt

---

## TC-T033: Cross-validate giá thực tế
**Steps:**
1. Lúc 10:30 sáng ngày thường, mở song song:
   - SSI app (hoặc CafeF.vn) — ghi giá VNM + HPG
   - CoinGecko.com — ghi giá BTC
   - SJC.com.vn — ghi giá vàng
2. Gửi bot: `briefing` hoặc query từng loại

**Expected Results:**
- Giá cổ phiếu lệch ≤ 500 VND so SSI
- Giá BTC lệch ≤ 0.5% so CoinGecko
- Giá vàng SJC khớp chính xác

---

## TC-T034: Multi-tenancy — không lộ dữ liệu chéo
**Persona:** Hà (không có BĐS), Phương (có BĐS Q7)

**Steps:**
1. Login với tài khoản Hà
2. Gửi: `bất động sản của tôi`

**Expected Results:**
- Bot không hiển thị BĐS Q7 của Phương
- Bot trả: "Bạn chưa có bất động sản nào" hoặc tương đương
- Dữ liệu Phương KHÔNG lộ sang Hà

---

## TC-T035: 4 personas đều briefing được
**Steps:**
1. Lần lượt trigger `/briefing` cho Hà, Phương, BrandNew

**Expected Results:**
- Hà: tin tức có ít nhất 1 trong VNM/HPG/VIC/FPT
- Phương: breakdown 5 loại tài sản, tổng > 2 tỷ
- BrandNew: empty state graceful, có lời khuyến khích bắt đầu

---

# Phần 10: Kiểm tra dữ liệu cũ không lộ ra

## TC-T036: Không có stub/placeholder trong bất kỳ response nào
**Steps:**
Gửi 10 câu hỏi khác nhau về thị trường và portfolio, đọc kỹ responses

**Expected Results:**
- KHÔNG có từ nào: "stub", "placeholder", "test", "TODO", "hardcoded", "N/A" (trừ khi thực sự không có dữ liệu hợp lý)
- Tất cả số đều có vẻ là dữ liệu thật

---

## TC-T037: Giá không bao giờ là 0 hoặc 1
**Steps:**
1. Query: `giá BTC`, `giá vàng`, `giá VNM`, `giá HPG`

**Expected Results:**
- Không có response nào trả về: giá = 0, giá = 1, giá = 999, giá = 9999999
- Tất cả trong vùng thực tế:
  - VNM: 60,000 – 100,000 VND
  - HPG: 15,000 – 40,000 VND
  - BTC: > 2,000,000,000 VND
  - Vàng SJC: > 70,000,000 VND/lượng

---

## TC-T038: Briefing sau 1 tuần dùng thực tế
**Thực hiện:** Owner dùng bot bình thường 7 ngày

**Checklist cuối tuần:**
- [ ] Không có ngày nào briefing báo lỗi
- [ ] Giá thị trường trông thực tế mỗi ngày
- [ ] Không nhận quá 3 alert/ngày
- [ ] Tin tức trong briefing có vẻ liên quan holdings
- [ ] Tone của bot nhất quán, không có ngày nào trả lời cứng/lạ
- [ ] Không có dữ liệu của account này lộ sang account khác

---

# Tracking

| TC# | Mô tả ngắn | Status | Ngày test | Ghi chú |
|---|---|---|---|---|
| TC-T001 | Briefing Hà — đủ 5 section | | | |
| TC-T002 | Briefing BrandNew — empty graceful | | | |
| TC-T003 | Briefing Phương — 5 loại tài sản | | | |
| TC-T004 | Giá briefing khớp thực tế | | | |
| TC-T005 | Tài sản đầy đủ — Hà | | | |
| TC-T006 | Tài sản ngoài giờ — có banner | | | |
| TC-T007 | Crypto Phương | | | |
| TC-T008 | Vàng Phương | | | |
| TC-T009 | Hỏi VN-Index | | | |
| TC-T010 | Hỏi Bitcoin | | | |
| TC-T011 | Hỏi vàng SJC | | | |
| TC-T012 | Lãi suất tốt nhất | | | |
| TC-T013 | Lãi suất VCB cụ thể | | | |
| TC-T014 | Giá HPG | | | |
| TC-T015 | Symbol chữ thường | | | |
| TC-T016 | Symbol khoảng trắng thừa | | | |
| TC-T017 | Symbol không tồn tại | | | |
| TC-T018 | Alert giá (passive) | | | |
| TC-T019 | So sánh BTC vs vàng | | | |
| TC-T020 | Gợi ý tài chính | | | |
| TC-T021 | Tin tức về HPG | | | |
| TC-T022 | Câu hỏi ngoài phạm vi | | | |
| TC-T023 | Xem profile | | | |
| TC-T024 | Gửi feedback | | | |
| TC-T025 | Chi tiêu tháng này | | | |
| TC-T026 | Nhập giao dịch | | | |
| TC-T027 | Xem goals | | | |
| TC-T028 | Intent 5 loại câu hỏi | | | |
| TC-T029 | Không harsh khi overspend | | | |
| TC-T030 | Tiếng Việt tự nhiên | | | |
| TC-T031 | Gọi đúng tên | | | |
| TC-T032 | Smoke test 10 phút | | | |
| TC-T033 | Cross-validate giá thực | | | |
| TC-T034 | Multi-tenancy | | | |
| TC-T035 | 3 personas đều briefing OK | | | |
| TC-T036 | Không có stub/placeholder | | | |
| TC-T037 | Giá không phải 0 hoặc 1 | | | |
| TC-T038 | 7 ngày dùng thực tế | | | |

**Tổng: 38 test cases**
