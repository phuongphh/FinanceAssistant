# Phase 4B — Deploy Announcement Templates

> **Phase:** 4B — Twin Polish + Life Event Simulator + Cashflow Forecasting v2 + Zalo Adapter.
> **Reference:** [phase-4B-detailed.md](./phase-4B-detailed.md)
> **Status:** Reference copy — operator broadcasts via `scripts/broadcast_announcement.py` (see § Broadcast tool below).

Phase 4B đưa Twin từ "dự phóng lý thuyết" sang **"dự phóng có thật của cuộc đời bạn"**: mua nhà, kết hôn, con cái, học phí đại học — không còn là vết nứt trong kế hoạch, mà là những cột mốc được Bé Tiền vẽ thẳng vào cone tương lai.

Ngoài Life Events, Phase 4B cũng nâng cashflow: Bé Tiền tự phát hiện các khoản chi định kỳ của bạn (điện, nước, Netflix, tiền thuê...) và dự báo 3 tháng tới với cảnh báo sớm nếu tài khoản có nguy cơ âm. Cuối cùng: Zalo — để Bé Tiền có thể gửi nhắc nhở qua kênh bạn đang dùng.

Đây là **3-message campaign**: teaser trước deploy, launch ngay sau khi lên, và follow-up cho user chưa thử Life Events sau 1 tuần.

Tone theo [tone_guide.md](../phase-4A/tone_guide.md): "mình" / "bạn", ấm áp, **probability over precision** — không bao giờ hứa con số chắc chắn. Với life events, KHÔNG BAO GIỜ gợi ý delay cột mốc cá nhân vì lý do tài chính.

---

## Message 1 — Pre-deploy teaser (1 ngày trước deploy)

**ID:** `teaser`
**When:** ~24h trước deploy, buổi tối 19h–21h.
**Goal:** Gây tò mò về Life Events — "lần đầu tiên Twin biết bạn sắp mua nhà".

```
🌅 *Sắp có một thứ mình nghĩ bạn sẽ thích...*

Bạn nhớ cái cone tương lai mình gửi trước không?
Nó đẹp — nhưng còn thiếu một thứ:

*Những cột mốc thật của cuộc đời bạn.*

Mua nhà. Kết hôn. Đón con đầu lòng.
Cho con vào đại học. Hay chỉ đơn giản là nghỉ ngơi sớm hơn.

Ngày mai, Bé Tiền sẽ có thể *vẽ những điều đó thẳng vào tương lai của bạn* —
không phải lo lắng, không phải cảnh báo,
mà chỉ là: _"Nếu mình mua nhà năm 2028, cone trông như thế này"_.

Hẹn bạn ngày mai 💚
```

---

## Message 2 — Launch announcement (trong vòng 1h sau deploy)

**ID:** `launch`
**When:** Ngay sau khi deploy pass smoke test (Life Events endpoint live + cashflow forecast cron chạy + Zalo link flow accessible).
**Goal:** Giới thiệu 3 tính năng mới, hướng dẫn 1 hành động cụ thể để user thêm Life Event đầu tiên.

```
🎉 *Bé Tiền vừa hiểu cuộc đời bạn hơn một chút!*

Hôm nay có 3 điều mới — mình giới thiệu từng cái:

---

🗓 *Life Event Simulator — Cột mốc cuộc đời vào trong Twin*

Bấm menu → *🔮 Bé Tiền tương lai* → *Thêm cột mốc* để khai báo:
• 🏠 Mua nhà / mua xe
• 💍 Kết hôn
• 👶 Có con
• 🎓 Học phí đại học cho con
• 🌴 Nghỉ hưu sớm

Ngay khi bạn thêm vào, Twin sẽ tính lại cone — cho bạn thấy
_cột mốc này sẽ ảnh hưởng thế nào đến tài sản 5 và 10 năm tới_.

Bé Tiền không khuyên bạn nên hay không nên làm gì —
chỉ là công cụ để bạn thấy rõ hơn, quyết định tốt hơn 💚

---

📊 *Cashflow Forecast — Dự báo 3 tháng tới*

Bé Tiền đã phân tích lịch sử giao dịch của bạn và tự phát hiện
các khoản định kỳ (tiền nhà, điện, nước, subscription...).

Bấm menu → *💰 Dòng tiền* → *Dự báo 3 tháng* để xem:
• Tháng nào chi nhiều hơn bình thường
• Tháng nào có nguy cơ âm tài khoản (mình sẽ nhắc sớm trước 3 ngày)

Xác nhận hoặc chỉnh lại các khoản Bé Tiền đề xuất — khoản nào chưa xác nhận
thì không được đưa vào dự báo.

---

📱 *Kết nối Zalo*

Muốn nhận thông báo qua Zalo? Bấm menu → *⚙️ Cài đặt* → *Kết nối Zalo*.
Mình sẽ gửi link xác thực, bạn chỉ cần bấm xác nhận 1 lần.

Sau đó, cảnh báo cashflow và briefing sáng sẽ đến trên cả Telegram lẫn Zalo —
tuỳ bạn đang mở cái nào.

---

⚠️ *Nhắc nhẹ:*
Tất cả dự phóng là _ước tính dựa trên dữ liệu hiện tại_ —
tương lai thật sự còn phụ thuộc vào quyết định của bạn và thị trường.
Bé Tiền giúp bạn thấy hình thù, không đảm bảo con số.

Thêm cột mốc đầu tiên nhé: /menu → 🔮 💚
```

