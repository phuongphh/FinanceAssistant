# Phase 4B — Manual Test Cases

**Total:** 56 test cases  
**Organized by:** Epic → Feature area  
**Format:** TC-{AREA}-{ID}: Title | Precondition | Steps | Expected Result

---

## Epic 1: Twin Polish

### TC-TP-01: Accuracy Delta in Morning Briefing
**Precondition:** User có ≥ 2 weekly twin projections. Week N-1 P50 = 1.2 tỷ. Current net worth = 1.18 tỷ.  
**Steps:**
1. Chờ hoặc trigger morning briefing
**Expected:** Briefing hiển thị "Tuần trước Bé Tiền dự báo P50 = 1.2 tỷ, thực tế = 1.18 tỷ (−2%)"

### TC-TP-02: Accuracy Delta — Actual Below P10 (Reassure Tone)
**Precondition:** Actual net worth < P10 của projection tuần trước (thị trường crash mạnh).  
**Steps:**
1. Trigger morning briefing
**Expected:** Briefing có tone reassure (không phán xét), không dùng từ "thất bại" hay "tệ"

### TC-TP-03: Accuracy Delta — Actual Above P90 (Celebrate)
**Precondition:** Actual net worth > P90 của projection tuần trước (danh mục bứt phá).  
**Steps:**
1. Trigger morning briefing
**Expected:** Briefing có tone celebrate, Bé Tiền thể hiện vui mừng

### TC-TP-04: Accuracy Delta — Not Shown If < 2 Projections
**Precondition:** User mới dùng Twin, chỉ có 1 weekly projection.  
**Steps:**
1. Trigger morning briefing
**Expected:** Accuracy delta KHÔNG hiển thị trong briefing. Không có lỗi.

### TC-TP-05: On-Demand Recompute — Large Asset Update
**Precondition:** User có net worth 2 tỷ. Last twin recompute > 30 phút trước.  
**Steps:**
1. Thêm tài sản mới trị giá 200 triệu (10% net worth)
**Expected:** Trong vòng 30 phút: nhận Telegram notification "🔮 Bé Tiền đã cập nhật dự báo tương lai của bạn"

### TC-TP-06: On-Demand Recompute — Small Asset Update (No Trigger)
**Precondition:** User có net worth 2 tỷ.  
**Steps:**
1. Cập nhật giá trị cổ phiếu từ 95 triệu lên 98 triệu (1.5% change)
**Expected:** KHÔNG nhận notification recompute. Recompute chỉ xảy ra vào Sunday cron.

### TC-TP-07: On-Demand Recompute — Debounce
**Precondition:** User có net worth 2 tỷ.  
**Steps:**
1. Thêm tài sản 200 triệu (trigger threshold)
2. Trong vòng 5 phút: thêm 2 tài sản khác cũng ≥ 5%
**Expected:** Chỉ nhận 1 notification recompute (không nhận 3 notifications)

### TC-TP-08: LLM Narrative v2 — References Wealth Level
**Precondition:** User có wealth level "Tích lũy".  
**Steps:**
1. Request twin narrative (qua Telegram hoặc Mini App)
**Expected:** Narrative đề cập "Tích lũy" hoặc language phù hợp level này. Không generic.

### TC-TP-09: LLM Narrative v2 — References Life Events
**Precondition:** User có life event "Mua nhà 2028" active.  
**Steps:**
1. Request twin narrative
**Expected:** Narrative nhắc đến "mua nhà" hoặc "2028" ít nhất một lần.

### TC-TP-10: Scenario Comparison Delta Badges
**Precondition:** User có twin projection với cả Current và Optimal cones.  
**Steps:**
1. Mở Mini App → xem Twin section
**Expected:** Delta badges hiển thị tại 2027, 2030, 2035 với format "Optimal +X%". CTA hiển thị số tiền cụ thể (X triệu/tháng).

### TC-TP-11: Uncertainty Breakdown — Top 2 Contributors
**Precondition:** User có danh mục gồm cổ phiếu VN (50%), BĐS (30%), tiền gửi (20%).  
**Steps:**
1. Xem twin projection (Mini App hoặc Telegram)
**Expected:** Hiển thị "Yếu tố bất định lớn nhất: Cổ phiếu VN (X%), BĐS (Y%)" với tooltip giải thích.

