# Finance Assistant — Product Enhancement Strategy

> **Mục tiêu cuối cùng:** Xây dựng một finance assistant độc đáo tại thị trường Việt Nam, vượt qua các đối thủ hiện tại (Money Lover, MISA, Spendee) bằng 3 lợi thế cốt lõi: **trải nghiệm có cảm xúc**, **capture dữ liệu không cần nhập tay**, và **hiểu sâu hành vi tài chính của user**.

> **Nguyên tắc triển khai:** Mỗi Phase phải **độc lập có giá trị** — user thấy được cải thiện ngay sau khi hoàn thành, không cần đợi Phase sau. Ưu tiên **UX cảm xúc trước**, **tự động hóa sau**, vì cảm xúc tạo retention, tự động hóa tạo scale.

---

## 📋 Tổng Quan Các Phase

| Phase | Tên | Thời gian ước tính | Mục tiêu chính |
|-------|-----|-------------------|----------------|
| **Phase 1** | Tối Đa Hóa UX Trong Telegram | 3-4 tuần | Bot trông chuyên nghiệp, thao tác 1 chạm |
| **Phase 2** | Làm Khách Hàng Cảm Thấy Được Quan Tâm | 2-3 tuần | Bot có personality, nhớ user, empathy |
| **Phase 3** | Zero-Input Philosophy | 4-6 tuần | 90% giao dịch tự capture, không cần nhập |
| **Phase 4** | Behavioral Finance Engine | 4-5 tuần | Financial DNA + Micro-intervention + Twin |
| **Phase 5** | Mở Rộng Kênh (Web + PWA) | 3-4 tuần | Dashboard web, PWA, email digest |
| **Phase 6** | Scale & Commercialize | Ongoing | Household mode, Zalo Mini App, native |

**Tổng thời gian ước tính cho MVP commercializable: ~4-5 tháng**

---

# 🎨 PHASE 1: Tối Đa Hóa UX Trong Telegram

> **Lý do làm trước:** UX là lớp vỏ user nhìn thấy đầu tiên. Dù logic backend tốt đến đâu, nếu bot trả lời text khô khan, user sẽ bỏ đi trong 3 ngày. Phase này tạo nền tảng cho mọi thứ sau.

> **Kết quả sau Phase 1:** Bot trông giống một sản phẩm được đầu tư, mỗi tin nhắn đều đẹp và có action ngay.

## 1.1 — Rich Message Design

**Mục tiêu:** Thay thế toàn bộ tin nhắn plain text bằng format có cấu trúc.

### Công việc cần làm:

- [ ] **Tạo module `message_formatter.py`** trong FastAPI backend
  - Function `format_transaction()` — format tin nhắn xác nhận giao dịch
  - Function `format_summary()` — format báo cáo ngày/tuần/tháng
  - Function `format_alert()` — format cảnh báo ngân sách
  - Function `format_progress_bar(current, total, width=10)` — tạo `████████░░` Unicode

- [ ] **Thiết lập bảng emoji chuẩn cho từng category** (lưu trong `config/categories.py`):
  ```
  🍜 Ăn uống       🚗 Di chuyển      🏠 Nhà cửa
  👕 Mua sắm       💊 Sức khỏe       📚 Giáo dục
  🎮 Giải trí      💰 Tiết kiệm      📊 Đầu tư
  🎁 Quà tặng      ⚡ Tiện ích       🔄 Chuyển khoản
  ```

- [ ] **Chuẩn format tin nhắn xác nhận giao dịch**:
  ```
  ✅ Ghi xong!
  
  🍜 Phở Bát Đàn  —  45,000đ
  📍 Hà Nội  •  12:15
  
  💰 Hôm nay: 215k / 400k
     █████░░░░░ 54%
  
  Còn 185k cho hôm nay 👌
  ```

- [ ] **Chuẩn format báo cáo cuối ngày**:
  ```
  🌙 Tóm tắt ngày 15/04
  
  Tổng chi: 485,000đ (4 giao dịch)
  
  🍜 Ăn uống      245k  ████████░░
  🚗 Di chuyển    150k  █████░░░░░
  👕 Mua sắm       90k  ███░░░░░░░
  
  So với trung bình: +12% ↑
  ```

- [ ] **Test A/B đơn giản** với chính bạn: gửi format cũ vs mới, xem cái nào "cảm giác" tốt hơn.

---

## 1.2 — Inline Buttons Thông Minh

