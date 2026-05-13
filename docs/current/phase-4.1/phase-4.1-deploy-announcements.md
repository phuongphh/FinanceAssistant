# Phase 4.1 — Deploy Announcements

> File này chứa toàn bộ communication artifact cho 50-user soft launch tháng 6/2026:
> - Operator-facing: deploy checklist, dry-run preview, daily check-in template
> - User-facing: teaser, launch day welcome, follow-up day 7
> - Distribution: 50 invite link assignment plan

Mọi copy đã được tune cho tone Bé Tiền (ấm áp, không hype, không sales-y).

---

## 📅 Timeline tổng quan

```
T-3 days  │ Operator dry-run với 3 fake user; KPI digest verify 3 ngày liên tiếp staging
T-2 days  │ Sentry test exception; verify PII scrub
T-1 day   │ Generate 50 invite link; CSV export; ZALO_CHANNEL_ENABLED=false verify
T0        │ Launch day — distribute 5–10 invite/ngày, không cùng lúc
T+1 day   │ First KPI digest production; founding member sequence check
T+3 days  │ Operator review giữa cohort: onboarding completion rate, emoji signal trend
T+7 days  │ D7 retention checkpoint; gửi follow-up message; first feedback interview wave (3–5 user)
T+14 days │ D14 review; ship hotfix nếu có
T+30 days │ D30 review (link sang Phase 4.2 hoặc Phase 5.x kickoff)
```

**Nguyên tắc distribution:** 50 link không gửi 1 lượt. Distribute 3–5 ngày, 10–15 link/ngày. Lý do: operator support theo kịp + có signal sớm trước khi mở thêm.

---

## 🔧 OPERATOR-FACING

### Deploy Checklist (T-1 day)

Copy template này vào notebook và tick từng item trước khi distribute invite đầu tiên.