---

## Epic 2: Life Event Simulator

### TC-LE-01: Add Life Event — Buy House (Happy Path)
**Precondition:** User chưa có life events.  
**Steps:**
1. Gửi `/life_events` → chọn "Thêm mới"
2. Chọn "🏠 Mua nhà"
3. Bé Tiền hiện preset: "3.5 tỷ, -8 triệu/tháng, 20 năm"
4. Nhập năm dự kiến: "2028"
5. Chọn "Dùng ước tính này"
6. Confirm
**Expected:** Event saved. Nhận message "🔮 Bé Tiền đang tính lại tương lai của bạn...". Sau khi recompute xong: nhận impact chart.

### TC-LE-02: Add Life Event — Custom Override
**Precondition:** Không có life events.  
**Steps:**
1. `/life_events` → Thêm mới → Mua nhà
2. Nhập năm "2027"
3. Chọn "Tùy chỉnh chi tiết"
4. Nhập chi phí: "5000000000" (5 tỷ)
5. Nhập trả góp: "12000000" (12 triệu/tháng)
6. Nhập thời hạn: "240" tháng
7. Confirm
**Expected:** Event saved với custom values (không phải preset). Impact chart hiển thị đúng giá trị custom.

### TC-LE-03: Add Life Event — Planned Date in the Past
**Precondition:** Không có life events.  
**Steps:**
1. `/life_events` → Thêm mới → Mua nhà
2. Nhập năm: "2020" (quá khứ)
**Expected:** Bé Tiền hiển thị error thân thiện: "Ngày bạn nhập đã qua rồi 😊 Bạn muốn nhập năm khác không?" Không save event. Không crash.

### TC-LE-04: View Life Events List
**Precondition:** User có 2 active life events (mua nhà 2028, kết hôn 2026).  
**Steps:**
1. `/life_events` → Xem danh sách
**Expected:** Hiển thị danh sách 2 events với: icon + tên + năm dự kiến + chi phí ước tính. Format đẹp, dễ đọc.

### TC-LE-05: Delete Life Event
**Precondition:** User có life event "Mua nhà 2028".  
**Steps:**
1. `/life_events` → Xóa
2. Chọn event "Mua nhà 2028"
3. Bé Tiền confirm: "Bạn có chắc muốn xóa sự kiện này không?"
4. Xác nhận xóa
**Expected:** Event bị soft delete (deleted_at set). Không hiển thị trong danh sách nữa. Twin recompute triggered.

### TC-LE-06: Life Event Impact Chart — Before/After Cones
**Precondition:** User vừa thêm "Mua nhà 2028, 3.5 tỷ".  
**Steps:**
1. Chờ/trigger impact chart generation
**Expected:** Nhận PNG chart với 2 cones màu khác nhau (xanh = before, cam = after). Impact labels tại 2030, 2035. Watermark "dự phóng, không phải dự đoán".

### TC-LE-07: Life Event Impact — Multiple Events
**Precondition:** User có 2 events: mua nhà 2028 + con đầu lòng 2029.  
**Steps:**
1. Xem Mini App → tab Kế hoạch
2. Toggle OFF "Con đầu lòng"
**Expected:** Cone chart cập nhật chỉ phản ánh mua nhà (không có first_child). Toggle lại ON → cả 2 events reflected.

### TC-LE-08: Mini App Life Events Panel — Empty State
**Precondition:** User chưa có life events.  
**Steps:**
1. Mở Mini App → tab Kế hoạch
**Expected:** Empty state: "Chưa có kế hoạch nào. Nhấn để thêm sự kiện đầu tiên →". Button → deep link Telegram.

### TC-LE-09: LLM Narrative — Buy House Framing
**Precondition:** User có life event "Mua nhà 2028".  
**Steps:**
1. Request twin narrative
**Expected:** Narrative frame mua nhà tích cực: đề cập "đầu tư" hoặc "trade-off bình thường". KHÔNG có từ "nguy hiểm", "cảnh báo", "thất bại".