**Mục tiêu:** Mỗi tin nhắn bot gửi đều có ít nhất 1 action button. User không bao giờ phải gõ lệnh.

### Công việc cần làm:

- [ ] **Định nghĩa button layout chuẩn** cho từng loại tin nhắn:
  - Sau khi ghi giao dịch: `[🏷 Đổi danh mục] [✏️ Sửa] [🗑 Xóa]`
  - Báo cáo ngày: `[📊 Xem chi tiết] [📅 So sánh tuần trước]`
  - Cảnh báo ngân sách: `[⚙️ Điều chỉnh ngân sách] [📝 Xem giao dịch]`

- [ ] **Implement callback handlers** trong Telegram Bot:
  - Tạo dictionary routing `callback_data → handler_function`
  - Mỗi callback có prefix rõ ràng: `edit_tx:123`, `change_cat:123`, `view_report:2025-04`

- [ ] **Xử lý edit flow 1-chạm**:
  - User tap `[🏷 Đổi danh mục]` → bot hiện list categories dưới dạng inline buttons
  - User tap category mới → bot update DB + edit message gốc (không tạo tin nhắn mới)

- [ ] **Xử lý undo**:
  - Sau mỗi giao dịch vừa ghi, có button `[↶ Hủy (5s)]` auto-ẩn sau 5 giây
  - Nếu user tap → rollback DB

**Nguyên tắc UX:** Mọi action phải thực hiện **trong 1 tap, không rời chat thread**.

---

## 1.3 — Telegram Mini App (Chìa Khóa Vượt Giới Hạn Chat)

**Mục tiêu:** Khi user cần xem dashboard hoặc input phức tạp, mở Mini App thay vì text.

### Công việc cần làm:

- [ ] **Setup Mini App trong BotFather**:
  - Tạo Web App URL, enable Mini App
  - Domain phải có HTTPS (dùng FastAPI + Let's Encrypt hoặc Cloudflare tunnel)

- [ ] **Tạo route `/miniapp` trong FastAPI** serve static HTML/CSS/JS:
  - `/miniapp/dashboard` — dashboard xem báo cáo tháng
  - `/miniapp/budget` — form đặt ngân sách
  - `/miniapp/dna` — visualization Financial DNA (để Phase 4 dùng)

- [ ] **Build dashboard Mini App đầu tiên**:
  - Stack gợi ý: Vanilla JS + Chart.js (nhẹ, load nhanh)
  - Auth qua Telegram `initData` (Telegram gửi user_id đã verify)
  - Hiển thị: pie chart category, line chart 3 tháng, list giao dịch lớn nhất

- [ ] **Thêm button `[📊 Dashboard]` vào bot menu chính**:
  - Mỗi khi user gõ `/report` hoặc tap button này → mở Mini App

- [ ] **Optimize tốc độ load**:
  - Mini App phải load <1s (nếu không user sẽ khó chịu)
  - Dùng skeleton loading khi fetch data

**Lưu ý kỹ thuật:** Mini App chỉ là web app thông thường, verify user qua `initData` HMAC. FastAPI có sẵn hết cơ sở hạ tầng.

---

## 1.4 — Visual Identity Nhất Quán

**Mục tiêu:** Bot có brand rõ ràng, nhất quán ở mọi touchpoint.

### Công việc cần làm:

- [ ] **Chọn tên bot cuối cùng** (ví dụ gợi ý: "Xu", "Tiết", "Money" — thân thiện, dễ nhớ)

- [ ] **Thiết kế mascot đơn giản**:
  - Có thể thuê Fiverr/99designs (~$50-100) hoặc dùng AI (Midjourney)
  - Gợi ý concept: con heo đất cách điệu, chú sóc, hoặc một nhân vật trung tính
  - Yêu cầu: 3 expression (vui, lo lắng, ngạc nhiên) để dùng trong các tình huống khác nhau

- [ ] **Tạo bộ sticker Telegram** (tùy chọn, nhưng rất hiệu quả):
  - 10-15 stickers biểu cảm
  - Bot dùng sticker trong những khoảnh khắc cảm xúc (ví dụ: user đạt mục tiêu → sticker chúc mừng)

- [ ] **Chuẩn hóa tone writing**:
  - Xưng "mình" - "bạn"
  - Viết ngắn, có khoảng trắng giữa các ý
  - Dùng emoji có chọn lọc (không lạm dụng)
  - Không bao giờ dùng từ phán xét ("sai", "tệ", "lãng phí")

---

# 💝 PHASE 2: Làm Khách Hàng Cảm Thấy Được Quan Tâm

> **Lý do làm sau Phase 1:** Personality cần "vỏ" đẹp để thể hiện. Nếu làm personality trên text khô, user không cảm nhận được.

> **Kết quả sau Phase 2:** User cảm thấy bot "hiểu mình", không phải bot generic. Retention tăng mạnh.

## 2.1 — First Impression Ritual (Onboarding 3 Phút)

**Mục tiêu:** 30 giây đầu tiên phải có "wow moment" khiến user muốn ở lại.

### Công việc cần làm:

- [ ] **Viết kịch bản onboarding 3 phút**, chia thành các step:
  
  **Step 1 (10 giây):** Lời chào ấm áp
  ```
  👋 Chào bạn!
  
  Mình là [tên bot] — trợ lý tài chính của bạn.
  Mình không chỉ ghi chép — mình hiểu bạn.
  ```
  
  **Step 2 (20 giây):** Hỏi tên
  ```
  Trước tiên, cho mình hỏi nhẹ nhé:
  Bạn muốn mình gọi bạn là gì?
  ```
  → User nhập tên → lưu DB
  
  **Step 3 (30 giây):** Hỏi mục tiêu (button)
  ```
  [Tên user] ơi, bạn đang muốn cải thiện điều gì nhất?
  
  [💰 Tiết kiệm nhiều hơn]
  [📊 Hiểu mình tiêu vào đâu]
  [🎯 Đạt mục tiêu cụ thể]
  [🧘 Bớt stress về tiền]
  ```
  → Lưu vào `users.primary_goal`
  
  **Step 4 (60 giây):** Ghi giao dịch đầu tiên
  ```
  Thử ngay nhé! Hôm nay bạn đã chi gì chưa?
  Gõ số tiền và nơi chi — ví dụ: "45k phở"
  ```
  → Bot parse, xác nhận, lưu
  
  **Step 5 (60 giây):** Aha moment
  ```
  🎉 Tuyệt! Mình đã ghi rồi.
  
  Từ giờ, bạn có thể:
  • Gõ như vậy bất cứ lúc nào
  • Gửi ảnh hóa đơn, mình đọc được
  • Gửi voice, mình hiểu luôn
  
  Sẵn sàng chưa? 💪
  ```

- [ ] **Implement onboarding state machine** trong backend:
  - Table `users` thêm column `onboarding_step` (0-5)
  - Mỗi tin nhắn user gửi, kiểm tra step hiện tại, xử lý phù hợp
  - Skip được (user tap "Bỏ qua") nhưng bot nhắc lại sau

- [ ] **Lưu thông tin cá nhân hóa**:
  - `users.display_name` — tên user muốn được gọi
  - `users.primary_goal` — mục tiêu chính
  - `users.onboarding_completed_at` — timestamp

---

## 2.2 — Ghi Nhớ & Nhắc Lại (Memory Moments)

**Mục tiêu:** Bot "nhớ" và nhắc lại các moment có ý nghĩa, tạo cảm giác có mối quan hệ.

### Công việc cần làm:

- [ ] **Tạo table `user_milestones`** lưu các cột mốc:
  - `first_transaction_at`
  - `first_budget_set_at`
  - `first_saving_milestone_at` (khi tiết kiệm được 1tr, 5tr, 10tr)
  - `streak_days` (số ngày liên tục theo dõi chi tiêu)

- [ ] **Scheduled job `check_milestones.py`** chạy mỗi sáng:
  - Check nếu user đạt milestone mới → gửi tin nhắn chúc mừng
  - Check nếu hôm nay là "tròn X ngày" dùng app → gửi tin nhắn kỷ niệm

- [ ] **Viết sẵn 20+ tin nhắn milestone** cho các trường hợp:
  - 7 ngày: "1 tuần rồi nhỉ! Bạn đã ghi 23 giao dịch..."
  - 30 ngày: "Tròn 1 tháng rồi! Cùng nhau nhìn lại hành trình nhé 👇"
  - 100 ngày: "100 ngày! Đây là con số đặc biệt — 80% người bỏ cuộc trong 30 ngày đầu..."
  - Tiết kiệm 10% thu nhập lần đầu: "Ồ! Lần đầu tiên bạn tiết kiệm được 10%..."

- [ ] **Nhắc lại mục tiêu đã đặt**:
  - Mỗi tuần 1 lần, bot nhắc: "Nhớ bạn nói muốn [goal] chưa? Tuần này bạn đã tiến gần hơn rồi đó 🌱"

---

## 2.3 — Empathy Moments (Khoảnh Khắc Cảm Thông)

**Mục tiêu:** Phát hiện cảm xúc user và phản hồi đúng — không phán xét, không dạy đời.

### Công việc cần làm:

- [ ] **Định nghĩa các trigger empathy** trong `empathy_rules.py`:
  
  | Trigger | Phản hồi |
  |---------|----------|
  | User vượt ngân sách tháng | "Không sao cả. Mình để ý có đám cưới/về quê — những thứ đáng giá..." |
  | User đạt milestone tiết kiệm | "Đây là bước ngoặt — 80% người không đạt được..." |
  | User im lặng >7 ngày | "👋 Lâu rồi không gặp. Mọi thứ ổn chứ?" |
  | User ghi giao dịch lớn bất thường | "Ồ giao dịch lớn! Mình xếp vào đâu cho hợp lý nhỉ?" |
  | User chi nhiều vào cuối tuần | (Không phán xét) "Cuối tuần mà — tận hưởng thôi 😊" |

- [ ] **Implement `check_empathy_triggers.py`** — scheduled job chạy mỗi giờ, check conditions

- [ ] **Nguyên tắc viết tin nhắn empathy**:
  - Không bao giờ dùng "đừng", "không nên", "phải"
  - Luôn có sự thấu hiểu context ("Mình để ý thấy...")
  - Đưa ra lựa chọn, không ra lệnh
  - Dùng "chúng ta" thay vì "bạn" khi nói về kế hoạch

---

## 2.4 — Surprise & Delight (Easter Eggs)

**Mục tiêu:** Những khoảnh khắc bất ngờ khiến user muốn screenshot khoe bạn bè.

### Công việc cần làm:

- [ ] **Fun facts hàng tuần**:
  - Scheduled job chủ nhật: tính toán 1 fun fact từ dữ liệu user
  - Ví dụ: "Tháng này bạn tiêu 1.2tr cho café — bằng 60 ly Highlands 😄"
  - Template facts: cafe count, số lần Grab, chi phí/ngày trung bình...

- [ ] **Seasonal content** (quan trọng với thị trường VN):
  - **Tết Nguyên Đán**: Bot đổi avatar, tự động tạo category "Lì xì", báo cáo chi tiêu Tết
  - **Trung thu**: Nhắc về pattern chi bánh trung thu năm trước
  - **Đầu năm học**: Alert về chi tiêu cho con cái
  - **Black Friday / 11.11**: Cảnh báo "mùa mua sắm" sắp tới

- [ ] **Streak gamification nhẹ**:
  - Mỗi ngày user ghi ít nhất 1 giao dịch → +1 streak
  - Streak 7/30/100 ngày có badge đặc biệt
  - Không over-gamify (đây là finance app, không phải Duolingo)

- [ ] **Viết file `seasonal_content.py`** với calendar các sự kiện VN đã plan sẵn cho 12 tháng

---

# 🤖 PHASE 3: Zero-Input Philosophy

> **Lý do làm sau Phase 1 & 2:** Khi user đã "yêu" bot, họ sẵn sàng làm các setup phức tạp hơn (SMS forwarder, cấp permission). Nếu làm ngược — bot generic, setup khó — họ sẽ bỏ.

> **Kết quả sau Phase 3:** 90% giao dịch tự động vào hệ thống, user chỉ cần verify hoặc sửa khi cần.

## 3.1 — Tầng 1: SMS Banking Auto-Capture (Ưu Tiên Cao Nhất)

**Mục tiêu:** Tự động capture 100% giao dịch qua ngân hàng mà không cần user nhập.

### Công việc cần làm:

- [ ] **Nghiên cứu format SMS của top 5 bank VN** (quan trọng nhất):
  - Vietcombank (VCB)
  - Techcombank
  - MB Bank
  - ACB
  - VPBank
  
  → Thu thập 10-20 mẫu SMS mỗi bank (từ chính bạn và bạn bè)

- [ ] **Viết regex parser cho từng bank** trong `sms_parsers/`:
  ```python
  # Ví dụ cho VCB
  VCB_PATTERN = r"TK VCB (\d+).*?(-|\+)([\d,]+) VND.*?luc (\d{2}:\d{2}) (\d{2}/\d{2}).*?Noi dung: (.*?)SD"
  ```
  - Extract: account, amount, direction (chi/thu), time, date, description

- [ ] **Tạo smart categorizer** (`categorizer.py`):
  - Rule-based first: nếu description chứa "GRAB" → "Di chuyển"
  - LLM fallback (DeepSeek): nếu không match rule, gọi LLM phân loại
  - Học từ user: nếu user sửa category, save rule mới

- [ ] **Hướng dẫn user setup SMS Forwarder**:
  - Viết guide HTML (nhúng vào Mini App): "Cài SMS Forwarder trên Android"
  - Quay video 30 giây cho từng bank phổ biến (có thể screen record trên máy mình)
  - Bot gửi link guide khi user chọn "Thiết lập tự động ghi"

- [ ] **Implement endpoint `/webhook/sms`** nhận SMS forward:
  - Telegram bot nhận tin nhắn → check pattern → route vào SMS parser
  - Parse thành công → lưu DB → bot gửi confirmation đẹp
  - Parse thất bại → lưu raw, hỏi user "Đây là giao dịch gì?"

- [ ] **Handle edge cases**:
  - SMS OTP (bỏ qua, không lưu)
  - SMS quảng cáo từ bank (bỏ qua)
  - Giao dịch hoàn tiền/refund (xử lý riêng)
  - Chuyển khoản giữa tài khoản của chính user (không tính là chi/thu)

**Thời gian ước tính: 2 tuần** (1 tuần parsers + 1 tuần testing với users thật)

---

## 3.2 — Tầng 2: Screenshot OCR

**Mục tiêu:** Capture giao dịch từ MoMo, ZaloPay, VNPay qua ảnh screenshot.

### Công việc cần làm:

- [ ] **Integrate Claude Vision API** (bạn đã có sẵn trong stack):
  - Endpoint nhận ảnh từ Telegram → gửi tới Claude Vision với prompt chuẩn
  - Prompt: "Đây là screenshot giao dịch. Extract: số tiền, người nhận/đơn vị, thời gian, phương thức thanh toán. Trả về JSON."

- [ ] **Xử lý batch screenshots**:
  - User có thể gửi nhiều ảnh cùng lúc
  - Bot xử lý tuần tự, gửi 1 tin nhắn tổng: "Đã xử lý 5 ảnh: 3 thành công, 2 cần xem lại"

- [ ] **Fallback UI khi OCR không chắc chắn**:
  - Nếu Vision confidence thấp → bot hiện form pre-fill với các ô user có thể sửa
  - Hoặc hỏi user: "Số tiền là 150k hay 1.5tr?"

- [ ] **Tối ưu chi phí API**:
  - Cache kết quả parse theo hash ảnh (tránh parse lại cùng 1 ảnh)
  - Resize ảnh trước khi gửi (giảm token)

---

## 3.3 — Tầng 3: Voice Input

**Mục tiêu:** User nói "Vừa ăn phở 45k" → hệ thống ghi ngay.

### Công việc cần làm:

- [ ] **Integrate speech-to-text**:
  - Option A: OpenAI Whisper API (chính xác tiếng Việt, ~$0.006/phút)
  - Option B: DeepSeek audio (nếu hỗ trợ)
  - Option C: Self-host Whisper (free, cần GPU — để sau)

- [ ] **Flow xử lý voice**:
  - User gửi voice message → Telegram trả về audio file
  - Download file → gửi tới Whisper → nhận transcript
  - Transcript → NLU parser (rule-based + LLM) → extract amount, description
  - Confirm với user

- [ ] **Học context từ lịch sử**:
  - "Như hôm qua" → lookup giao dịch gần nhất của user
  - "Quán cũ" / "Chỗ quen" → lookup location đã ghi nhiều lần

- [ ] **Xử lý tiếng Việt có dấu/không dấu**:
  - Whisper có thể transcribe không dấu → normalize trước khi parse
  - Test với giọng miền Bắc, Nam, Trung

---

## 3.4 — Tầng 4: Passive Location Capture (Nâng Cao — Opt-in)

**Mục tiêu:** Bot chủ động hỏi khi phát hiện user đang ở địa điểm chi tiêu.

### Công việc cần làm:

- [ ] **Flow opt-in rõ ràng**:
  - Setting "Nhắc khi đi mua sắm" — mặc định TẮT
  - Giải thích rõ: "Bot sẽ hỏi nhẹ khi bạn dừng ở quán/siêu thị. Bạn kiểm soát hoàn toàn."
  - User có thể bật/tắt bất cứ lúc nào

- [ ] **Implement location tracking**:
  - Qua Telegram Mini App với Geolocation API
  - User mở Mini App 1 lần/ngày, app ping location về server
  - HOẶC yêu cầu user share location thủ công

- [ ] **Detect "commercial stop"**:
  - Dùng Google Places API để check nếu location là quán ăn/siêu thị/café
  - Nếu user dừng >15 phút → trigger hỏi

- [ ] **Tin nhắn chủ động**:
  - "Bạn đang ở Highlands Coffee Láng Hạ? Vừa chi bao nhiêu vậy?"
  - Buttons: `[30k] [50k] [85k] [Khác] [Không chi gì]`

**Lưu ý:** Phase này nhạy cảm về privacy. Cần transparency tuyệt đối.

---

## 3.5 — Tầng 5: Daily Wrap-up (Safety Net)

**Mục tiêu:** Bắt các giao dịch bỏ sót qua conversation cuối ngày.

### Công việc cần làm:

- [ ] **Scheduled job gửi wrap-up lúc 20:30 mỗi ngày**:
  ```
  🌙 Tóm tắt ngày 15/04:
  
  Đã ghi nhận:
  ✓ Grab 150k (từ SMS VCB)
  ✓ Highlands 85k (bạn đã nhắn)
  ✓ Lotte Mart 320k (từ screenshot MoMo)
  
  Có khoản nào thiếu không?
  [✅ Đủ rồi] [➕ Bổ sung]
  ```

- [ ] **Conversational flow khi user chọn "Bổ sung"**:
  - Bot hỏi: "Kể mình nghe bạn đã chi gì nữa?"
  - User gõ tự do → parser extract
  - Có thể lặp lại nhiều lần cho tới khi user nói "xong"

- [ ] **Adaptive timing**:
  - Nếu user thường online lúc 22h → gửi lúc 21:45
  - Nếu user chưa đọc wrap-up → không gửi lại sáng hôm sau (không spam)

---

# 🧬 PHASE 4: Behavioral Finance Engine

> **Lý do làm sau Phase 3:** Cần ít nhất 30-60 ngày dữ liệu sạch để phân tích pattern có ý nghĩa. Nếu làm sớm, insights sẽ sai.

> **Kết quả sau Phase 4:** Sản phẩm khác biệt hoàn toàn so với mọi finance app — không chỉ tracking mà thực sự thay đổi hành vi user.

## 4.1 — Financial DNA Profiling

### Công việc cần làm:

- [ ] **Tạo table `user_patterns`**:
  ```sql
  - user_id
  - pattern_type (stress_spending, fomo_buyer, weekend_splurger, ...)
  - confidence_score (0-1)
  - detected_at
  - evidence (JSONB — các giao dịch support pattern này)
  ```

- [ ] **Định nghĩa 8-10 pattern types**:
  1. **Stress spender** — chi mạnh vào cuối tuần/tối muộn
  2. **FOMO buyer** — mua nhiều vào các dịp sale (11.11, Black Friday)
  3. **Payday splurger** — chi 40%+ trong 3 ngày đầu nhận lương
  4. **Subscription hoarder** — nhiều subscription không dùng
  5. **Small-bleed spender** — nhiều giao dịch nhỏ tích lại lớn
  6. **Social spender** — chi nhiều cho nhậu/gặp gỡ
  7. **Delivery dependent** — >40% ăn uống qua GrabFood/ShopeeFood
  8. **Saver-then-splurge** — tiết kiệm 3 tuần rồi bùng 1 lần

- [ ] **Pattern detection algorithms** (chạy weekly):
  - Analyze last 60-90 days transactions
  - Apply rules cho mỗi pattern type
  - Update `user_patterns` với confidence score

- [ ] **Visualization trong Mini App**:
  - Hiển thị top 3 patterns nổi bật
  - Mỗi pattern có giải thích + ví dụ từ chính dữ liệu user
  - Không judgmental — chỉ observation

---

## 4.2 — Micro-Intervention Engine

### Công việc cần làm:

- [ ] **Tạo rules engine `interventions.py`**:
  - Mỗi rule có: trigger condition + message template + cooldown
  - Ví dụ:
    ```python
    {
      "name": "payday_splurge_warning",
      "trigger": "3 days after salary received AND spent > 30% of salary",
      "message": "Lương vừa vào được 3 ngày, bạn đã tiêu 35%... Muốn 'khóa' 2tr vào tiết kiệm ngay không?",
      "cooldown_days": 30
    }
    ```

- [ ] **Implement 15-20 intervention rules** bao phủ các scenarios phổ biến

- [ ] **Timing thông minh**:
  - Không gửi vào giờ ngủ (22h-7h)
  - Không gửi >2 interventions/ngày
  - Học từ response: nếu user ignore, giảm frequency

- [ ] **A/B test tone**:
  - Version A: thẳng thắn ("Bạn đã chi quá 30% lương")
  - Version B: mềm mại ("Mình để ý thấy...")
  - Track response rate để chọn tone tốt hơn

---

## 4.3 — Financial Twin (Hero Feature)

### Công việc cần làm:

- [ ] **Thiết kế thuật toán "optimal twin"**:
  - Given: user income, fixed expenses, demographic
  - Compute: optimal saving rate, investment allocation, discretionary budget
  - Dựa trên các best practices tài chính cá nhân (50-30-20 rule, 6-month emergency fund, ...)

- [ ] **Monthly comparison report**:
  ```
  Tháng 3 — Bạn vs Financial Twin:
  
  Thu nhập:        Bạn 20tr    Twin 20tr
  Tiết kiệm:       Bạn 1.5tr   Twin 4.2tr
  Đầu tư:          Bạn 0       Twin 2tr
  
  📉 Khoảng cách sau 5 năm: ~180 triệu
  ```

- [ ] **Visualization mạnh mẽ trong Mini App**:
  - Line chart: tài sản user vs twin qua 5/10 năm (compound interest)
  - Số "để mất" hiển thị lớn, ấn tượng tâm lý

- [ ] **Actionable suggestions**:
  - Không chỉ show gap, phải gợi ý cách đóng gap
  - "Nếu bạn tăng tiết kiệm 500k/tháng từ bây giờ..."

- [ ] **Không shaming**:
  - Twin là "bạn phiên bản tối ưu", không phải "bạn nên xấu hổ"
  - Framing: "Cơ hội đang chờ bạn" thay vì "Bạn đang lãng phí"

---

# 🌐 PHASE 5: Mở Rộng Kênh

> **Lý do làm giai đoạn này:** Khi user đã engaged qua Telegram, nhu cầu xem dashboard lớn, export báo cáo, chia sẻ với vợ/chồng sẽ nảy sinh. Đây là lúc mở rộng kênh.

## 5.1 — Web Dashboard

### Công việc cần làm:

- [ ] **Build Next.js web app**:
  - Stack: Next.js 14 + Tailwind + shadcn/ui
  - Deploy trên Vercel (free tier đủ cho giai đoạn đầu)

- [ ] **Magic link authentication từ Telegram**:
  - User gõ `/web` trong Telegram → bot gửi link có token
  - Token verify → tạo session → user đăng nhập

- [ ] **Pages chính**:
  - `/` — Overview (cards số liệu chính)
  - `/transactions` — List + filter + search
  - `/reports` — Biểu đồ, so sánh theo tháng/năm
  - `/dna` — Financial DNA visualization
  - `/settings` — Cấu hình tài khoản

- [ ] **Export features**:
  - Export PDF báo cáo tháng (đẹp, có thể gửi cho kế toán)
  - Export Excel raw data
  - Share link báo cáo (có thể chia sẻ với cố vấn tài chính)

---

## 5.2 — Progressive Web App (PWA)

### Công việc cần làm:

- [ ] **Setup PWA manifest** cho web app
- [ ] **Service worker** để cache offline
- [ ] **Push notifications** (thay thế/bổ sung cho Telegram)
- [ ] **Install prompt** hiển thị sau 3 lần user dùng web
- [ ] **Test trên iOS Safari + Android Chrome**

---

## 5.3 — Email Weekly Digest

### Công việc cần làm:

- [ ] **Thiết kế email template HTML đẹp** (MJML framework)
- [ ] **Content mỗi email**:
  - Số liệu tuần key
  - 1 insight cá nhân hóa
  - 1 milestone (nếu có)
  - Link về web dashboard
- [ ] **Scheduled job gửi mỗi chủ nhật 20h**
- [ ] **Unsubscribe link rõ ràng**

---

# 🚀 PHASE 6: Scale & Commercialize

## 6.1 — Household Mode (Tài Chính Gia Đình)

### Công việc cần làm:

- [ ] **Schema changes**:
  - Table `households` — mỗi household có nhiều users
  - Transactions có thể thuộc `household_id` (shared) hoặc chỉ `user_id` (cá nhân)

- [ ] **Invite flow**:
  - User tạo household → share invite link
  - Người được mời accept → join household

- [ ] **Shared reports**:
  - Báo cáo tổng household
  - Breakdown ai chi gì
  - Privacy: mỗi user có thể giữ 1 số giao dịch "cá nhân"

- [ ] **Target segment**: Gia đình trung lưu 30-45 tuổi (khả năng trả tiền cao nhất VN)

---

## 6.2 — Pricing & Monetization

### Công việc cần làm:

- [ ] **Freemium model**:
  - **Free**: 100 giao dịch/tháng, basic reports, 1 user
  - **Pro (99k/tháng)**: Unlimited, Financial DNA, Twin, Household mode
  - **Family (149k/tháng)**: Tới 4 users, household features

- [ ] **Payment integration**: VNPay / MoMo / bank transfer
- [ ] **14-day free trial** cho Pro

---

## 6.3 — Zalo Mini App (Mass Market)

### Công việc cần làm:

- [ ] Đăng ký Zalo OA
- [ ] Build Zalo Mini App (UI tương tự Telegram Mini App)
- [ ] Migrate users từ Telegram → cross-platform

---

## 6.4 — Growth Tactics

### Công việc cần làm:

- [ ] **Viral loop**: Share báo cáo đẹp cuối năm (như Spotify Wrapped)
- [ ] **Referral program**: Mời bạn → cả 2 được 1 tháng Pro free
- [ ] **Content marketing**: TikTok/Youtube về tài chính cá nhân VN
- [ ] **Partnerships**: Hợp tác với bank/fintech VN

---

# 📊 Metrics Quan Trọng Cần Track

> Ngay từ Phase 1, setup analytics để đo lường các chỉ số sau:

**Activation:**
- % user hoàn thành onboarding (target: >70%)
- Time to first transaction (target: <5 phút)

**Engagement:**
- Daily Active Users / Monthly Active Users (target: >40%)
- Avg transactions/user/week (target: >10)
- % user dùng ít nhất 2 capture methods (target: >50%)

**Retention:**
- D1, D7, D30 retention (target: 80% / 50% / 30%)
- Churn rate monthly (target: <10%)

**Satisfaction:**
- NPS score (target: >50)
- % user feedback tích cực về "personality" (qualitative)

---

# ⚠️ Rủi Ro & Mitigation

| Rủi ro | Mitigation |
|--------|-----------|
| Telegram bị chặn ở VN | Sớm build Zalo Mini App (Phase 6) + Web PWA (Phase 5) |
| SMS Forward không hoạt động trên iPhone | OCR + Voice là alternative |
| Privacy concerns (SMS, location) | Transparency tuyệt đối, opt-in, local processing khi có thể |
| LLM cost scale lên triệu user | Cache aggressive, rule-based fallback, self-host khi feasible |
| Cạnh tranh từ MISA/Money Lover | Lợi thế: AI-native, capture tốt hơn, personality — khó copy trong 12 tháng |

---

# 🎯 Nguyên Tắc Vàng Khi Implement

1. **Ship sớm, iterate nhanh** — Phase 1 xong → cho 10 users thật dùng → nghe feedback → sửa
2. **Metrics-driven** — Mỗi feature launch phải đo impact
3. **User interview mỗi tuần** — Nói chuyện với 2-3 users thật, không chỉ nhìn số
4. **Personality trước, feature sau** — User ở lại vì cảm xúc, không vì feature list
5. **Không over-engineer** — Rule-based trước khi ML, monolith trước khi microservices

---

# 📝 Ghi Chú Cuối

Tài liệu này là **living document** — cập nhật khi có insight mới từ users hoặc thay đổi thị trường.

**Ưu tiên thực hiện theo thứ tự Phase**, nhưng trong mỗi Phase có thể parallelize các task độc lập.

Khi bắt đầu mỗi Phase, tạo file `phase-X-detailed.md` riêng để break down công việc xuống cấp task nhỏ hơn.

**Good luck! 🚀**
