# Phase 4A — Deploy Announcement Templates

> **Phase:** 4A — Financial Twin Conservative MVP (Bé Tiền tương lai: dự phóng tài sản 5/10 năm với probability cones P10/P50/P90).
> **Reference:** [phase-4A-detailed.md](./phase-4A/phase-4A-detailed.md)
> **Status:** Reference copy — operator broadcasts via `scripts/broadcast_announcement.py` (see § Broadcast tool below).

Phase 4A là **wow-feature đầu tiên**: chuyển từ "tracking quá khứ" sang "nhìn thấy tương lai tài chính". Bé Tiền của bạn năm 2031/2036 trông như thế nào? Câu trả lời không phải 1 con số đoán mò — mà là một **dải xác suất** (cone) tính bằng Monte Carlo từ chính danh mục thật của bạn.

Đây là **3-message campaign**: teaser trước deploy, launch ngay sau khi lên, và follow-up cho user chưa thử Twin sau 1 tuần.

Tone theo [tone_guide.md](./tone_guide.md): "mình" / "bạn", ấm áp, **probability over precision** — không bao giờ hứa con số chắc chắn.

---

## Message 1 — Pre-deploy teaser (1 ngày trước deploy)

**ID:** `teaser`
**When:** ~24h trước deploy, buổi tối 19h–21h.
**Goal:** Gây tò mò về Twin, đặt tâm lý "đây là tính năng khác biệt".

```
🔮 *Sắp có điều mình đợi rất lâu để gửi bạn...*

Từ ngày mai, Bé Tiền sẽ làm được một việc mới:

*Cho bạn nhìn thấy tương lai tài chính của mình* —
không phải đoán mò, không phải một con số khô khan,
mà là *dải khả năng* dựa trên chính danh mục thật của bạn.

🌱 Bé Tiền của bạn năm *2031* trông thế nào?
🚀 Năm *2036*?
✨ Nếu tiết kiệm thêm 10% — có khác biệt bao nhiêu?

Mình không hứa con số chắc chắn (vì không ai biết tương lai 😊),
nhưng mình sẽ chỉ cho bạn _khoảng nào là khả thi_, dựa trên data thật.

Hẹn gặp bạn ngày mai để mở Twin đầu tiên 💚
```

---

## Message 2 — Launch announcement (trong vòng 1h sau deploy)

**ID:** `launch`
**When:** Ngay sau khi deploy pass smoke test (Twin engine + weekly cron + Mini App URL live).
**Goal:** Hướng dẫn 1 hành động cụ thể để user mở Twin lần đầu.

```
🎉 *Bé Tiền tương lai đã sẵn sàng!*

Mở menu chính → bấm *🔮 Bé Tiền tương lai* để gặp chính bạn của 5 và 10 năm sau.

*Bạn sẽ thấy gì?*

📈 *Cone dự phóng tài sản*
Không phải 1 con số — mà 3 đường:
• Khoảng thận trọng (P10) — nếu mọi thứ không thuận lợi
• Khoảng khả thi nhất (P50) — kịch bản trung bình
• Khoảng tích cực (P90) — nếu thị trường ưu ái bạn

Tất cả tính từ Monte Carlo 1,000 kịch bản trên danh mục thật của bạn.

⚖️ *So sánh "nếu tốt hơn"*
Bấm "So sánh Optimal" — Bé Tiền chỉ ra:
nếu tăng tiết kiệm 10% + tái cân bằng danh mục theo level của bạn,
tương lai có thể tốt hơn bao nhiêu (cụ thể bằng tỷ VND).

📊 *Mini App Dashboard*
Bấm "Mở Twin Dashboard" — xem cone tương tác trên web view,
chuyển qua lại Current ↔ Optimal mượt mà.

🌅 *Buổi sáng*
Từ mai, briefing sáng sẽ có thêm 1 dòng:
"_Bạn đang on-track / ahead / sau P50 dự phóng_" — không phán xét,
chỉ là một chỉ báo để bạn biết mình đang đứng đâu trên lộ trình.

⚠️ *Một lời nhắc thật lòng:*
Đây là *dự phóng, không phải dự đoán*. Tương lai phụ thuộc vào
thị trường + quyết định của bạn. Bé Tiền giúp bạn thấy hình thù —
nhưng không ai (kể cả mình) đảm bảo con số.

Mở Twin lần đầu nhé: bấm /menu → 🔮 💚
```

---

## Message 3 — Follow-up nudge (7 ngày sau launch)

**ID:** `followup`
**When:** +7 ngày. Bỏ qua user đã mở Twin sau launch date.
**Goal:** Kéo user chưa thử — Twin là wow-factor, mất 90% giá trị nếu user không tự xem.

```
👋 *Bạn đã gặp Bé Tiền tương lai chưa?*

Tuần trước mình mở chức năng *Twin* — nhìn dự phóng tài sản 5/10 năm.
Mình thấy bạn chưa thử, nên nhắc nhẹ thôi 😊

*Chỉ mất 30 giây để xem:*

📲 Gõ /menu → bấm *🔮 Bé Tiền tương lai* → *Xem trajectory*

Bạn sẽ thấy một bức tranh đầy đủ:
• Tài sản hiện tại
• Cone tương lai từ Monte Carlo trên danh mục thật của bạn
• Khoảng khả thi nhất năm 2031 và 2036

*Tại sao đáng thử?*
Hầu hết app tài chính chỉ kể quá khứ. Twin là cái duy nhất
giúp bạn *nhìn về trước* — và quyết định hôm nay tốt hơn nhờ đó.

Mọi thứ tự động — không cần khai báo gì thêm. Danh mục bạn đang có
là đủ để Bé Tiền dựng cone.

Gặp Bé Tiền 2036 của bạn nhé 🌱
/menu → 🔮
```

