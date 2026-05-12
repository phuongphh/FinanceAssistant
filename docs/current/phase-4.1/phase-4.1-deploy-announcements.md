# Phase 4.1 — Deploy Announcement Templates

> **Phase:** 4.1 — Pre-Launch Hardening (Bé Tiền chuẩn bị mở cửa cho 50 user đầu tiên — tháng 6/2026).
> **Reference:** [`phase-4.1-detailed.md`](./phase-4.1-detailed.md)
> **Status:** Reference copy — operator broadcasts via `scripts/broadcast_announcement.py` (xem § Broadcast tool).

Phase 4.1 khác Phase 4A: 4A là **wow-feature** (Twin) cần fanfare; 4.1 là **hardening** — chủ yếu cho user hiện có biết "Bé Tiền giờ ổn hơn, mời bạn vào cohort soft launch nếu bạn quan tâm".

Đây là **3-message campaign**, target khác nhau:
- **Teaser** — cho user hiện có (đã từ Phase 4A): "có thay đổi nhẹ, mời bạn dogfood thêm".
- **Soft launch invite** — cho 50 user mới qua invite link.
- **Week-1 check-in** — cho 50 cohort sau 7 ngày, hỏi feedback và nhắc Twin.

Tone theo [`tone_guide.md`](../tone_guide.md): "mình" / "bạn", ấm áp, **không bán hàng** — soft launch là privilege, không phải promo.

---

## Message 1 — Pre-deploy teaser cho user hiện có (1 ngày trước deploy)

**ID:** `teaser`
**When:** ~24h trước deploy, buổi tối 19h–21h.
**Audience:** User hiện có (đã onboard từ Phase 3A/4A).
**Goal:** Heads-up về changes nhỏ + đặt expectation "soon có thêm bạn mới vào".

```
💚 *Bé Tiền cập nhật nhẹ ngày mai...*

Tháng vừa rồi mình đã làm Twin (cone tương lai). Tháng này
mình tập trung vào *chất lượng*, không phải tính năng mới:

🌱 Onboarding mượt hơn cho bạn mới (bạn cũ không bị ảnh hưởng).
🛡 Bé Tiền sẽ *trung thực hơn* — sẽ cho bạn thấy
   "mình đoán đúng bao nhiêu lần" trong Twin view.
📸 Bạn có thể lưu Twin của mình thành ảnh kỷ niệm
   (không hiện số tiền — chỉ cone dáng).

Và một điều mình muốn chia sẻ:
*Tháng 6, mình sẽ mời 50 người bạn vào dùng Bé Tiền cùng bạn.*
Bạn đã đồng hành sớm — mình muốn cảm ơn bằng một lá thư
ngắn sau khi tháng 6 kết thúc 🌿

Không có gì phải làm cả. Cứ tiếp tục dùng Bé Tiền như bình thường nhé.
```

---

## Message 2 — Soft launch invite cho 50 user mới

**ID:** `launch`
**When:** Ngay sau khi deploy pass smoke test (TC-027 e2e pass). Operator distribute invite link qua kênh personal (FB DM, finance community, etc.).
**Audience:** 50 user mới, mỗi người 1 invite token unique.
**Goal:** Cá nhân hoá invitation, set expectation đúng — đây không phải app retail, đây là dogfood cohort.

```
👋 Chào bạn,

Mình là người đang xây *Bé Tiền* — một Personal CFO assistant
cho người Việt, qua Telegram.

Bé Tiền không phải app trading, cũng không phải app chi tiêu.
Bé Tiền giúp bạn:

💼 *Theo dõi tài sản* (cổ phiếu, crypto, vàng, BĐS)
   — tự động cập nhật giá thị trường.
🔮 *Nhìn dự phóng tài sản 5-10 năm sau* (Monte Carlo
   trên chính danh mục của bạn, không phải con số đoán mò).
☀️ *Briefing buổi sáng* về portfolio + thị trường.
💚 Persona ấm áp — không phán xét, không thúc giục.

*Vì sao mình mời bạn?*
Mình đang mở cohort 50 user đầu tiên — *bạn là 1 trong 50*.
Mục đích: học từ cách bạn dùng thật. Đổi lại bạn được:

✨ Truy cập sớm, miễn phí toàn bộ.
✨ Đường dây trực tiếp với mình — gửi `/feedback` là mình đọc + trả lời trong 24h.
✨ Tham gia quyết định feature nào ship tiếp theo.

*Cách bắt đầu (90 giây):*
👉 Bấm link: t.me/BeTienBot?start=invite_{{TOKEN}}

Link này là *của riêng bạn* — đừng share, vì cohort giới hạn 50 chỗ.

Nếu bạn không quan tâm, không sao cả — chỉ cần bỏ qua tin này 🌿
Nếu có hứng thú, mình rất mong gặp bạn bên trong.

Cảm ơn bạn 💚
```

