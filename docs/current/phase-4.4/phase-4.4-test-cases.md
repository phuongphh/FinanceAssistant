# Phase 4.4 — First-5-Minutes WOW — Manual Test Cases (Telegram)

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

> **Cách dùng tài liệu này**
> Đây là bộ test **chạy tay trên Telegram** (manual QA), không phải pytest.
> Mỗi case có: **ID · Mục tiêu · Tiền điều kiện (precondition) · Các bước · Kết quả mong đợi**.
> Tester chạy thật trên bot, đối chiếu kết quả mong đợi, đánh dấu **PASS / FAIL** + ghi chú.
>
> **Ký hiệu**
> - 🟢 ON / 🔴 OFF = trạng thái feature flag cần set trước khi test.
> - "Bé Tiền" = bot. "User" = người test.
> - Salutation = cách xưng hô user chọn (anh / chị / bạn).
>
> **Feature flags liên quan (set ở env, restart service nếu cần):**
> - `READING_ENABLED` (default `true`) — bật/tắt The Reading (WOW #1).
> - `SCREENSHOT_ONBOARDING_ENABLED` (default `false`) — bật/tắt đọc ảnh số dư (WOW #2).
> - `PROACTIVE_COMPANION_ENABLED` (default `true`) — bật/tắt nhắn chủ động sau onboarding (WOW #3).
>
> **Reset giữa các test:** dùng tài khoản test sạch hoặc reset onboarding state (xoá user test / dùng invite code mới) để các bước choreography chạy lại từ đầu.

---

## Choreography tham chiếu (rút gọn từ phase-4.4-detailed.md)

| Phút | Sự kiện | WOW |
|---|---|---|
| 0 | Welcome + chọn mục tiêu | — |
| 0.5 | Hỏi tên + xưng hô (anh/chị/bạn) | WOW #0 |
| 1 | The Reading v0 (đoán mò qua mục tiêu) | WOW #1 |
| 2 | Hỏi tài sản đầu tiên + (tuỳ chọn) chụp màn hình | WOW #2 |
| 3 | The Reading v1 (đoán trên con số thật) | — |
| 4 | Twin teaser | — |
| 5 | Twin shown + founding | — |
| sau | Nhắn chủ động (empathy) khi user im lặng | WOW #3 |

---

## Batch 1 — Epic 0 (Salutation) & Epic 1 (The Reading)

### TC-001 — Bước xưng hô xuất hiện đúng thứ tự
- **Mục tiêu:** Bước hỏi xưng hô hiện ngay sau khi user nhập tên, trước câu hỏi mục tiêu.
- **Precondition:** User test mới, chưa onboarding. Flags mặc định.
- **Các bước:**
  1. Start bot, bấm CTA "🌱 Bắt đầu hành trình".
  2. Khi Bé Tiền hỏi tên, gõ tên (vd: "Phương").
- **Kết quả mong đợi:** Sau khi nhập tên, Bé Tiền hỏi xưng hô với header "Bé Tiền xưng hô sao cho thân nhỉ?" và 3 nút: "Gọi mình là anh", "Gọi mình là chị", "Cứ gọi mình là bạn". Câu hỏi mục tiêu CHƯA xuất hiện.

### TC-002 — Chọn "anh" → ack đúng + xưng hô lưu lại
- **Mục tiêu:** Chọn "anh" lưu salutation và Bé Tiền tự xưng "em".
- **Precondition:** Đang ở bước xưng hô (sau TC-001).
- **Các bước:**
  1. Bấm "Gọi mình là anh".
- **Kết quả mong đợi:** Ack "Dạ vâng, em nhớ rồi ạ! 💚". Các tin nhắn tiếp theo gọi user là "anh" (Bé Tiền xưng "em"). Flow chuyển sang câu hỏi mục tiêu.

### TC-003 — Chọn "chị" → ack đúng
- **Mục tiêu:** Chọn "chị" lưu salutation đúng.
- **Precondition:** User test mới, đến bước xưng hô.
- **Các bước:**
  1. Bấm "Gọi mình là chị".
- **Kết quả mong đợi:** Ack "Dạ vâng, em nhớ rồi ạ! 💚". Tin nhắn sau gọi user là "chị". Flow sang câu hỏi mục tiêu.

### TC-004 — Chọn "bạn" → ack thân thiện, KHÔNG framing như fallback
- **Mục tiêu:** "bạn" là lựa chọn ngang hàng, ack riêng.
- **Precondition:** User test mới, đến bước xưng hô.
- **Các bước:**
  1. Bấm "Cứ gọi mình là bạn".
- **Kết quả mong đợi:** Ack "Okie, mình xưng bạn cho thoải mái nhé! 💚" (KHÁC với ack anh/chị, Bé Tiền xưng "mình"). Không có chữ nào ám chỉ đây là lựa chọn mặc định / kém hơn.

### TC-005 — Xưng hô được giữ xuyên suốt phiên
- **Mục tiêu:** Salutation đã chọn áp dụng nhất quán ở mọi tin nhắn sau (Reading, Twin teaser…).
- **Precondition:** Chọn "anh" ở TC-002.
- **Các bước:**
  1. Tiếp tục onboarding tới hết (mục tiêu → Reading → tài sản → Twin teaser).
- **Kết quả mong đợi:** Không tin nhắn nào gọi nhầm "chị"/"bạn". Reading v0, v1, Twin teaser đều gọi "anh".

### TC-006 — Reading v0 placeholder hiện ngay sau khi chọn mục tiêu
- **Mục tiêu:** WOW #1 mở màn — placeholder "đang đoán…" xuất hiện tức thì.
- **Precondition:** `READING_ENABLED` 🟢 ON (default). Đã chọn xưng hô.
- **Các bước:**
  1. Bấm 1 nút mục tiêu (vd "🌱 Hiểu rõ tổng tài sản của tôi").
- **Kết quả mong đợi:** Sau goal-ack, hiện placeholder kiểu "🔮 Khoan đã… để em đoán thử một chút về anh nhé…", sau đó được edit/thay bằng nội dung Reading thật (lời đoán) trong vài giây.

### TC-007 — Reading v0 nội dung ấm áp, đúng persona
- **Mục tiêu:** Lời đoán v0 thân thiện, không phán xét, đúng xưng hô.
- **Precondition:** TC-006, LLM hoạt động bình thường.
- **Các bước:**
  1. Đọc kỹ nội dung Reading v0.
- **Kết quả mong đợi:** Có câu mở "🔮 Để em đoán thử nha — anh đừng cười nếu em trật chút xíu nha 😄", phần đoán giữa do LLM viết, kết bằng disclaimer_v0 mời nhập số thật. Giọng ấm, KHÔNG phán xét, KHÔNG có chữ "CFO"/"Personal CFO".

### TC-008 — Reading v0 bám theo mục tiêu đã chọn
- **Mục tiêu:** Lời đoán phản ánh mục tiêu user chọn.
- **Precondition:** Chạy 3 lần với 3 user test, mỗi lần chọn 1 mục tiêu khác nhau.
- **Các bước:**
  1. understand_wealth → đọc Reading.
  2. plan_goal → đọc Reading.
  3. track_spending → đọc Reading.
- **Kết quả mong đợi:** Mỗi Reading v0 có sắc thái khớp mục tiêu (hiểu tài sản / kế hoạch mục tiêu lớn / theo dõi chi tiêu). Không bị generic giống hệt nhau.

### TC-009 — Reading v0 disclaimer mời nhập số thật
- **Mục tiêu:** Cầu nối từ v0 sang bước hỏi tài sản.
- **Precondition:** TC-007.
- **Các bước:**
  1. Đọc câu cuối Reading v0.
- **Kết quả mong đợi:** Kết bằng "…em đoán mò qua mục tiêu thôi đó. Anh cho em xem con số thật, em vẽ được bức tranh chuẩn hơn nhiều 💚". Ngay sau đó hiện bước (2/3) hỏi tài sản.

### TC-010 — Reading v1 chạy trên con số thật
- **Mục tiêu:** Sau khi nhập tài sản thật, Reading v1 đoán lại có cơ sở.
- **Precondition:** `READING_ENABLED` 🟢. Đã qua v0, đang ở bước hỏi tài sản.
- **Các bước:**
  1. Gõ tài sản thật (vd "500tr").
- **Kết quả mong đợi:** Hiện Reading v1 (đoán dựa trên con số), kết bằng disclaimer_v1 "Giờ em đoán có cơ sở hơn rồi đó. Để em vẽ Twin tài chính cho anh xem nhé…" — bắc cầu sang Twin teaser.

### TC-011 — Reading v1 phản ánh độ lớn con số
- **Mục tiêu:** Lời đoán v1 cảm nhận được quy mô tài sản.
- **Precondition:** Chạy 2 user test: 1 nhập "50tr", 1 nhập "3 tỷ".
- **Các bước:**
  1. So sánh nội dung Reading v1 của 2 trường hợp.
- **Kết quả mong đợi:** Nội dung khác nhau hợp lý theo quy mô, vẫn ấm áp & KHÔNG phán xét người ít tiền, KHÔNG nịnh quá đà người nhiều tiền.

### TC-012 — Reading v0 fallback khi LLM không khả dụng
- **Mục tiêu:** Khi LLM chậm/lỗi, phút-1 vẫn không gãy.
- **Precondition:** `READING_ENABLED` 🟢 nhưng LLM provider (Groq) bị tắt/timeout (mô phỏng lỗi, vd sai API key trên env test).
- **Các bước:**
  1. Chọn mục tiêu, chờ Reading.
- **Kết quả mong đợi:** Thay vì lời đoán, hiện fallback_v0 "🔮 Em đang hình dung về hành trình tài chính của anh… nhưng để chắc, anh cho em xem con số thật nhé 💚". Flow vẫn sang bước hỏi tài sản, KHÔNG crash, KHÔNG hiện lỗi kỹ thuật.

### TC-013 — Reading v1 fallback khi LLM không khả dụng
- **Mục tiêu:** v1 cũng có fallback an toàn.
- **Precondition:** Như TC-012, đang ở bước nhập tài sản.
- **Các bước:**
  1. Gõ con số thật.
- **Kết quả mong đợi:** Hiện fallback_v1 "Cảm ơn anh đã tin tưởng chia sẻ. Để em vẽ Twin tài chính cho anh xem nhé…". Vẫn bắc cầu sang Twin teaser bình thường.

### TC-014 — READING_ENABLED 🔴 OFF — bỏ qua The Reading
- **Mục tiêu:** Tắt flag thì không có bước Reading nào, flow vẫn liền mạch.
- **Precondition:** `READING_ENABLED` 🔴 OFF. User test mới.
- **Các bước:**
  1. Onboarding: chọn mục tiêu → quan sát.
  2. Nhập tài sản → quan sát.
- **Kết quả mong đợi:** KHÔNG có placeholder, KHÔNG có Reading v0/v1. Sau goal-ack đi thẳng tới bước hỏi tài sản; sau khi nhập số đi thẳng tới Twin teaser. Không lỗi.

### TC-015 — Persona check: tuyệt đối không có "CFO"
- **Mục tiêu:** Không lộ chữ "CFO"/"Personal CFO" ở bất kỳ tin nhắn user-facing nào.
- **Precondition:** Chạy full onboarding với Reading ON.
- **Các bước:**
  1. Đọc toàn bộ tin nhắn từ welcome → Twin teaser.
- **Kết quả mong đợi:** Không xuất hiện "CFO"/"Personal CFO" ở bất kỳ đâu. Vị trí định vị dùng "người đồng hành quản lý tài sản".

### TC-016 — Persona check: zero phán xét
- **Mục tiêu:** Bé Tiền không bao giờ chê người dùng (ít tiền, chi tiêu nhiều…).
- **Precondition:** User test nhập tài sản nhỏ (vd "2tr").
- **Các bước:**
  1. Hoàn tất tới Reading v1.
- **Kết quả mong đợi:** Reading v1 không có giọng chê bai/khuyên dạy gắt. Toàn bộ supportive, đồng hành.

### TC-017 — Xưng hô đúng trong Reading cho cả 3 lựa chọn
- **Mục tiêu:** anh/chị/bạn đều được điền đúng vào Reading.
- **Precondition:** Chạy 3 user test, mỗi user chọn 1 xưng hô.
- **Các bước:**
  1. Mỗi user đi tới Reading v0.
- **Kết quả mong đợi:** User chọn "anh" → Reading gọi "anh"; "chị" → "chị"; "bạn" → "bạn" (và Bé Tiền xưng "mình" thay vì "em" khi user là "bạn", nếu copy yêu cầu). Không lẫn lộn.

### TC-018 — Capitalization đầu câu của salutation
- **Mục tiêu:** `{Salutation}` viết hoa đầu câu, `{salutation}` thường giữa câu.
- **Precondition:** Reading ON, chọn bất kỳ xưng hô.
- **Các bước:**
  1. Đọc disclaimer_v0 (bắt đầu bằng salutation viết hoa) và câu mở (salutation thường).
- **Kết quả mong đợi:** disclaimer_v0 "…Anh cho em xem con số thật…" (viết hoa đầu mệnh đề), câu giữa "về anh nhé" (thường). Không có chỗ viết hoa/thường sai.

### TC-019 — Reading không vượt giới hạn độ dài
- **Mục tiêu:** Reading gọn (≤ ~600 ký tự), không tràn dài lê thê.
- **Precondition:** Reading ON.
- **Các bước:**
  1. Đọc Reading v0 và v1, ước lượng độ dài.
- **Kết quả mong đợi:** Mỗi Reading ngắn gọn, đọc lướt trong vài giây, không bị cắt cụt giữa chừng, không quá dài gây ngợp.

### TC-020 — Quay lại giữa chừng (resume) giữ nguyên xưng hô & tiến độ
- **Mục tiêu:** Rời app rồi quay lại không mất salutation, không lặp lại bước xưng hô.
- **Precondition:** Chọn xưng hô "anh", dừng ở bước hỏi tài sản, đóng Telegram vài phút.
- **Các bước:**
  1. Mở lại bot, gửi tin nhắn bất kỳ / bấm tiếp tục.
- **Kết quả mong đợi:** Bé Tiền resume đúng bước đang dở (hỏi tài sản), vẫn gọi "anh", KHÔNG hỏi lại tên/xưng hô từ đầu.

---

## Batch 2 — Epic 2 (Screenshot Onboarding) & nhập tài sản đầu tiên

### TC-021 — Nhập tài sản dạng "200tr"
- **Mục tiêu:** Parse được định dạng rút gọn "tr".
- **Precondition:** Đang ở bước (2/3) hỏi tài sản.
- **Các bước:**
  1. Gõ "200tr".
- **Kết quả mong đợi:** Bé Tiền nhận = 200,000,000đ, chuyển sang Reading v1 / Twin teaser. Không báo lỗi.

### TC-022 — Nhập tài sản dạng "1.5 tỷ"
- **Mục tiêu:** Parse được "tỷ" có phần thập phân.
- **Precondition:** Bước hỏi tài sản.
- **Các bước:**
  1. Gõ "1.5 tỷ".
- **Kết quả mong đợi:** Nhận = 1,500,000,000đ. Flow tiếp tục.

### TC-023 — Nhập tài sản dạng số nguyên đầy đủ
- **Mục tiêu:** Parse được số nguyên thô.
- **Precondition:** Bước hỏi tài sản.
- **Các bước:**
  1. Gõ "500000000".
- **Kết quả mong đợi:** Nhận = 500,000,000đ. Flow tiếp tục.

### TC-024 — Nhập số không hợp lệ
- **Mục tiêu:** Báo lỗi nhẹ nhàng, hướng dẫn định dạng.
- **Precondition:** Bước hỏi tài sản.
- **Các bước:**
  1. Gõ "rất nhiều tiền" / "abc".
- **Kết quả mong đợi:** Hiện copy `invalid`: "Bé Tiền chưa hiểu con số đó. Bạn thử lại với định dạng như 200tr, 1.5 tỷ, hoặc nhập số nguyên (200000000) nhé." Vẫn ở bước hỏi tài sản, không crash.

### TC-025 — Nhập số quá nhỏ
- **Mục tiêu:** Chặn số dưới ngưỡng tối thiểu (1 triệu).
- **Precondition:** Bước hỏi tài sản.
- **Các bước:**
  1. Gõ "100" hoặc "50000".
- **Kết quả mong đợi:** Hiện copy `too_small` mời nhập tối thiểu từ 1 triệu hoặc bấm demo. Không tiến bước.

### TC-026 — Nhập số quá lớn (vô lý)
- **Mục tiêu:** Chặn con số phi thực tế.
- **Precondition:** Bước hỏi tài sản.
- **Các bước:**
  1. Gõ con số cực lớn (vd "999999 tỷ").
- **Kết quả mong đợi:** Hiện copy `too_large` "Số tiền có vẻ chưa hợp lý. Bạn kiểm tra lại giúp Bé Tiền nhé." Không tiến bước.

### TC-027 — Demo mode từ nút "Để Bé Tiền dùng demo trước"
- **Mục tiêu:** Demo hiển thị Twin giả định với framing rõ ràng.
- **Precondition:** Bước hỏi tài sản.
- **Các bước:**
  1. Bấm "🎭 Để Bé Tiền dùng demo trước".
- **Kết quả mong đợi:** Hiện demo_banner nêu rõ "Demo Mode" với danh mục 50 triệu (30tr tiết kiệm + 20tr cổ phiếu), nhắc "Twin của bạn sẽ khác". Có nút "💎 Xem Twin của tôi" để thoát demo. User KHÔNG nhầm 50tr là số của mình.

### TC-028 — Thoát demo về nhập số thật
- **Mục tiêu:** Nút "Xem Twin của tôi" đưa user trở lại nhập tài sản thật.
- **Precondition:** Đang ở demo (TC-027).
- **Các bước:**
  1. Bấm "💎 Xem Twin của tôi".
- **Kết quả mong đợi:** Quay lại bước nhập tài sản thật. Sau khi nhập số thật, Twin tính trên số thật chứ không phải 50tr demo.

### TC-029 — SCREENSHOT_ONBOARDING_ENABLED 🔴 OFF (mặc định) — ảnh KHÔNG được parse
- **Mục tiêu:** Mặc định tắt: gửi ảnh ở bước tài sản KHÔNG kích hoạt đọc số dư.
- **Precondition:** `SCREENSHOT_ONBOARDING_ENABLED` 🔴 OFF (default). Đang ở bước hỏi tài sản.
- **Các bước:**
  1. Gửi 1 ảnh chụp màn hình số dư.
- **Kết quả mong đợi:** Bé Tiền KHÔNG đọc số từ ảnh trong luồng onboarding (không hiện "đang đọc ảnh"). Hint chụp màn hình KHÔNG xuất hiện trong body bước tài sản. (Ảnh có thể được xử lý theo luồng mặc định khác hoặc bỏ qua, nhưng KHÔNG điền tài sản onboarding từ ảnh.)

### TC-030 — SCREENSHOT_ONBOARDING_ENABLED 🟢 ON — hint xuất hiện
- **Mục tiêu:** Bật flag thì gợi ý chụp màn hình hiện trong bước tài sản.
- **Precondition:** `SCREENSHOT_ONBOARDING_ENABLED` 🟢 ON. Bước hỏi tài sản.
- **Các bước:**
  1. Đọc nội dung tin bước (2/3) hỏi tài sản.
- **Kết quả mong đợi:** Có thêm dòng hint "💡 Ngại gõ số? Bạn chụp luôn màn hình số dư app ngân hàng / ví đầu tư gửi Bé Tiền cũng được nhé."

### TC-031 — Đọc số dư từ ảnh hợp lệ (happy path)
- **Mục tiêu:** Ảnh số dư rõ ràng được đọc đúng số.
- **Precondition:** Flag 🟢 ON. Có ảnh chụp app ngân hàng có dòng "Tổng số dư" rõ ràng (vd 200.000.000đ).
- **Các bước:**
  1. Gửi ảnh ở bước hỏi tài sản.
- **Kết quả mong đợi:** Hiện ack "Bé Tiền đang đọc ảnh giúp bạn… chờ chút xíu nha 👀", sau đó đọc đúng ~200tr và tiếp tục flow (Reading v1 / Twin teaser).

### TC-032 — Ảnh không phải số dư
- **Mục tiêu:** Ảnh không chứa số tài sản → nudge lịch sự.
- **Precondition:** Flag 🟢 ON. Ảnh bất kỳ (vd ảnh mèo / ảnh chữ).
- **Các bước:**
  1. Gửi ảnh ở bước hỏi tài sản.
- **Kết quả mong đợi:** Hiện copy `screenshot_not_balance` mời chụp màn hình có "Tổng số dư"/"Số dư khả dụng" hoặc gõ thẳng số. Vẫn ở bước hỏi tài sản.

### TC-033 — Ảnh mở/đọc thất bại
- **Mục tiêu:** Lỗi tải/giải mã ảnh → fallback gõ số.
- **Precondition:** Flag 🟢 ON. Ảnh hỏng / quá lớn / định dạng lạ.
- **Các bước:**
  1. Gửi ảnh lỗi ở bước hỏi tài sản.
- **Kết quả mong đợi:** Hiện copy `screenshot_failed` mời chụp lại rõ hơn hoặc gõ thẳng con số. Không crash.

### TC-034 — Cảnh báo chất lượng dữ liệu (data-quality warning)
- **Mục tiêu:** Khi số đọc được nhưng đáng ngờ, Bé Tiền hỏi xác nhận.
- **Precondition:** Flag 🟢 ON. Ảnh đọc ra số nhưng kích hoạt cảnh báo chất lượng (vd nhiều số gây nhập nhằng).
- **Các bước:**
  1. Gửi ảnh kiểu đó.
- **Kết quả mong đợi:** Hiện copy `screenshot_quality_warning` với ⚠️ "Kiểm tra lại số tiền", nội dung cảnh báo {warning}, "Bé Tiền đọc được <số> từ ảnh. Bạn chọn số đúng nhé:" kèm nút chọn. User xác nhận trước khi lưu.

### TC-035 — Xác nhận số sau cảnh báo chất lượng
- **Mục tiêu:** Sau khi user chọn số đúng, flow tiếp tục bình thường.
- **Precondition:** Đang ở màn cảnh báo chất lượng (TC-034).
- **Các bước:**
  1. Bấm nút số đúng.
- **Kết quả mong đợi:** Lưu số đã chọn, chuyển sang Reading v1 / Twin teaser.

### TC-036 — Ảnh số dư khi flag ON nhưng KHÔNG ở bước tài sản
- **Mục tiêu:** Đọc-số-dư-onboarding chỉ kích hoạt đúng bước (STEP_FIRST_ASSET).
- **Precondition:** Flag 🟢 ON. User đã onboarding xong (không ở bước tài sản).
- **Các bước:**
  1. Gửi ảnh số dư.
- **Kết quả mong đợi:** KHÔNG chạy luồng onboarding-screenshot; ảnh đi theo luồng xử lý ảnh mặc định (vd receipt). Không nhảy ngược về onboarding.

### TC-037 — Thứ tự worker: ảnh ở bước tài sản KHÔNG bị nuốt bởi luồng receipt
- **Mục tiêu:** Khi user đang trong bước tài sản, ảnh ưu tiên cho onboarding-screenshot (không bị photo_receipt xử lý trước).
- **Precondition:** Flag 🟢 ON. Đang ở bước hỏi tài sản.
- **Các bước:**
  1. Gửi ảnh số dư.
- **Kết quả mong đợi:** Ảnh được xử lý như đọc số dư onboarding (ack "đang đọc ảnh"), KHÔNG bị nhận nhầm là hoá đơn/receipt.

### TC-038 — Gõ số đè lên gợi ý chụp màn hình
- **Mục tiêu:** Khi hint chụp ảnh đang hiện, user vẫn gõ số bình thường được.
- **Precondition:** Flag 🟢 ON. Bước hỏi tài sản (có hint).
- **Các bước:**
  1. Bỏ qua hint, gõ "300tr".
- **Kết quả mong đợi:** Nhận 300tr như TC-021, không bắt buộc phải chụp ảnh.

### TC-039 — Định dạng tiền hiển thị rút gọn đúng
- **Mục tiêu:** Số đọc/nhập hiển thị qua format chuẩn (45k/1.5tr/1.2 tỷ).
- **Precondition:** Nhập/đọc các mốc: 1.500.000; 200.000.000; 1.500.000.000.
- **Các bước:**
  1. Quan sát cách Bé Tiền hiển thị lại số.
- **Kết quả mong đợi:** Hiển thị rút gọn hợp lý (vd "1.5tr", "200tr", "1.5 tỷ"), nhất quán, không sai đơn vị.

### TC-040 — Bật/tắt flag screenshot không ảnh hưởng luồng gõ số
- **Mục tiêu:** Dù flag ON hay OFF, gõ số tay luôn hoạt động.
- **Precondition:** Chạy 2 lần: flag OFF rồi flag ON.
- **Các bước:**
  1. Mỗi lần: gõ "250tr" ở bước tài sản.
- **Kết quả mong đợi:** Cả hai lần đều nhận 250tr và tiếp tục flow. Flag screenshot chỉ ảnh hưởng đường đi của ảnh, không ảnh hưởng gõ số.

---

## Batch 3 — Epic 3 (Proactive Companion), Twin teaser & choreography end-to-end

### TC-041 — Twin teaser xuất hiện sau Reading v1
- **Mục tiêu:** Phút-4 Twin teaser nối tiếp Reading v1.
- **Precondition:** Đã nhập tài sản thật, Reading ON.
- **Các bước:**
  1. Hoàn tất nhập tài sản → đọc Reading v1.
- **Kết quả mong đợi:** Sau disclaimer_v1, Bé Tiền hiện Twin teaser rồi tới bước (3/3) "Twin của bạn".

### TC-042 — Twin shown + founding (kết thúc onboarding)
- **Mục tiêu:** Phút-5 đánh dấu Twin đã hiện, hoàn tất onboarding.
- **Precondition:** Đã qua Twin teaser.
- **Các bước:**
  1. Tiếp tục tới khi Twin hiển thị đầy đủ.
- **Kết quả mong đợi:** Twin của user (trên số thật) hiển thị, onboarding kết thúc, state đánh dấu twin_shown. Không lặp lại các bước trước.

### TC-043 — PROACTIVE_COMPANION_ENABLED 🟢 ON — nhắn chủ động khi im lặng
- **Mục tiêu:** WOW #3 — Bé Tiền nhắn empathy sau khi user onboarding xong rồi im lặng.
- **Precondition:** `PROACTIVE_COMPANION_ENABLED` 🟢 ON (default). User vừa xong onboarding, không tương tác thêm cho tới khi job chạy (qua ngưỡng im lặng).
- **Các bước:**
  1. Hoàn tất onboarding, không nhắn gì thêm.
  2. Chờ hourly job kích hoạt trigger (hoặc chạy job thủ công ở env test).
- **Kết quả mong đợi:** Bé Tiền chủ động gửi 1 tin empathy ấm áp, gọi đúng xưng hô, không phán xét, không spam (chỉ 1 lần).

### TC-044 — PROACTIVE_COMPANION_ENABLED 🔴 OFF — không nhắn chủ động
- **Mục tiêu:** Tắt flag thì không có tin nhắn chủ động.
- **Precondition:** `PROACTIVE_COMPANION_ENABLED` 🔴 OFF. User onboarding xong, im lặng.
- **Các bước:**
  1. Chờ/chạy job như TC-043.
- **Kết quả mong đợi:** KHÔNG có tin empathy chủ động nào được gửi.

### TC-045 — Empathy chủ động dùng đúng xưng hô
- **Mục tiêu:** Tin chủ động tôn trọng salutation đã chọn.
- **Precondition:** Flag 🟢. Chạy 2 user: 1 chọn "anh", 1 chọn "chị".
- **Các bước:**
  1. Kích hoạt trigger cho cả hai.
- **Kết quả mong đợi:** User "anh" nhận tin gọi "anh"; user "chị" nhận tin gọi "chị". Không lẫn.

### TC-046 — Không nhắn chủ động nếu user vẫn đang tương tác
- **Mục tiêu:** Trigger chỉ bắn khi thực sự im lặng (không làm phiền user đang chat).
- **Precondition:** Flag 🟢. User onboarding xong và tiếp tục chat bình thường.
- **Các bước:**
  1. User nhắn vài tin trong khoảng thời gian quan sát.
  2. Chạy job.
- **Kết quả mong đợi:** Không gửi tin empathy chủ động (chưa đủ điều kiện im lặng).

### TC-047 — Empathy chủ động không lặp lại nhiều lần
- **Mục tiêu:** Không spam — trigger không bắn lại liên tục mỗi giờ.
- **Precondition:** Flag 🟢. User im lặng kéo dài qua nhiều lần job chạy.
- **Các bước:**
  1. Để job chạy nhiều chu kỳ.
- **Kết quả mong đợi:** Tin empathy onboarding-silence chỉ gửi 1 lần (không lặp mỗi giờ).

### TC-048 — Empathy chủ động không có "CFO", đúng persona
- **Mục tiêu:** Tin chủ động giữ persona Bé Tiền.
- **Precondition:** Flag 🟢, đã nhận tin TC-043.
- **Các bước:**
  1. Đọc nội dung tin chủ động.
- **Kết quả mong đợi:** Ấm áp, đồng hành, KHÔNG "CFO", KHÔNG phán xét chuyện chưa nhập thêm dữ liệu.

### TC-049 — Choreography đầy đủ end-to-end (happy path)
- **Mục tiêu:** Toàn bộ 5 phút diễn ra đúng thứ tự với tất cả flag mặc định.
- **Precondition:** Flags default (Reading ON, Screenshot OFF, Proactive ON). User mới.
- **Các bước:**
  1. Welcome → chọn mục tiêu → nhập tên → chọn xưng hô → Reading v0 → nhập tài sản → Reading v1 → Twin teaser → Twin shown.
- **Kết quả mong đợi:** Thứ tự đúng bảng choreography, không bước nào bị nhảy/lặp, xưng hô nhất quán, không lỗi kỹ thuật, không "CFO".

### TC-050 — Tất cả flag OFF — flow tối giản vẫn hoàn tất
- **Mục tiêu:** Tắt cả 3 flag, onboarding vẫn đi tới Twin.
- **Precondition:** Reading 🔴, Screenshot 🔴, Proactive 🔴. User mới.
- **Các bước:**
  1. Chạy onboarding tới hết.
- **Kết quả mong đợi:** Không Reading, không hint chụp ảnh, không nhắn chủ động. Vẫn: welcome → mục tiêu → tên → xưng hô → nhập tài sản → Twin. Hoàn tất bình thường.

### TC-051 — Tất cả flag ON (gồm screenshot) — full WOW
- **Mục tiêu:** Bật hết, mọi WOW đều xuất hiện.
- **Precondition:** Reading 🟢, Screenshot 🟢, Proactive 🟢. User mới.
- **Các bước:**
  1. Onboarding dùng ảnh số dư để nhập tài sản, rồi im lặng.
- **Kết quả mong đợi:** WOW #0 (xưng hô), #1 (Reading v0+v1), #2 (đọc ảnh), Twin, #3 (nhắn chủ động) đều hoạt động đúng.

### TC-052 — Welcome theo source variant (invite code có source)
- **Mục tiêu:** Invite code mang source hiện prefix tương ứng.
- **Precondition:** Dùng invite code có source (vd `vn_finance_community`).
- **Các bước:**
  1. Start bot qua invite code đó.
- **Kết quả mong đợi:** Trên intro default xuất hiện prefix đúng source. Vẫn không có "CFO" (variant dùng "người đồng hành quản lý tài sản").

### TC-053 — Welcome mặc định (không source)
- **Mục tiêu:** Không có source thì chỉ intro default.
- **Precondition:** Start bot không qua source-aware invite.
- **Các bước:**
  1. Start bot.
- **Kết quả mong đợi:** Chỉ intro default "👋 Chào bạn, Bé Tiền đây!…" với CTA "🌱 Bắt đầu hành trình". Không prefix lạ.

### TC-054 — Nhập tên không hợp lệ
- **Mục tiêu:** Tên rỗng/ký tự lạ được xử lý nhẹ nhàng.
- **Precondition:** Đang ở bước hỏi tên.
- **Các bước:**
  1. Gửi tin không phải tên hợp lệ (vd emoji-only / quá dài).
- **Kết quả mong đợi:** Bé Tiền mời nhập lại tên lịch sự, không crash, chưa sang bước xưng hô.

### TC-055 — Đổi mục tiêu trước khi xác nhận (nếu UI cho phép bấm lại)
- **Mục tiêu:** Bấm nhiều nút mục tiêu không gây trạng thái rối.
- **Precondition:** Bước chọn mục tiêu.
- **Các bước:**
  1. Bấm 1 mục tiêu, rồi (nếu nút còn hiện) bấm mục tiêu khác.
- **Kết quả mong đợi:** Hệ thống xử lý nhất quán (chốt mục tiêu cuối hoặc khoá sau lần chọn đầu), không tạo 2 Reading chồng nhau gây rối.

### TC-056 — Gửi tin text giữa lúc Reading đang chạy
- **Mục tiêu:** User gõ trong lúc chờ Reading không làm gãy flow.
- **Precondition:** Reading ON, vừa chọn mục tiêu, placeholder đang hiện.
- **Các bước:**
  1. Gõ 1 tin bất kỳ trong lúc chờ.
- **Kết quả mong đợi:** Reading vẫn hoàn tất / hoặc tin được xử lý hợp lý; không kẹt, không double-send, không lỗi.

### TC-057 — LLM trả về nội dung lỗi định dạng (parse fail) → fallback
- **Mục tiêu:** Nếu phản hồi LLM không parse được, dùng fallback thay vì hiện rác.
- **Precondition:** Reading ON; mô phỏng LLM trả format sai (nếu môi trường test cho phép).
- **Các bước:**
  1. Kích hoạt Reading.
- **Kết quả mong đợi:** Hiện fallback_v0/v1 thay vì text lỗi/JSON thô. Không lộ chi tiết kỹ thuật.

### TC-058 — Money dùng Decimal, không sai số float
- **Mục tiêu:** Số tài sản lẻ không bị lỗi làm tròn float.
- **Precondition:** Nhập số có phần lẻ (vd "1.234.567").
- **Các bước:**
  1. Nhập và quan sát số Bé Tiền ghi nhận/hiển thị lại.
- **Kết quả mong đợi:** Giá trị chính xác, không xuất hiện đuôi thập phân lạ (vd 0.30000000004). Hiển thị rút gọn đúng.

### TC-059 — Localization: không lộ chuỗi tiếng Việt hardcode / placeholder thô
- **Mục tiêu:** Mọi copy đến từ YAML, không lộ `{salutation}`, `{amount}`, `{warning}` chưa điền.
- **Precondition:** Chạy full onboarding (Reading + screenshot quality warning).
- **Các bước:**
  1. Quan sát kỹ mọi tin nhắn.
- **Kết quả mong đợi:** Không tin nào còn dấu ngoặc nhọn placeholder chưa thay; không chuỗi tiếng Anh dev lọt ra.

### TC-060 — Regression: onboarding cũ (không Phase 4.4) vẫn không vỡ
- **Mục tiêu:** Với flag Reading/Proactive OFF + screenshot OFF, trải nghiệm tương đương trước 4.4.
- **Precondition:** Reading 🔴, Proactive 🔴, Screenshot 🔴.
- **Các bước:**
  1. Onboarding đầy đủ.
- **Kết quả mong đợi:** Vẫn có bước xưng hô (Epic 0 luôn bật, không có flag) nhưng KHÔNG Reading/chủ động/ảnh. Flow tới Twin bình thường, không lỗi — đảm bảo Phase 4.4 additive, an toàn rollback.

---

## Tổng kết coverage

| Epic / Vùng | Test cases |
|---|---|
| Epic 0 — Salutation | TC-001…TC-005, TC-017, TC-018, TC-045, TC-060 |
| Epic 1 — The Reading | TC-006…TC-019, TC-056, TC-057 |
| Epic 2 — Screenshot Onboarding | TC-021…TC-040 (đặc biệt 029/030 flag, 037 worker order) |
| Epic 3 — Proactive Companion | TC-043…TC-048 |
| Twin teaser / shown | TC-041, TC-042 |
| Choreography end-to-end | TC-049, TC-050, TC-051 |
| Feature flags on/off | TC-014, TC-029/030, TC-040, TC-043/044, TC-050, TC-051 |
| Persona / no-CFO / no-judgment | TC-007, TC-015, TC-016, TC-048 |
| Welcome / source variants | TC-052, TC-053 |
| Validation / edge / regression | TC-024…TC-026, TC-054…TC-059, TC-060 |

**Definition of Done (manual QA):** Tất cả TC trên PASS với flag mặc định (Reading ON, Screenshot OFF, Proactive ON) + xác minh riêng các tổ hợp flag ở Batch 3.