### TC-LE-10: LLM Narrative — First Child Framing
**Precondition:** User có life event "Con đầu lòng 2029".  
**Steps:**
1. Request twin narrative
**Expected:** Narrative supportive về con cái. KHÔNG có gợi ý trì hoãn sinh con. KHÔNG phán xét.

### TC-LE-11: All 5 Event Types Available
**Precondition:** Không có life events.  
**Steps:**
1. `/life_events` → Thêm mới
**Expected:** Hiển thị 5 buttons: Mua nhà, Kết hôn, Con đầu lòng, Học phí ĐH, Nghỉ hưu sớm. Và "Tùy chỉnh". Tổng 6 options.

### TC-LE-12: Life Event — Wedding Preset
**Precondition:** Không có life events.  
**Steps:**
1. `/life_events` → Thêm mới → Kết hôn
2. Nhập năm "2027"
3. Dùng preset
**Expected:** Preset hiển thị 500 triệu chi phí một lần. Không có recurring delta (wedding không có ongoing cost trong preset).

---

## Epic 3: Cashflow Forecasting v2

### TC-CF-01: Recurring Detection — Salary Detected
**Precondition:** User có transaction history 3+ tháng. Tháng 1, 2, 3: mỗi tháng có giao dịch +20,000,000 VND vào ngày 1.  
**Steps:**
1. Chờ/trigger Monday detection cron
**Expected:** Pattern "Lương ~20 triệu, ngày 1 hàng tháng, income" được tạo với confidence ≥ 0.9 và `is_confirmed = false`.

### TC-CF-02: Recurring Detection — Random Transactions Not Detected
**Precondition:** User có 3 transactions trong 3 tháng nhưng với amounts và dates khác nhau (17tr, 23tr, 11tr vào ngày 7, 14, 3).  
**Steps:**
1. Trigger detection
**Expected:** KHÔNG có recurring pattern nào được tạo. Confidence < 0.7 → không save.

### TC-CF-03: Recurring Detection — Insufficient History
**Precondition:** User mới đăng ký, chỉ có 1 tháng transaction history.  
**Steps:**
1. Trigger detection
**Expected:** Detection bỏ qua user này. KHÔNG có error. Log: "User X: insufficient history (1 month), skipping."

### TC-CF-04: User Review — Confirm Pattern
**Precondition:** User có unconfirmed pattern "Lương ~20 triệu, ngày 1".  
**Steps:**
1. Nhận Telegram message "Bé Tiền nhận ra 1 khoản thu định kỳ"
2. Nhấn ✅ Đúng
**Expected:** Pattern `is_confirmed = true`. Cashflow forecast ngay lập tức cập nhật để dùng pattern này.

### TC-CF-05: User Review — Dismiss Pattern
**Precondition:** User có unconfirmed pattern "Mua cà phê ~50k, ngày 8" (false positive).  
**Steps:**
1. Nhấn ❌ Không phải
**Expected:** Pattern `dismissed_until = now() + 30 days`. Không hiện lại trong 30 ngày. Không dùng vào forecast.

### TC-CF-06: User Review — Edit Pattern
**Precondition:** User có pattern "Lương ~19.8 triệu" nhưng lương thực tế là 20 triệu.  
**Steps:**
1. Nhấn ✏️ Sửa
2. Nhập lại: "20000000"
3. Confirm
**Expected:** Pattern updated với amount 20,000,000. `is_confirmed = true`.

### TC-CF-07: User Review — Max 5 Patterns Per Message
**Precondition:** User có 8 unconfirmed patterns.  
**Steps:**
1. Trigger review message
**Expected:** Chỉ 5 patterns hiển thị trong 1 message. Không nhận 2 messages cho 8 patterns cùng lúc. (Còn lại hiển thị lần sau hoặc có pagination.)

### TC-CF-08: No Duplicate Review Messages
**Precondition:** User có 1 unconfirmed pattern. User đã nhận review message rồi nhưng chưa respond.  
**Steps:**
1. Trigger detection lại (e.g. next Monday)
**Expected:** KHÔNG nhận duplicate review message cho cùng pattern.