---

## Message 3 — Week-1 check-in cho 50 cohort (T+7 ngày)

**ID:** `followup`
**When:** +7 ngày sau invite. Bỏ qua user chưa active (chưa qua onboarding) — họ cần message khác.
**Audience:** 50 cohort đã onboard.
**Goal:** Thu feedback chất lượng cao + nhắc nhẹ user chưa thử Twin / chưa log asset thật.

```
👋 *Đã 1 tuần rồi — cảm ơn bạn đã đồng hành!*

Mình chỉ muốn ghé qua nhẹ nhàng, không spam đâu 😊

*Một câu hỏi nhỏ:* nếu bạn có 30 giây,
gõ `/feedback` và viết cho mình *bất cứ điều gì*:
- Tính năng bạn thấy hay nhất tuần này.
- Cái gì làm bạn khó chịu / lú lẫn / chán.
- Tính năng nào bạn ước có nhưng chưa thấy.

Mình đọc *từng feedback*, trong 24h. Không phải AI — là mình thật.

---

*Và một nhắc nhỏ nếu bạn chưa thử:*

🔮 *Bé Tiền tương lai* — gõ /menu → 🔮
Đây là feature mình tự hào nhất — nhưng chỉ work nếu bạn đã thêm tài sản thật.
Nếu mới chỉ có demo asset, hãy thêm 1-2 thứ thật (cổ phiếu, crypto, tiền gửi).

Cảm ơn vì bạn ở đây từ ngày đầu 💚
```

---

## Broadcast tool

**Script:** `scripts/broadcast_announcement.py`

One-click broadcast. Operator chọn message bằng `--message <id>`, script đọc nội dung từ file này, liệt kê recipients, hỏi xác nhận, rồi gửi có throttling.

### Cách dùng cho Phase 4.1

```bash
# Bước 1 — Preview (LUÔN LÀM TRƯỚC)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4.1/phase-4.1-deploy-announcements.md \
    --message teaser --dry-run

# Bước 2 — Test trên Telegram ID của chính mình
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4.1/phase-4.1-deploy-announcements.md \
    --message teaser --only <YOUR_TELEGRAM_ID>

# Bước 3 — Gửi teaser cho user hiện có (~24h trước deploy)
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4.1/phase-4.1-deploy-announcements.md \
    --message teaser --audience existing_users

# Bước 4 — Soft launch invite KHÔNG dùng broadcast tool
# (Vì mỗi user 1 token unique → distribute manual qua FB DM / community)
python scripts/soft_launch_acquisition.py generate \
    --source vn_finance_community --count 25
python scripts/soft_launch_acquisition.py generate \
    --source friends --count 25
# → Export CSV, operator paste từng link vào DM bằng tay.

# Bước 5 — Week-1 followup cho cohort soft launch
python scripts/broadcast_announcement.py \
    --file docs/current/phase-4.1/phase-4.1-deploy-announcements.md \
    --message followup --audience soft_launch_cohort \
    --launch-date 2026-06-01
```

> **Lưu ý quan trọng:** Phase 4.1 có 2 audience khác nhau:
> - `existing_users` = user `created_at < phase_4_1_deploy_date`
> - `soft_launch_cohort` = user có `acquisition_source IN ('friends','personal_fb','vn_finance_community','direct_msg')`
>
> Broadcast script cần support `--audience <key>` flag để phân tách.

### `--audience` filter (Phase 4.1)

Extend `_recipient_user_ids()` trong `scripts/broadcast_announcement.py`:

```sql
-- existing_users
SELECT id FROM users WHERE created_at < :phase_4_1_deploy_date
  AND is_active = TRUE;

-- soft_launch_cohort
SELECT id FROM users
WHERE acquisition_source IN ('friends','personal_fb','vn_finance_community','direct_msg')
  AND created_at >= :launch_date
  AND is_active = TRUE;
```

### Options (toàn bộ flag)

