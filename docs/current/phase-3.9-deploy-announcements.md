# Phase 3.9 — Deploy Announcement Templates

> **Phase:** 3.9 — Market Data Real (giá cổ phiếu, crypto, vàng, lãi suất, tin tức thị trường thời gian thực).
> **Reference:** [phase-3.9-detailed.md](./phase-3.9/phase-3.9-detailed.md)
> **Status:** Reference copy — operator broadcasts via
> `scripts/broadcast_announcement.py` (see § Broadcast tool below).

Phase 3.9 là bước ngoặt lớn nhất kể từ khi app ra đời: **mọi con số tài chính giờ
là số thật, không còn placeholder**. Morning briefing sẽ hiển thị giá thị trường
thực tế, portfolio tự động cập nhật, và bạn biết được mình lãi/lỗ bao nhiêu so với
giá mua.

Đây là **3-message campaign**: teaser trước deploy, launch ngay sau khi lên, và
follow-up sau 1 tuần cho ai chưa mở briefing.

Tone theo [tone_guide.md](./tone_guide.md): "mình" / "bạn", ấm áp, không phán xét,
gợi ý chứ không ép buộc.

---

## Message 1 — Pre-deploy teaser (1 ngày trước khi deploy)

**ID:** `teaser`
**When:** ~24h trước deploy, buổi tối 19h–21h để tỷ lệ đọc cao nhất.
**Goal:** Tạo kỳ vọng, chuẩn bị tâm lý user rằng sắp có nâng cấp quan trọng.

```
📊 *Sắp có cập nhật lớn từ Bé Tiền!*

Từ ngày mai, tất cả số liệu tài chính của bạn sẽ là *số thật*:

📈 Giá cổ phiếu cập nhật mỗi 15 phút (giờ giao dịch)
₿ Giá crypto cập nhật mỗi 5 phút, 24/7
🪙 Giá vàng SJC mới nhất trong ngày
🏦 Lãi suất từ 20 ngân hàng lớn
📰 Tin tức thị trường liên quan đến danh mục của bạn

Buổi sáng mở app, bạn sẽ thấy *số thật* — không còn giá tự nhập nữa.

Hẹn gặp bạn sáng mai 💚
```

---

## Message 2 — Launch announcement (trong vòng 1h sau khi deploy)

**ID:** `launch`
**When:** Ngay sau khi deploy pass smoke test.
**Goal:** Thông báo live, hướng dẫn 1 hành động cụ thể để user trải nghiệm ngay.

```
🎉 *Dữ liệu thị trường thật đã lên rồi!*

Từ giờ Bé Tiền dùng giá thật — không còn giá bạn tự nhập nữa.

*Thử ngay:*

☀️ Gõ _"briefing sáng"_ hoặc /briefing
→ Xem tổng tài sản cập nhật theo giá thị trường hôm nay
→ VN-Index, giá vàng, BTC — tất cả đều là số thật

📊 *Có cổ phiếu hoặc crypto?*
Portfolio của bạn giờ tự cập nhật — không cần nhập giá tay nữa.
Bạn còn thấy được: _giá mua vs giá hiện tại → lãi/lỗ bao nhiêu %_

🔔 *Cổ phiếu tăng/giảm đột ngột?*
Mình sẽ nhắn khi cổ phiếu bạn đang giữ biến động ≥5% trong 15 phút.

📰 Tin thị trường buổi sáng sẽ được lọc riêng theo danh mục của bạn —
chỉ thấy tin liên quan, không bị ngập bởi tin chung.

Mọi thứ cũ vẫn nguyên, chỉ chính xác hơn thôi 😊
Cứ hỏi tự nhiên như cũ nhé!
```

---

## Message 3 — Follow-up nudge (7 ngày sau launch)

**ID:** `followup`
**When:** +7 ngày. Bỏ qua user đã mở briefing hoặc xem portfolio sau ngày launch.
**Goal:** Kéo lại user chưa thử — đây là tính năng cốt lõi, quan trọng để họ trải nghiệm.