---

## Message 3 — Follow-up nudge (7 ngày sau launch)

**ID:** `followup`
**When:** +7 ngày. Bỏ qua user đã thêm ít nhất 1 Life Event sau launch date.
**Goal:** Kéo user chưa thử Life Events — đây là tính năng tạo attachment cao nhất vì gắn với kế hoạch cá nhân.

```
👋 *Bạn đã vẽ tương lai của mình vào Twin chưa?*

Tuần trước mình thêm tính năng *Life Event Simulator* —
cột mốc cuộc đời (mua nhà, có con, kết hôn...) vào thẳng trong dự phóng tài sản.

Mình thấy bạn chưa thử, nhắc nhẹ thôi 😊

*Chỉ mất 1 phút:*

📲 /menu → *🔮 Bé Tiền tương lai* → *Thêm cột mốc*

Chọn 1 cột mốc bạn đang nghĩ đến (không cần chắc chắn —
bạn có thể chỉnh hoặc xoá bất cứ lúc nào).

Ngay lập tức, Bé Tiền sẽ vẽ lại cone và cho bạn thấy:
_"Nếu điều này xảy ra năm đó, tài sản 2031/2036 của bạn trông thế này."_

Không phán xét. Không hối thúc. Chỉ là để bạn thấy rõ hơn 💚

/menu → 🔮
```

---

## Broadcast tool

**Script:** `scripts/broadcast_announcement.py`

### Cách dùng cho Phase 4B

```bash
# Bước 1 — Preview nội dung trước khi gửi (LUÔN LÀM TRƯỚC)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4B/phase-4B-deploy-announcements.md \
    --message teaser --dry-run

# Bước 2 — Test trên Telegram ID của chính mình
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4B/phase-4B-deploy-announcements.md \
    --message teaser --only <YOUR_TELEGRAM_ID>

# Bước 3 — Gửi teaser (~24h trước deploy, tối 19-21h)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4B/phase-4B-deploy-announcements.md \
    --message teaser

# Bước 4 — Gửi launch (trong vòng 1h sau deploy + smoke test pass)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4B/phase-4B-deploy-announcements.md \
    --message launch

# Bước 5 — Gửi follow-up sau 7 ngày, chỉ cho user chưa thêm Life Event
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4B/phase-4B-deploy-announcements.md \
    --message followup --skip-engaged --launch-date 2026-XX-XX
```

> **Lưu ý:** Luôn truyền `--file docs/current/phase-4B/phase-4B-deploy-announcements.md`
> để tránh script đọc nhầm file phase cũ.

### `--skip-engaged` hoạt động thế nào (Phase 4B)

"Engaged" với Phase 4B được định nghĩa là user đã **thêm ít nhất 1 Life Event** sau `--launch-date`. Cách kiểm tra:

```sql
SELECT DISTINCT user_id FROM life_events
WHERE created_at >= :launch_date
  AND deleted_at IS NULL;
```

Fallback nếu bảng `life_events` chưa có dữ liệu đủ: dùng `cashflow_forecasts` (user đã xem forecast):

```sql
SELECT DISTINCT user_id FROM cashflow_forecasts
WHERE computed_at >= :launch_date;
```

Extend `_engaged_user_ids()` trong `scripts/broadcast_announcement.py` để chạy query trên.