### TC-CF-09: 3-Month Forecast — Basic Calculation
**Precondition:** User có 2 confirmed patterns: Lương +20tr (ngày 1), Tiền nhà −8tr (ngày 5). Current balance = 50 triệu. Today = Aug 15.  
**Steps:**
1. Request cashflow forecast
**Expected:**  
- Tháng 8: income ≈ 0 (đã qua ngày 1 và 5), expense ≈ 0, net ≈ 0, balance EOM ≈ 50tr  
- Tháng 9: income 20tr, expense −8tr, net +12tr, balance EOM ≈ 62tr  
- Tháng 10: income 20tr, expense −8tr, net +12tr, balance EOM ≈ 74tr

### TC-CF-10: Forecast — Only Uses Confirmed Patterns
**Precondition:** User có 1 confirmed pattern (lương 20tr) và 1 unconfirmed pattern (tiền nhà −8tr).  
**Steps:**
1. View cashflow forecast
**Expected:** Forecast chỉ tính lương 20tr. Tiền nhà KHÔNG included. Net = +20tr/tháng.

### TC-CF-11: Low-Balance Alert — Trigger
**Precondition:** User có confirmed patterns: Lương +20tr, Tổng chi −22tr. Current balance = 30 triệu. Alert threshold = 20 triệu.  
**Steps:**
1. Daily cron recompute forecast
**Expected:** Tháng tới: balance EOM ≈ 28tr > 20tr (OK). Tháng 2: ≈ 26tr > 20tr (OK). Tháng 3: ≈ 24tr > 20tr... Nhưng sau 2 tháng: 30 + 2×(−2) = 26tr. Nếu chi > thu, balance giảm dần. Khi forecast tháng nào < 20tr → alert gửi.  
**Adjust precondition nếu cần:** Current balance = 22tr với chi vượt thu 3tr/tháng → Tháng 3: 22 - 9 = 13tr < 20tr → alert.  
**Expected:** Nhận Telegram alert với tone "có thể", "dự báo", gợi ý hành động.

### TC-CF-12: Low-Balance Alert — No Duplicate
**Precondition:** User đã nhận alert cho "Tháng 10" rồi.  
**Steps:**
1. Trigger forecast recompute lần nữa (vẫn thấy Tháng 10 < threshold)
**Expected:** KHÔNG nhận alert lần 2 cho Tháng 10 trong vòng 7 ngày.

### TC-CF-13: Low-Balance Alert — Re-trigger After Recovery
**Precondition:** User đã nhận alert cho "Tháng 10". Sau đó add thu nhập tăng, tháng 10 OK. Nhưng sau 10 ngày forecast lại xấu, tháng 10 < threshold.  
**Steps:**
1. Forecast recompute sau khi balance recover rồi lại xấu
**Expected:** Alert gửi lại cho Tháng 10 (vì đã > 7 ngày từ last alert, hoặc vì recovery reset dedup key).

### TC-CF-14: Cashflow Waterfall Chart
**Precondition:** User có cashflow forecast với 3 tháng data.  
**Steps:**
1. Request cashflow chart (qua Telegram command hoặc Mini App)
**Expected:** Nhận PNG chart với: grouped bars (xanh income, đỏ expense), tím balance line, Vietnamese labels, watermark "dự báo dựa trên thu chi định kỳ". Mobile readable.

### TC-CF-15: Morning Briefing — Cashflow Section Shows
**Precondition:** User có ≥ 2 confirmed recurring patterns. Cashflow forecast exists.  
**Steps:**
1. Trigger morning briefing
**Expected:** Briefing bao gồm dòng: "💰 Cashflow tháng tới: dự kiến +X triệu (thu Y − chi Z)"

### TC-CF-16: Morning Briefing — Cashflow Not Shown With < 2 Patterns
**Precondition:** User có 1 confirmed pattern.  
**Steps:**
1. Trigger morning briefing
**Expected:** Cashflow section KHÔNG hiển thị. Không lỗi. Briefing format bình thường.

### TC-CF-17: Morning Briefing — Warning Shows When Low Balance Risk
**Precondition:** User có ≥ 2 confirmed patterns. Forecast có `low_balance_risk = true`.  
**Steps:**
1. Trigger morning briefing
**Expected:** Briefing có thêm dòng: "⚠️ Tháng X: số dư có thể xuống ~Y triệu — dưới ngưỡng an toàn bạn đặt"