| Flag | Mục đích |
|---|---|
| `--message <id>` | Bắt buộc. Một trong: `teaser`, `launch` (không dùng cho 4.1), `followup`. |
| `--file <path>` | Bắt buộc cho 4.1. Trỏ tới file này. |
| `--audience <key>` | Bắt buộc cho 4.1. `existing_users` hoặc `soft_launch_cohort`. |
| `--dry-run` | Preview + list recipients, không gửi. |
| `--only <telegram_id>` | Gửi cho 1 user (để test). |
| `--launch-date YYYY-MM-DD` | Cohort filter date (dùng với `soft_launch_cohort`). |
| `--throttle-ms <n>` | Delay giữa các lần gửi (default 50ms). |
| `--yes` | Bỏ qua prompt xác nhận (CI / scripted). |

### Safety checklist (làm theo thứ tự)

- [ ] **Đọc to message** — nếu cứng hoặc máy móc thì viết lại.
- [ ] **Kiểm tra Markdown render** (dấu `*` balanced, không có `_` thừa).
- [ ] **Verify Phase 4.1 đã ship** — Sentry live, cost guardrail enforced, KPI digest chạy ít nhất 1 lần.
- [ ] **Test với `--only <your_telegram_id>`** — đọc message như user thật.
- [ ] **Chạy `--dry-run`** confirm số recipients trước khi gửi thật.
- [ ] **Confirm audience filter** — KHÔNG gửi teaser cho cohort soft launch (vì họ chưa onboard).
- [ ] **Soft launch invite distribute thủ công** — KHÔNG broadcast (mỗi token 1 người).
- [ ] **Gửi thật** — đứng cạnh laptop 15 phút đầu để theo dõi log.
- [ ] **Monitor Sentry** sau khi gửi — error rate có spike không.

---

## Timeline gợi ý

| Thời điểm | Action | Lưu ý |
|---|---|---|
| **T-2 ngày** | Sign-off test cases, change marker `signed` | Trigger archive workflow chuẩn bị |
| **T-1 ngày, 19h-21h** | Gửi `teaser` cho `existing_users` | Heads-up cho user cũ |
| **T-day, sáng** | Deploy 4.1, run smoke test TC-027 + TC-028 | KHÔNG distribute invite trước khi smoke pass |
| **T-day, chiều** | Generate 50 invite link, distribute thủ công | Operator paste vào FB DM / community DM |
| **T+1 → T+7** | Đọc KPI digest mỗi sáng, reply feedback < 24h | Cohort còn nhỏ → personal touch |
| **T+7, 19-21h** | Gửi `followup` cho `soft_launch_cohort` | Mục tiêu: 60%+ phản hồi feedback / mở Twin |
| **T+14** | Mid-cohort review | Đo metric theo `success-metrics.md` |
| **T+28** | Sign off Phase 4.1 nếu KPIs đạt (xem detailed.md § DoD) | Kiểm checkpoint theo `kill-criteria.md` |

---

## Notes for operator

- **Phase 4.1 khác Phase 4A ở điểm:** 4A là **new surface** (Twin) cần fanfare; 4.1 là **hardening** chủ yếu invisible. Vì thế teaser ngắn hơn, không "wow" — và sức nặng campaign nằm ở **soft launch invite cá nhân hoá**, không phải broadcast.
- **Soft launch invite KHÔNG broadcast.** Mỗi link có token riêng, distribute qua DM cá nhân. Đây là intentional — soft launch privilege phải feel personal, không feel spam.
- **Trust framing:** Followup message thẳng thắn nói "không phải AI — là mình thật" để user feel direct line với operator. Đây là moat của soft launch — đừng outsource đoạn này.
- **Vietnamese cultural fit:** KHÔNG có CTA "share Bé Tiền với bạn bè" / "khoe Twin lên FB". Mass affluent VN "kín tiếng về tiền" — soft launch lan toả qua mời tay, không qua viral.
- **Đo cohort acquisition source:** Trước khi gửi followup, query `/cohort_stats` để biết kênh nào hiệu quả nhất → guide cho Phase 5 (Zalo) khi quyết định kênh acquisition.
- **Backup plan:** Nếu T+7 cohort engagement < 40%, KHÔNG send `followup` trước khi audit lý do. Có thể là onboarding fail, có thể là invite thô — fix root cause trước khi nhắc nhở thêm.