---

## Broadcast tool

**Script:** `scripts/broadcast_announcement.py`

One-click broadcast. Operator chọn message bằng `--message <id>`, script đọc nội dung từ file này, liệt kê recipients, hỏi xác nhận, rồi gửi có throttling.

### Cách dùng cho Phase 4A

```bash
# Bước 1 — Preview nội dung trước khi gửi (LUÔN LÀM TRƯỚC)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4A-deploy-announcements.md \
    --message teaser --dry-run

# Bước 2 — Test trên Telegram ID của chính mình
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4A-deploy-announcements.md \
    --message teaser --only <YOUR_TELEGRAM_ID>

# Bước 3 — Gửi teaser (~24h trước deploy, tối 19-21h)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4A-deploy-announcements.md \
    --message teaser

# Bước 4 — Gửi launch (trong vòng 1h sau deploy + smoke test pass)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4A-deploy-announcements.md \
    --message launch

# Bước 5 — Gửi follow-up sau 7 ngày, chỉ cho user chưa thử Twin
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4A-deploy-announcements.md \
    --message followup --skip-engaged --launch-date 2026-07-25
```

> **Lưu ý quan trọng:** Script mặc định có thể đọc file phase trước. Với Phase 4A
> **luôn truyền `--file docs/current/phase-4A-deploy-announcements.md`**.

### `--skip-engaged` hoạt động thế nào (Phase 4A)

"Engaged" với Phase 4A nên được định nghĩa là user đã **mở Twin view ít nhất 1 lần** sau `--launch-date`. Cách kiểm tra:

1. Mỗi action `(twin, view_current)` / `(twin, compare_optimal)` / `(twin, open_miniapp)` được log vào `intent_logs` hoặc `bot_action_logs` (tuỳ codebase).
2. Extend `_engaged_user_ids()` trong `scripts/broadcast_announcement.py` để query:
   ```sql
   SELECT DISTINCT user_id FROM bot_action_logs
   WHERE action_group = 'twin'
     AND action_name IN ('view_current', 'compare_optimal', 'open_miniapp')
     AND created_at >= :launch_date;
   ```
3. Fallback: nếu chưa có log bảng đó, dùng query `SELECT DISTINCT user_id FROM twin_projections WHERE computed_at >= :launch_date` — yếu hơn (chỉ kiểm tra cron đã chạy chứ không xác định user có thật sự xem). Nên ưu tiên log thật.

### Options (toàn bộ flag)

| Flag | Mục đích |
|---|---|
| `--message <id>` | Bắt buộc. Một trong: `teaser`, `launch`, `followup`. |
| `--file <path>` | Bắt buộc cho 4A. Trỏ tới file này. |
| `--dry-run` | Preview + list recipients, không gửi thật. |
| `--only <telegram_id>` | Gửi cho 1 user (để test). |
| `--skip-engaged` | Cho `followup`: bỏ qua user đã mở Twin sau launch date. |
| `--launch-date YYYY-MM-DD` | Ngày deploy thật, dùng với `--skip-engaged`. |
| `--throttle-ms <n>` | Delay giữa các lần gửi (default 50ms). Tăng lên 200+ nếu > 1k users để tránh Telegram rate limit. |
| `--yes` | Bỏ qua prompt xác nhận (dùng trong CI / scripted). |

### Safety checklist (làm theo thứ tự)

- [ ] **Đọc to message** — nếu cứng hoặc máy móc thì viết lại.
- [ ] **Kiểm tra Markdown render** (dấu `*` balanced, không có `_` thừa, không có `*` lẻ trong từ).
- [ ] **Verify feature đã ship thật** — Twin engine live, weekly cron đã chạy ít nhất 1 lần, Mini App URL accessible.
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
| **T-day, sau deploy + smoke test pass** | Gửi `launch` | Trong vòng 1h sau deploy. KHÔNG gửi trước khi xác nhận: Twin engine live, weekly cron đã chạy thử cho user test, Mini App URL trả 200 |
| **T+1 ngày, sáng 9-10h** | Verify metrics | Đếm bao nhiêu user đã mở Twin lần đầu. Mục tiêu: ≥ 40% active users trong 24h |
| **T+7 ngày, 19-21h** | Gửi `followup` với `--skip-engaged --launch-date <T>` | Mục tiêu: kéo thêm 20-30% user chưa thử |
| **T+14 ngày** | Retrospective | Sign off Phase 4A nếu KPIs đạt (xem detailed.md § Definition of Done) |

---

## Notes for operator

- **Phase 4A khác Phase 3.9 ở điểm:** 3.9 là backend upgrade (mọi số tự cập nhật) — user không cần làm gì. 4A là **new surface** — user phải tự bấm vào "🔮 Bé Tiền tương lai" lần đầu. Vì thế `followup` quan trọng hơn nhiều.
- **Trust framing:** Ba message đều phải có ít nhất một câu thừa nhận giới hạn (`không hứa con số chắc chắn`, `dự phóng không phải dự đoán`). Nếu bạn edit copy, đừng bỏ những câu này — đó là moat của Twin.
- **Vietnamese cultural fit:** Mass affluent VN "kín tiếng về tiền" → Twin là tính năng *cá nhân*, không khuyến khích share ra ngoài (theo strategy V3). KHÔNG thêm CTA "khoe Twin của bạn" / "share lên FB".
- **Mini App URL:** Trước khi gửi `launch`, mở URL Mini App từ chính Telegram của bạn để xác nhận initData verify hoạt động + chart load < 3s trên 4G.