### Options (toàn bộ flag)

| Flag | Mục đích |
|---|---|
| `--message <id>` | Bắt buộc. Một trong: `teaser`, `launch`, `followup`. |
| `--file <path>` | Bắt buộc. Trỏ tới file này. |
| `--dry-run` | Preview + list recipients, không gửi thật. |
| `--only <telegram_id>` | Gửi cho 1 user (để test). |
| `--skip-engaged` | Cho `followup`: bỏ qua user đã thêm Life Event sau launch date. |
| `--launch-date YYYY-MM-DD` | Ngày deploy thật, dùng với `--skip-engaged`. |
| `--throttle-ms <n>` | Delay giữa các lần gửi (default 50ms). Tăng lên 200+ nếu > 1k users. |
| `--yes` | Bỏ qua prompt xác nhận (dùng trong CI / scripted). |

### Safety checklist (làm theo thứ tự)

- [ ] **Đọc to message** — nếu cứng hoặc máy móc thì viết lại.
- [ ] **Kiểm tra Markdown render** (dấu `*` balanced, không có `_` thừa, không có `*` lẻ trong từ).
- [ ] **Verify feature đã ship thật:**
  - Life Events: `/menu → 🔮 → Thêm cột mốc` responsive, cone tính lại trong < 3s.
  - Cashflow Forecast: cron đã chạy ít nhất 1 lần, `/menu → 💰 → Dự báo 3 tháng` hiển thị dữ liệu.
  - Zalo: link token endpoint live, OA webhook registered, test send từ ZaloNotifier sandbox.
- [ ] **Test với `--only <your_telegram_id>`** — đọc message như user thật.
- [ ] **Chạy `--dry-run`** để confirm số lượng recipients trước khi gửi thật.
- [ ] **Verify launch date** trước khi dùng `--skip-engaged`.
- [ ] **Gửi thật** — đứng cạnh laptop 15 phút đầu để theo dõi log lỗi.
- [ ] **Monitor logs** sau khi gửi — nếu Telegram trả 429 / 403 nhiều → tăng `--throttle-ms`.

---

## Timeline gợi ý

| Thời điểm | Action | Lưu ý |
|---|---|---|
| **T-1 ngày, 19h-21h** | Gửi `teaser` | Cao điểm read rate buổi tối |
| **T-day, sau deploy + smoke test pass** | Gửi `launch` | Trong vòng 1h sau deploy. KHÔNG gửi trước khi xác nhận: Life Events endpoint live, cashflow forecast cron đã chạy thử, Zalo link flow accessible |
| **T+1 ngày, sáng 9-10h** | Verify metrics | Đếm bao nhiêu user đã thêm Life Event lần đầu. Mục tiêu: ≥ 30% active users trong 24h |
| **T+7 ngày, 19-21h** | Gửi `followup` với `--skip-engaged --launch-date <T>` | Mục tiêu: kéo thêm 20% user chưa thử Life Events |
| **T+14 ngày** | Retrospective | Sign off Phase 4B nếu KPIs đạt (xem detailed.md § Definition of Done) |

---

## Notes for operator

- **Phase 4B khác 4A ở điểm:** 4A là passive (Twin tự tính, user chỉ xem). 4B yêu cầu **user action để có giá trị** (phải thêm Life Event mới thấy cone thay đổi). Vì thế `followup` quan trọng hơn và message cần thuyết phục hơn.
- **Life Events tone:** Tuyệt đối KHÔNG dùng các cụm từ như "bạn có đủ khả năng mua nhà chưa", "bạn nên đợi thêm vài năm để có con", "kết hôn có thể ảnh hưởng tới tài chính của bạn". Life Events là công cụ nhìn rõ, không phải công cụ tư vấn khi nào nên làm.
- **Probability framing:** Ba message đều phải có ít nhất một câu thừa nhận giới hạn. Đừng bỏ những câu này khi edit copy.
- **Zalo announcement:** Không cần riêng 1 message campaign — đã gộp vào launch message. Zalo là kênh thứ hai, không phải hero feature.
- **Vietnamese cultural fit:** Life Events rất personal — tránh bất kỳ ngôn ngữ nào nghe có vẻ đang "chấm điểm" hoặc so sánh với người khác.
- **Cashflow alert opt-out:** Khi user nhận alert `sắp âm tài khoản`, message phải rõ ràng là dự báo có thể sai và có link để tắt alert nếu muốn.