### TC-CF-18: Custom Alert Threshold
**Precondition:** Default threshold = avg expense = 15 triệu.  
**Steps:**
1. Gửi `/settings cashflow_threshold 20000000`
**Expected:** Threshold updated thành 20 triệu. Tiếp theo forecast recompute: dùng threshold 20tr (không phải 15tr default).

### TC-CF-19: Mini App Cashflow Tab — Edit Pattern
**Precondition:** User có confirmed pattern "Tiền nhà −8,000,000".  
**Steps:**
1. Mở Mini App → tab Dòng tiền
2. Tap pattern "Tiền nhà −8,000,000"
3. Sửa thành "−8,500,000"
4. Save
**Expected:** Pattern updated. Forecast tự động recompute. Tab shows new amount.

### TC-CF-20: Mini App Cashflow Tab — Add Manual Pattern
**Precondition:** Detection đã chạy nhưng bỏ sót "Tiền điện −500k/tháng".  
**Steps:**
1. Mở Mini App → tab Dòng tiền → "Thêm thủ công"
2. Nhập: type=expense, amount=500000, day_of_month=20, description="Tiền điện"
3. Save
**Expected:** Pattern saved với `is_confirmed = true` (manual add không cần review flow). Forecast cập nhật.

### TC-CF-21: Mini App Cashflow Tab — Alert Banner
**Precondition:** Forecast có `low_balance_risk = true`.  
**Steps:**
1. Mở Mini App → tab Dòng tiền
**Expected:** Alert banner hiển thị ở đầu tab với màu vàng/đỏ. Có CTA "Xem chi tiết" hoặc link explanation.

---

## Epic 4: Zalo Adapter

### TC-ZL-01: Zalo Linking — Happy Path
**Precondition:** User có Zalo account. User chưa linked Zalo.  
**Steps:**
1. Gửi `/link_zalo` qua Telegram
2. Nhận message với mã "BT-A7K3P2"
3. Mở Zalo → tìm "Bé Tiền" OA → Follow → Gửi "BT-A7K3P2"
**Expected:**  
- Telegram: "✅ Đã liên kết Zalo thành công!"  
- Zalo: "✅ Xin chào! Bé Tiền đã kết nối với tài khoản của bạn."  
- `/profile` shows "Zalo: đã liên kết ✅"

### TC-ZL-02: Zalo Linking — Token Expired
**Precondition:** User gửi `/link_zalo`, nhận mã, đợi > 10 phút rồi mới dùng mã.  
**Steps:**
1. Nhập mã vào Zalo sau 11 phút
**Expected:** Zalo OA nhận message → backend trả lỗi "Mã đã hết hạn. Vui lòng gửi /link_zalo lại trong Telegram."

### TC-ZL-03: Zalo Linking — Token Already Used
**Precondition:** User đã link thành công.  
**Steps:**
1. Copy mã cũ → gửi lại cho Zalo OA
**Expected:** Error message thân thiện: "Mã này đã được dùng rồi."

### TC-ZL-04: Zalo Unlinking
**Precondition:** User đã linked Zalo.  
**Steps:**
1. Gửi `/unlink_zalo` qua Telegram
**Expected:** Telegram confirmation: "Đã hủy liên kết Zalo. Bạn sẽ chỉ nhận thông báo qua Telegram." `/profile` không còn show Zalo linked.

### TC-ZL-05: Cashflow Alert — Linked User Receives on Both Channels
**Precondition:** User đã linked Zalo. Forecast có `low_balance_risk = true`.  
**Steps:**
1. Trigger cashflow alert
**Expected:** Nhận alert trên Telegram (với Markdown formatting) VÀ Zalo (plain text, ≤ 300 chars).

### TC-ZL-06: Cashflow Alert — Unlinked User Only Gets Telegram
**Precondition:** User CHƯA linked Zalo. Forecast có `low_balance_risk = true`.  
**Steps:**
1. Trigger cashflow alert
**Expected:** Nhận alert chỉ trên Telegram. Không có error. Không có Zalo message.