```
👋 *Tuần qua thế nào rồi?*

Mình thấy bạn chưa thử dữ liệu thị trường mới — không sao,
chỉ nhắc nhẹ vì bạn có thể đang bỏ lỡ:

☀️ *Briefing buổi sáng giờ xịn hơn nhiều*
→ Gõ /briefing để xem giá cổ phiếu, vàng, crypto — số thật, cập nhật tới hôm nay
→ Tin tức lọc riêng theo danh mục của bạn

📊 *Biết mình đang lãi hay lỗ bao nhiêu?*
→ Gõ _"portfolio của tôi"_ — mình tính P/L so với giá bạn mua

Chỉ cần thử briefing một lần thôi 💚
Gõ /briefing hoặc hỏi mình _"sáng nay thị trường thế nào?"_
```

---

## Broadcast tool

**Script:** `scripts/broadcast_announcement.py`

One-click broadcast. Operator chọn message bằng `--message <id>`, script đọc
nội dung từ file này, liệt kê recipients, hỏi xác nhận, rồi gửi có throttling.

### Cách dùng cho Phase 3.9

```bash
# Bước 1 — Preview nội dung trước khi gửi (luôn làm trước)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-3.9-deploy-announcements.md \
    --message teaser --dry-run

# Bước 2 — Test trên Telegram ID của chính mình
python scripts/broadcast_announcement.py \
    --file docs/current/phase-3.9-deploy-announcements.md \
    --message teaser --only <YOUR_TELEGRAM_ID>

# Bước 3 — Gửi teaser (~24h trước deploy)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-3.9-deploy-announcements.md \
    --message teaser

# Bước 4 — Gửi launch (trong vòng 1h sau deploy + smoke test pass)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-3.9-deploy-announcements.md \
    --message launch

# Bước 5 — Gửi follow-up sau 7 ngày, chỉ cho user chưa mở briefing
python scripts/broadcast_announcement.py \
    --file docs/current/phase-3.9-deploy-announcements.md \
    --message followup --skip-engaged --launch-date 2026-06-18
```

> **Lưu ý quan trọng:** Script mặc định đọc file Phase 3.8. Với Phase 3.9,
> **phải luôn truyền `--file docs/current/phase-3.9-deploy-announcements.md`**.

### `--skip-engaged` hoạt động thế nào

Với Phase 3.9, "engaged" được đo bằng user đã tạo goal kể từ `--launch-date`
(logic hiện tại trong script). Để chính xác hơn cho Phase 3.9, bạn có thể
extend `_engaged_user_ids()` trong script để check thêm:
- User mở briefing sau launch date (query `briefing_logs` nếu có)
- User xem portfolio sau launch date

Nhưng nếu chưa có bảng đó, dùng goal check là đủ an toàn.

### Options

| Flag | Mục đích |
|---|---|
| `--message <id>` | Bắt buộc. Một trong: `teaser`, `launch`, `followup`. |
| `--file <path>` | Bắt buộc cho 3.9. Trỏ tới file này. |
| `--dry-run` | Preview + list recipients, không gửi thật. |
| `--only <telegram_id>` | Gửi cho 1 user (để test). |
| `--skip-engaged` | Cho `followup`: bỏ qua user đã engage với features mới. |
| `--launch-date YYYY-MM-DD` | Ngày deploy thật, dùng với `--skip-engaged`. |
| `--throttle-ms <n>` | Delay giữa các lần gửi (default 50ms). Tăng lên 200+ nếu > 1k users. |
| `--yes` | Bỏ qua prompt xác nhận (dùng trong CI / scripted). |

### Safety checklist

- [ ] Đọc to message — nếu cứng hoặc máy móc thì viết lại.
- [ ] Kiểm tra Markdown render (dấu `*` balanced, không có `_` thừa).
- [ ] Feature name phải khớp với thứ đã ship thật.
- [ ] Test `--only <your_telegram_id>` trước.
- [ ] `--dry-run` để confirm số lượng recipients.
- [ ] Gửi thật.

---

## Timeline gợi ý

| Thời điểm | Action |
|---|---|
| T-1 ngày (tối) | Gửi `teaser` |
| Deploy day (sáng sớm) | Deploy + chạy smoke test |
| Deploy day (trong 1h) | Gửi `launch` |
| T+7 ngày | Gửi `followup` với `--skip-engaged --launch-date <deploy-date>` |