```markdown
## Bé Tiền Phase 4.1 — Pre-Launch Checklist

### Infrastructure
- [ ] Tất cả 4 migration applied trên production DB (`4.1.01` → `4.1.04`)
- [ ] `ENV.SENTRY_DSN` set, đã có 1 test exception capture được
- [ ] `ENV.OPERATOR_TELEGRAM_ID` set đúng user_id của founder
- [ ] `ENV.ZALO_CHANNEL_ENABLED=false` — verified 2 lần (grep code + check deploy config)
- [ ] `ENV.ONBOARDING_V2_ENABLED=true`
- [ ] `ENV.USD_VND_RATE` set (current ~25000)
- [ ] PostgreSQL backup automation chạy mỗi 6 giờ
- [ ] Sentry alert routing đến Telegram operator (không chỉ email)

### Cron / Workers
- [ ] `daily_kpi_digest_worker` cron đăng ký 8:00 ICT
- [ ] `feedback_sla_worker` cron đăng ký mỗi giờ
- [ ] `onboarding_resume_worker` cron đăng ký mỗi 5 phút
- [ ] `twin_calibration_worker` cron đăng ký daily 0:00 ICT
- [ ] `cost_budget_worker` lifecycle test (mock budget exceed → user nhận message)

### Content
- [ ] `vi-localization-checker` pass — không hardcoded Vietnamese string
- [ ] Tất cả file `content/*.yaml` đã load được, không syntax error
- [ ] 5 source variant trong `welcome_v2.yaml` đã test với 5 invite test
- [ ] `founding_welcome.yaml` test với 3 sequence value (#1, #25, #50)

### Smoke Tests
- [ ] E2E test clean account → `/start` → goal question → first asset → Twin → < 5 phút
- [ ] E2E test demo mode: skip Step 2 → demo banner rõ ràng → "Xem Twin của tôi" → quay lại Step 2
- [ ] E2E test resume: drop ở step 2 → đợi 10 phút → nhận đúng 1 nudge
- [ ] E2E test in-onboarding feedback: bấm 😍 → lưu vào DB, ack message gửi
- [ ] E2E test first briefing: onboard hôm trước → 8h sáng nhận briefing với explainer + button
- [ ] E2E test feedback flow: user gửi `/feedback`, operator `/feedback_inbox`, reply with template, user nhận
- [ ] E2E test cost guardrail: mock spend > 80% cap → warning, > 100% → block với message ấm áp

### Operator Readiness
- [ ] Đọc `kill-criteria.md` 1 lần
- [ ] Đọc `success-metrics.md` 1 lần
- [ ] Đọc `founding-promise.md` 1 lần — hiểu commitment trước khi distribute invite
- [ ] Block 1h/ngày trong calendar T0–T+7 cho việc đọc KPI digest + reply feedback
- [ ] Có process backup nếu operator nghỉ (vd: ai cover feedback?)

### Distribution Package
- [ ] CSV với 50 invite link đã generate
- [ ] Assignment plan: mỗi link → ai gửi, channel nào (DM Telegram / FB / Zalo / email)
- [ ] Personal message template cho mỗi nhóm source (xem dưới)

✅ All checked → ready to distribute first 10 invite at T0.
```

---

### Distribution Plan — 50 Invite Allocation

Phân bổ 50 invite link để cân bằng giữa **diversity of source** và **operator support capacity**.

| Source | Số link | Distribution channel | Note |
|---|---|---|---|
| `friends` | 12 | Personal Telegram/Zalo DM | Người bạn thân, đồng nghiệp cũ. Cao tỷ lệ activate. |
| `personal_fb` | 8 | FB Messenger DM | Friend list cá nhân, không public post. |
| `vn_finance_community` | 15 | DM trong các group VN FIRE / đầu tư / quản lý tài chính cá nhân | Largest source — early adopter persona đúng nhất. |
| `tg_finance_groups` | 10 | DM trong Telegram crypto/finance groups VN | Tech-savvy, có thể là cohort WTP cao. |
| `direct_msg` | 5 | Operator outreach 1-1 đến mass affluent acquaintances | Quality cao, conversion cao. |

**Phasing distribution qua 5 ngày T0..T+4:**
- T0 (10 link): 5 `friends` + 5 `direct_msg` — kiểm soát được, ai feedback gửi liền operator
- T+1 (10 link): 5 `personal_fb` + 5 `vn_finance_community`
- T+2 (10 link): 10 `vn_finance_community`
- T+3 (10 link): 5 `tg_finance_groups` + 5 `friends` còn lại
- T+4 (10 link): 5 `tg_finance_groups` + 3 `personal_fb` + 2 `vn_finance_community`

Operator có thể **dừng distribution** giữa chừng nếu in-onboarding emoji 😕 > 30% trong cohort đã onboard — cứu trước khi mở thêm.

---

### Personal Message Template — Operator gửi cùng invite link

Đây là template **operator tự gửi** đi kèm invite link, KHÔNG phải bot auto-send.

#### Template cho `friends` (personal DM)

```
Hi [Tên],

Mình đang build một AI tài chính cá nhân tên Bé Tiền — kiểu Personal CFO cho người Việt. Đang mở soft launch với 50 người đầu tiên, mình muốn mời bạn thử.

Trong 5 phút bạn sẽ thấy "Twin tài chính" của mình — Bé Tiền dự phóng 3 con đường tương lai dựa trên tài sản hiện tại.

Đặc quyền Founding Member: dùng full miễn phí, khi Pro ra mắt được giảm 50% trọn đời.

Link: [INVITE_URL]

Mình thật sự cần feedback của bạn — không cần khen, cứ thẳng. Bạn dùng 5–10 phút rồi nhắn mình nhé.
```

#### Template cho `vn_finance_community` (FB/Zalo finance group)

```
Chào anh/chị,

Em đang soft launch một sản phẩm AI tài chính cá nhân tên Bé Tiền — Personal CFO cho người Việt mass affluent. Đang mở cho 50 Founding Member đầu tiên.

Khác với app tracker truyền thống, Bé Tiền tập trung vào:
• Briefing tổng tài sản 30 giây mỗi sáng
• Twin tài chính — dự phóng 3 con đường tương lai
• Trợ lý chat 1-1 hiểu tiếng Việt và mục tiêu của anh/chị

Founding Member dùng full miễn phí + giảm 50% trọn đời khi Pro ra mắt.

Link: [INVITE_URL]

Em rất mong nhận góp ý từ anh/chị. Cảm ơn anh/chị dành thời gian.
```

#### Template cho `tg_finance_groups` (Telegram crypto/finance)

```
Hey,

I'm building Bé Tiền — an AI Personal CFO for Vietnamese, currently soft launching with 50 founding users.

Different from Money Lover or similar trackers: focus on **total wealth orchestration** rather than expense logging.
• Daily 30-sec briefing on your total assets
• "Financial Twin" — 3-path future projection
• Chat assistant that speaks Vietnamese natively

Founding Member perk: free forever during this phase, 50% off lifetime when Pro launches.

[INVITE_URL]

Would love your raw feedback — not the polite kind. Thanks for trying it.
```

#### Template cho `personal_fb` / `direct_msg`

Adapt từ `friends` template — chỉ cần thay đổi opening để khớp với relationship.

---

### KPI Digest Format Spec (cho A.6 worker)

Đây là template message 8h sáng operator nhận. Worker `daily_kpi_digest_worker` phải tuân theo format này.

```
🌅 Bé Tiền KPI Digest — [Ngày DD/MM/YYYY]

💸 Cost (24h trước)
• Total: 12.500đ | DeepSeek: 8.200đ | Claude OCR: 3.100đ | Whisper: 1.200đ
• Top 5: u_a3f...(2.800đ) u_b1c...(1.900đ) u_d4e...(1.700đ) u_f5g...(1.500đ) u_h8i...(1.200đ)
• Chạm 80% cap hôm nay: 0 user
[🚨 nếu total > 200% avg 7d]

📊 Engagement
• DAU: 23 | WAU: 41 | MAU: 47
• Twin view 24h: 18 | Onboarding completed: 4
• In-onboarding emoji: 😍 3 | 🤔 1 | 😕 0

🎯 Quality
• Intent accuracy: 87% (12 confirmed, 2 clarified, 0 misexecuted của 14 calls)
• Twin within-band (90d horizon, cohort completed): 78% (7/9 founding member)

⚠️ Churn signals
• 2 user inactive 7+ ngày: u_c2d... (founding #12), u_e6f... (founding #28)

📝 Feedback queue
• 3 feedback chưa trả lời:
  - id_a3f (2h, founding) "Twin của em không hiện asset bất động sản..."
  - id_b1c (5h) "Em muốn share Twin lên Zalo được không?"
  - id_d4e (18h, ⚠️ sắp SLA) "Bé Tiền có thể tính thuế thu nhập không?"

✅ All workers green
```

**Edge cases:**
- Nếu 24h không có cost: ghi "Total: 0đ — không có LLM call"
- Nếu không có feedback chưa trả lời: ghi "Feedback inbox: empty ✨"
- Nếu có worker fail: thêm dòng "❌ Worker fail: [name] — xem Sentry"

---

### Daily Check-in Template (Operator + Dev, 15 phút mỗi sáng T0..T+7)

Đọc cùng nhau lúc 8:30 sáng sau khi KPI digest đến. Mục đích: align trên signal, không deep dive.

```markdown
## Bé Tiền Daily Check-in — [Ngày]

### 1. KPI digest review (5 phút)
- Cost gì bất thường? → ai check
- Active user trend? → so với hôm qua
- In-onboarding emoji distribution? → nếu 😕 nhiều → red flag

### 2. Feedback inbox (5 phút)
- Còn bao nhiêu chưa trả lời?
- Có cái nào sắp breach SLA?
- Pattern gì xuất hiện 2+ lần?

### 3. Action items (5 phút)
- Bug nào cần fix hôm nay?
- Feedback nào cần reply trong 4 tiếng tới?
- Có cần dừng distribution chưa?
```

---

## 👤 USER-FACING

Tất cả copy dưới đây phải dry-run qua operator account trước khi gửi production.

### Teaser (T-2 day, optional) — chỉ gửi cho `friends` cohort

Đây là teaser **trước khi gửi invite link**, dùng để gauge interest và set expectation. Không bắt buộc.

```
Hi [Tên],

Mình đang sắp launch một thứ mình build từ đầu năm — AI tài chính cá nhân cho người Việt. Trong 2 hôm nữa mình sẽ gửi bạn link thử với 50 người đầu tiên.

Nếu bạn có 5 phút tuần này, mình rất muốn bạn xem qua và cho mình feedback thẳng. Bạn OK không?
```

### Welcome message (sau khi user redeem invite — T0 onwards)

Đây là **bot auto-send** ngay sau khi user start với invite code. Copy nằm trong `welcome_v2.yaml`, có variant theo source.

#### Variant `friends` / `personal_fb`

```
🌱 Chào [tên user đã set trên Telegram]!

[{referrer_name}] giới thiệu bạn đến với Bé Tiền — cảm ơn bạn dành thời gian thử nhé.

Bé Tiền là Personal CFO cho người Việt — giúp bạn hiểu rõ tài sản, lên kế hoạch dài hạn, và theo dõi chi tiêu thông minh.

🌟 Bạn là Founding Member #[N] — 1 trong 50 người đầu tiên.
Trong giai đoạn này dùng full miễn phí. Khi Bé Tiền Pro ra mắt cuối 2026, bạn được giảm 50% trọn đời — 44.000đ/tháng thay vì 88.000đ.

Sẵn sàng bắt đầu hành trình chưa?

[🌱 Bắt đầu hành trình]
```

#### Variant `vn_finance_community` / `tg_finance_groups`

```
🌱 Chào bạn,

Cảm ơn bạn đến từ cộng đồng tài chính. Bé Tiền là Personal CFO cho người Việt mass affluent — tập trung vào tổng tài sản, dự phóng tương lai, và quyết định tài chính dài hạn (không chỉ là expense tracking).

3 thứ Bé Tiền làm khác:
• Briefing 30 giây tổng tài sản mỗi sáng 8h
• Twin tài chính — dự phóng 3 con đường tương lai
• Chat 1-1 hiểu tiếng Việt và mục tiêu của bạn

🌟 Bạn là Founding Member #[N] — 1 trong 50 người đầu tiên.
Dùng full miễn phí giai đoạn này. Khi Pro ra mắt cuối 2026, giảm 50% trọn đời (44.000đ/tháng thay vì 88.000đ).

Bắt đầu thôi nhé?

[🌱 Bắt đầu hành trình]
```

#### Variant `direct_msg`

```
🌱 Chào bạn,

Cảm ơn bạn đã trả lời tin nhắn của Bé Tiền. Bé Tiền là Personal CFO cho người Việt — giúp bạn hiểu rõ tài sản, kế hoạch dài hạn, và chi tiêu thông minh.

🌟 Bạn là Founding Member #[N] — 1 trong 50 người đầu tiên.
Dùng full miễn phí giai đoạn này. Khi Pro ra mắt, giảm 50% trọn đời.

Khám phá nhé!

[🌱 Bắt đầu hành trình]
```

---

### Step 1 — Goal Question (sau khi bấm "Bắt đầu hành trình")

```
(1/3) Để Bé Tiền hiểu bạn hơn — bạn muốn Bé Tiền giúp gì trước nhất?

[🌱 Hiểu rõ tổng tài sản của tôi]
[🎯 Lên kế hoạch cho mục tiêu lớn]
[📊 Theo dõi chi tiêu thông minh]
```

### Step 2 — First Asset

```
(2/3) Tốt rồi! Bây giờ để Bé Tiền vẽ Twin tài chính cho bạn, hãy cho biết tổng số tiền tiết kiệm + đầu tư hiện tại của bạn.

Bạn có thể nhập tự do, ví dụ "300 triệu" hoặc "1.5 tỷ" — Bé Tiền hiểu được.

Không nhớ chính xác? Bấm nút bên dưới để Bé Tiền dùng demo trước.

[🤖 Để Bé Tiền dùng demo trước]
```

#### Demo mode banner (khi skip)

```
📌 Demo Mode

Đây là Twin của một người giả định với 50 triệu tiết kiệm. Twin của bạn sẽ khác — nhập tài sản thật để xem Twin riêng của bạn.

(Twin demo dưới đây chỉ để bạn hình dung — không phải dự phóng cá nhân.)
```

Sau demo:

```
Bạn đã xem demo. Muốn xem Twin thật của chính mình không?

[💎 Xem Twin của tôi]
```

### Step 3 — Twin Reveal (3 message liên tiếp)

**Message 1 — Mascot narrative:**

```
(3/3) ✨

Đây là Twin tài chính của bạn — Bé Tiền vẽ ra 3 con đường tương lai dựa trên tình hình hiện tại.

• Đường giữa là điều kiện thường
• Đường trên là nếu bạn tiết kiệm chăm hơn
• Đường dưới là nếu có biến cố

Bạn không cần đoán tương lai — Bé Tiền đoán giúp, bạn chỉ cần quyết định.
```

**Message 2 — Cone chart image** (rendered, không text)

**Message 3 — In-moment feedback (sau 7s delay):**

```
💬 Bạn cảm thấy thế nào về Twin đầu tiên?

[😍] [🤔] [😕]
```

**Sau bấm feedback:**

```
Cảm ơn bạn — Bé Tiền ghi nhận để cải thiện.

Sáng mai 8h Bé Tiền sẽ gửi bạn briefing đầu tiên về tài sản của bạn — đợi nhé!

Có thể dùng /help bất cứ lúc nào để xem Bé Tiền làm được gì.
```

---

### Resume Nudge (worker `onboarding_resume_worker` gửi sau 10 phút stuck)

```
🌱 Bé Tiền đang chờ bạn ở bước [X] — chỉ cần thêm 1 thông tin là Twin sẵn sàng.

Tiếp tục nhé?

[▶️ Tiếp tục]  [🤖 Để Bé Tiền dùng demo trước]
```

Chỉ gửi **1 lần** vĩnh viễn per user. Không spam.

---

### First Morning Briefing (T+1 ngày sau onboarding, 8h sáng)

```
🌅 Chào buổi sáng [tên user]!

📍 Đây là briefing đầu tiên của bạn!

Mỗi sáng 8h Bé Tiền sẽ tổng hợp 3 thứ quan trọng nhất về tài sản của bạn trong 30 giây đọc.

Hôm nay Bé Tiền nói về:

1️⃣ Tổng tài sản hiện tại: [số liệu cá nhân]
2️⃣ Thay đổi vs hôm qua: [số liệu]
3️⃣ Điều Bé Tiền chú ý: [observation contextual]

[💡 Bé Tiền đang nói gì?]
```

**Bấm "Bé Tiền đang nói gì?":**

```
ℹ️ Giải thích nhanh:

• "Tổng tài sản" = tiền tiết kiệm + đầu tư + bất động sản (nếu đã nhập) trừ nợ
• "Thay đổi vs hôm qua" = tăng/giảm dựa trên giá thị trường hiện tại (chứng khoán, crypto, vàng)
• "Điều Bé Tiền chú ý" = thứ Bé Tiền nghĩ bạn nên biết — không phải lời khuyên đầu tư

Mỗi ngày 3 mục này có thể khác nhau tùy vào tài sản và mục tiêu của bạn.

Bấm /menu để xem thêm tính năng.
```

---

### Day 7 Follow-up (T+7 days, gửi cho user còn active)

```
🌱 Chào bạn,

Bé Tiền đã đồng hành cùng bạn được 7 ngày rồi — cảm ơn bạn đã thử.

Bé Tiền rất muốn hỏi bạn 1 câu nhanh:

Trong 7 ngày qua, **điều gì Bé Tiền giúp bạn được nhiều nhất** — và **điều gì còn thiếu**?

Bạn trả lời bằng /feedback hoặc nhắn tự do — Bé Tiền (= Founder thật) đọc từng câu.

Cảm ơn bạn lần nữa 🌱
```

**Cho user inactive 7+ ngày (gửi 1 lần, không tiếp tục push):**

```
🌱 Chào bạn,

Bé Tiền nhận ra bạn lâu chưa quay lại. Có thể bạn bận, có thể Bé Tiền chưa đủ giá trị — cả 2 đều OK.

Nếu bạn có 1 phút, Bé Tiền rất muốn nghe **lý do bạn không quay lại**. Câu trả lời thẳng giúp Bé Tiền cải thiện rất nhiều — bạn không cần ngại.

Reply tin này hoặc gửi /feedback, Bé Tiền sẽ đọc.

Cảm ơn bạn đã thử 🌱
```

---

### Cost Warning at 80% (gửi 1 lần/tháng khi chạm 80% cap)

```
🌱 Bé Tiền note nhanh cho bạn,

Bạn đang dùng Bé Tiền rất tích cực — đến 80% hạn mức tháng này (chuyện hiếm, mostly là dấu hiệu tốt!).

Trong 20% còn lại Bé Tiền vẫn phục vụ bình thường. Sang tháng sau hạn mức reset, dùng tiếp như bình thường.

Có gì cần nâng cao limit, gửi /feedback Bé Tiền xem qua.
```

### Cost Block at 100% (chạm 100% cap)

```
🌱 Bé Tiền tạm dừng tính năng [X] cho bạn tháng này — sang tháng mở lại nhé.

Trong khi đó các tính năng khác vẫn dùng bình thường. Có gì cần gấp dùng /feedback Bé Tiền xem qua.

(Đây là hạn mức để Bé Tiền không "đốt" tài nguyên — không phải bạn làm gì sai.)
```

---

## 🚨 Crisis Comms (nếu có incident)

### Template: Bug critical — user không onboard được

```
🌱 Bé Tiền gặp lỗi tạm thời với onboarding — đội đang fix.

Bạn vui lòng đợi 30 phút rồi thử lại /start. Nếu vẫn lỗi, reply tin này để Bé Tiền hỗ trợ trực tiếp.

Xin lỗi sự bất tiện.
```

### Template: Data incident (rất unlikely với phase này, nhưng có sẵn)

```
🚨 Bé Tiền cần báo bạn một việc quan trọng:

[Mô tả ngắn gọn, không tô vẽ — kiểu "do lỗi kỹ thuật, briefing sáng hôm [DATE] tính sai cho một số user"]

Tài sản thật của bạn không bị ảnh hưởng — đây chỉ là số trong briefing bị tính sai. Bé Tiền đã fix lúc [TIME] và đang gửi briefing lại cho user bị ảnh hưởng.

Nếu bạn có câu hỏi, reply tin này — Bé Tiền trả lời trong 2 tiếng.

Xin lỗi bạn vì sự cố.
```

---

## 📝 Internal Notes

- **Tone discipline:** Bé Tiền KHÔNG bao giờ dùng "khách hàng" — luôn "bạn". KHÔNG dùng "trải nghiệm" — dùng "hành trình" / "dùng" / "thử". KHÔNG dùng emoji bắn pháo 🎉 — dùng 🌱 (đặc trưng Bé Tiền).
- **Không hype:** đừng viết "đẳng cấp", "siêu", "tốt nhất". Viết bình thường.
- **Founding member promise** là cam kết thật. Mỗi message gửi đến founding member phải nhất quán về promise.
- **Mọi copy mới phải review qua `vi-localization-checker` agent** trước khi merge.

---

## ✅ Distribution Day-of Checklist

Trước khi gửi mỗi batch invite (T0, T+1, ... T+4):

```markdown
- [ ] Cohort hôm nay đã online check (Telegram active, không phải đêm khuya)
- [ ] Personal message template đã customize tên người nhận
- [ ] Invite URL đã verify hoạt động (click thử 1 link)
- [ ] Operator có rảnh tối thiểu 2h sau gửi để reply ngay nếu có feedback nhanh
- [ ] In-onboarding emoji metric từ batch trước < 30% 😕 (nếu trên ngưỡng → pause distribution, fix trước)
```

---

## 📊 Post-Launch Review Template (T+7, T+14, T+30)

```markdown
## Bé Tiền Soft Launch — Review [T+N days]

### Numbers
- Active users: [N] / 50
- Onboarding completion rate: [%]
- Twin view in session 1: [%]
- D[N] retention: [%]
- In-onboarding emoji: 😍 [%] / 🤔 [%] / 😕 [%]
- Avg cost/user/30d: [VND]
- Feedback received: [N] | SLA respected: [%]

### Top 3 Patterns
1.
2.
3.

### Top 3 Bugs
1.
2.
3.

### Top 3 Feature Requests
1.
2.
3.

### Kill Criteria Status
- [ ] 4-week retention threshold (waiting...)
- [ ] Cost per user threshold (current: X)
- [ ] Critical bug rate (current: X)
- [ ] Persona violation (current: X)
- [ ] Emoji 😕 distribution (current: X%)

### Decision
[Continue / Hotfix / Pause / Pivot]
```