### TC-ZL-07: Zalo Fail-Open
**Precondition:** User đã linked Zalo. Zalo OA API bị lỗi (mock: 500 error).  
**Steps:**
1. Trigger cashflow alert
**Expected:** Telegram alert gửi thành công. Zalo failure được log (WARNING level). KHÔNG raise exception. KHÔNG block Telegram delivery.

### TC-ZL-08: Zalo Message Format — Plain Text No Markdown
**Precondition:** Cashflow alert template chứa Markdown: "**⚠️** số dư *có thể* xuống".  
**Steps:**
1. Trigger alert → Zalo message generated
**Expected:** Zalo message là plain text: "⚠️ số dư có thể xuống" (không có `**` hay `*`).

### TC-ZL-09: Zalo Message Length Limit
**Precondition:** Alert message Telegram version = 450 chars.  
**Steps:**
1. Zalo notifier formats message
**Expected:** Zalo version ≤ 300 chars (truncated với "..." nếu cần).

---

## Regression Tests

### TC-REG-01: Phase 4A Twin Not Broken
**Precondition:** Phase 4A Financial Twin features working.  
**Steps:**
1. Request /twin from Telegram
**Expected:** Twin PNG chart renders, morning briefing twin section still works.

### TC-REG-02: Morning Briefing Not Broken
**Precondition:** All Phase 4A morning briefing features working.  
**Steps:**
1. Trigger morning briefing
**Expected:** All existing sections present (wealth, market, portfolio). New cashflow section conditional (only if ≥ 2 confirmed patterns).

### TC-REG-03: Asset Service Still Works
**Precondition:** Existing asset CRUD working.  
**Steps:**
1. Thêm, sửa, xóa tài sản
**Expected:** All asset operations work. New trigger logic (on-demand recompute) fires appropriately without breaking asset operations.

### TC-REG-04: No Layer Contract Violations
**Steps:**
1. Chạy `layer-contract-checker` agent trên toàn bộ Phase 4B code
**Expected:** Zero violations: không `db.commit()` trong services, không raw SQL trong handlers, không env read trong services, không direct telegram_service import outside adapters.

### TC-REG-05: Vietnamese Strings Not Hardcoded
**Steps:**
1. Chạy `vi-localization-checker` agent
**Expected:** Tất cả user-facing strings trong `content/*.yaml`. Zero hardcoded Vietnamese strings trong code.

---

## Performance Tests

### TC-PERF-01: Life Event MC Injection Benchmark
**Steps:**
1. Run `benchmarks/bench_life_events.py`: 5 events × 1000 paths × 240 months  
**Expected:** p95 < 500ms

### TC-PERF-02: Cashflow Forecast Compute Time
**Steps:**
1. Benchmark `compute_cashflow_forecast()` với 10 confirmed patterns  
**Expected:** p95 < 200ms

### TC-PERF-03: Waterfall Chart Render Time
**Steps:**
1. Benchmark `render_cashflow_waterfall()` với 3-month data  
**Expected:** p95 < 500ms

### TC-PERF-04: Mini App Life Events Tab Load
**Steps:**
1. Load "Kế hoạch" tab với 5 active life events (network throttling: 3G)  
**Expected:** Tab visible (LCP) < 1s

### TC-PERF-05: Life Event Toggle Re-render
**Steps:**
1. Toggle life event ON/OFF trong Mini App, measure time to cone re-render  
**Expected:** Re-render < 500ms

---

## Summary

| Area | TCs |
|---|---|
| Twin Polish (Epic 1) | TC-TP-01 to TC-TP-11 (11 TCs) |
| Life Events (Epic 2) | TC-LE-01 to TC-LE-12 (12 TCs) |
| Cashflow v2 (Epic 3) | TC-CF-01 to TC-CF-21 (21 TCs) |
| Zalo (Epic 4) | TC-ZL-01 to TC-ZL-09 (9 TCs) |
| Regression | TC-REG-01 to TC-REG-05 (5 TCs) |
| Performance | TC-PERF-01 to TC-PERF-05 (5 TCs) |
| **Total** | **63 TCs** |
