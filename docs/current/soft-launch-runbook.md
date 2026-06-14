# Soft Launch Runbook — Tháng 6/2026 (50 Founding Members)

> **Mục đích:** một nơi duy nhất để chạy ngày launch. Gom checklist kỹ thuật,
> vận hành và **business / go-to-market** (seeding message, kênh, lịch phát
> invite). Tick trực tiếp trên file này.
>
> **Nguồn tổng hợp:** `phase-4.1/deploy-checklist.md`, `phase-4.1/success-metrics.md`,
> `phase-4.1/phase-4.1-detailed.md` (Epic C playbook), `founding-promise.md`,
> `phase-4.2.5/phase-4.2.5-detailed.md`, `phase-4.3/phase-4.3-deploy-announcement.md`.
>
> **Status code đến launch:** Phase 4.1 → 4.3 đã `done`. Phần còn lại là
> **verify + vận hành**, KHÔNG phải code feature mới.

---

## 0. Lưu ý positioning (đọc trước khi viết bất kỳ message nào)

- **KHÔNG** dùng "Personal CFO" / "CFO" trong bất kỳ text nào người dùng đọc
  (welcome, seeding post, announcement, share image). Dùng **"người đồng hành
  quản lý tài sản"** / **"trợ lý tài chính cá nhân"**.
- Persona **Bé Tiền**: ấm áp, đồng hành, không phán xét chi tiêu. Đọc to —
  nếu nghe sượng hoặc "robot", viết lại.
- ⚠️ **Cần verify:** spec cũ (`phase-4.1-detailed.md:466`) có copy welcome
  cho source `vn_finance_community` ghi *"Bé Tiền là Personal CFO..."* — phải
  kiểm tra `content/onboarding/welcome_v2.yaml` đã sửa thành "người đồng hành
  quản lý tài sản" chưa. (Xem mục 3.)

---

## 1. Kỹ thuật — Verify trên staging (T-7 → T-3)

- [ ] `alembic upgrade head` chạy sạch; xác nhận 4 migration Phase 4.1 có mặt
      (`user_cost_budgets`, `feedback_sla`, `twin_calibration`, `founding_member`)
- [ ] Spot-check bảng tồn tại: `invite_codes`, `onboarding_sessions`,
      `user_cost_budgets`, `twin_calibration_snapshots`
- [ ] Cost report + KPI digest 08:00 ICT chạy đủ **3 ngày liên tiếp** trên staging
- [ ] Sentry test exception xuất hiện kèm `user_id` hash + intent context;
      PII (số >6 chữ số, email, phone) bị scrub
- [ ] `vi-localization-checker` pass: không có string tiếng Việt hardcode;
      content YAML đủ 4 wealth level; persona Bé Tiền nhất quán

### Gate Zalo — CRITICAL (3 lớp phòng thủ)

- [ ] Code gate `if settings.zalo_channel_enabled:` quanh Zalo router, default `False`
- [ ] Prod `.env`: `ZALO_CHANNEL_ENABLED=false` (operator + dev xác nhận **cùng nhau**)
- [ ] `curl -sI https://<prod>/api/v1/zalo/webhook` → 404/405
- [ ] Log boot in đúng string `"Zalo channel disabled (ZALO_CHANNEL_ENABLED=false)..."`
- [ ] Zalo OA console: webhook URL để trống (belt + braces)

---

## 2. Vận hành & dogfood (T-3)

- [ ] **Operator tự dogfood toàn flow từ cả 5 source** (`friends`, `personal_fb`,
      `vn_finance_community`, `direct_msg`, `tg_finance_groups`):
      `/start` → goal → first asset → narrative → cone → nút 😍 → completion.
      **Đo time-to-first-Twin (<5 phút).**
- [ ] Briefing sáng hôm sau có explainer + nút "💡 Bé Tiền đang nói gì?"
- [ ] Demo mode: skip asset → banner "📌 Demo Mode..." → "Xem Twin của tôi" → quay lại asset entry
- [ ] Resume nudge: drop ở step 2, chờ 10 phút → nhận đúng **1 nudge** (không trùng)
- [ ] Operator gửi `/feedback` → `/feedback_inbox` thấy row có cờ 🌱 → reply bằng template
- [ ] Test SLA: để 1 feedback >24h → worker alert bắn **đúng 1 lần**
- [ ] **Xoá sạch test account** khỏi `invite_codes` + `users` để không chiếm seat founding

---

## 3. Content & localization cần verify

- [ ] `content/onboarding/welcome_v2.yaml`: copy source-aware đủ 5 variant; **không
      có "Personal CFO"** (xem mục 0)
- [ ] `content/onboarding/founding_welcome.yaml`: banner `#N` + 50% trọn đời + bản `cap_reached`
- [ ] Briefing #1 explainer string
- [ ] 5 template feedback triage: `thanks_logged`, `clarify_request`,
      `feature_acknowledged`, `bug_apology`, `not_supported_yet`

---

## 4. Founding member — model mới: token-free, source-tracked (T-3 → T-1)

> **Đổi từ "token một lần" → "first 50 onboard = Founding".** Không cần sinh
> 50 token nữa. Chỉ cần **5 link cố định** `t.me/BeTienBot?start=src_<source>`
> (1 link/kênh, dùng lại thoải mái). 50 suất được trao tự động cho 50 người
> onboard đầu tiên (advisory-lock race-safe, cap 50). `src_<source>` chỉ ghi
> attribution kênh vào `users.acquisition_source` cho `/cohort_stats`.

- [ ] Soạn sẵn 5 link kênh và dán vào đúng message ở mục 6.3:
      `src_friends`, `src_personal_fb`, `src_vn_finance_community`,
      `src_direct_msg`, `src_tg_finance_groups`
- [ ] Test onboard 1 account sạch qua `src_friends` → banner Founding Member
      `#1` + 50% trọn đời; DB set `users.founding_member_sequence`,
      `acquisition_source='friends'`
- [ ] **Race test:** onboard 5 account song song → sequence 1–5 distinct,
      không trùng/nhảy số (advisory lock `pg_advisory_xact_lock`)
- [ ] Verify cap: onboard người thứ 51 → vẫn vào được, KHÔNG nhận banner
      Founding (cohort đầy), vẫn lưu `acquisition_source` cho cohort tracking

> **Backward-compat (tuỳ chọn):** nếu cần phát link token một lần cho một đợt
> riêng, `scripts/soft_launch_acquisition.py --batch <name>` vẫn sinh
> `invite_codes` + CSV; link `invite_<token>` vẫn redeem được. CSV token là
> **nhạy cảm**, chuyển sang folder private, **KHÔNG commit vào git**.

---

## 5. T-0 (sáng launch)

- [ ] Lặp lại verify gate Zalo (mục 1) trên **production**
- [ ] KPI digest 08:00 ICT tới hộp operator
- [ ] Sentry test exception trên prod OK
- [ ] `git tag v4.1.0-soft-launch && git push --tags`
- [ ] Gửi announcement Phase 4.3 lúc **9–10h sáng VN** (sau briefing) — 3 biến thể
      sẵn trong `phase-4.3/phase-4.3-deploy-announcement.md`

---

## 6. 📣 BUSINESS / GO-TO-MARKET

### 6.1 Cam kết Founding Member (wording chuẩn — không tự chế thêm)

> 🌱 **Bạn là Founding Member #N của Bé Tiền** — 1 trong 50 người đầu tiên.
> Trong giai đoạn này toàn bộ tính năng **miễn phí**. Khi Bé Tiền Pro ra mắt
> chính thức (dự kiến cuối 2026), bạn được **giảm 50% trọn đời** —
> 44.000đ/tháng thay vì 88.000đ — để cảm ơn sự đồng hành.

**Quy tắc:** chỉ hứa đúng điều này. Không hứa quà/bonus khác trừ khi document
trong `founding-promise.md`. (Chi tiết & corner case: xem `founding-promise.md`.)

### 6.2 Phân bổ 50 seat theo source & cadence phát invite

| Source | Seat | Kênh thực tế | Tone |
|---|---|---|---|
| `friends` | 10 | Nhắn tay bạn bè thân | Ấm, cá nhân |
| `personal_fb` | 10 | Post Facebook cá nhân | Ấm, kể chuyện |
| `vn_finance_community` | 10 | Group/cộng đồng tài chính VN | Chuyên nghiệp, không khoe |
| `direct_msg` | 10 | DM người đã quan tâm trước đó | Cá nhân, follow-up |
| `tg_finance_groups` | 10 | Group Telegram tài chính | Ngắn, đúng trọng tâm |

**Cadence (tránh dồn 50 người vào cùng lúc, để kịp triage):** vì link
`src_<source>` dùng lại được, điều tiết bằng **thời điểm đăng/nhắn từng kênh**
(stagger), không phải bằng số token phát ra. Gợi ý rải theo nhịp ~15 / 15 / 10 /
10 người qua 2 ngày — group post (kênh C, E) đăng sau cùng vì khó kiểm soát lượt.

### 6.3 Seeding messages (operator copy-paste — KHÔNG phải in-app string)

> Tất cả đều warm, không hype, không "CFO". Mỗi kênh dùng **một link cố
> định kèm đúng source** (không phải token một lần):
> `t.me/BeTienBot?start=src_<source>` —
> ví dụ `src_friends`, `src_personal_fb`, `src_vn_finance_community`,
> `src_direct_msg`, `src_tg_finance_groups`.
>
> Link `src_<source>` **không giới hạn lượt dùng**: dán nguyên một link vào
> group cũng được, nhiều người cùng bấm vẫn nhận đúng attribution kênh để
> `/cohort_stats` đo sạch. **50 suất Founding Member được trao tự động cho 50
> người onboard đầu tiên** (race-safe, đếm theo thứ tự hoàn tất `/start`),
> không phụ thuộc token. Link `invite_<token>` cũ vẫn redeem được (backward
> compatible) cho các link đã phát trước đó.

**A. `friends` — nhắn tay bạn bè thân**
```
Mình đang làm Bé Tiền — một trợ lý tài chính cá nhân nhắn qua Telegram, giúp
theo dõi tài sản và "nhìn trước" tương lai tài chính của mình. Đang mở cho 50
người đầu tiên dùng miễn phí. Bạn thử giúp mình với nhé, 5 phút thôi, rồi cho
mình xin cảm nhận thật 🙏
👉 [invite link]
```

**B. `personal_fb` — post Facebook cá nhân**
```
Sau một thời gian ấp ủ, mình mở cửa Bé Tiền cho 50 người đầu tiên 🌱

Bé Tiền là người đồng hành quản lý tài sản cho người Việt — nhắn tin qua
Telegram như chat với một người bạn hiểu tiền. Nó giúp bạn:
• Ghi lại tài sản & chi tiêu chỉ bằng một câu nhắn
• Thấy bức tranh tài chính tương lai của mình (mưa / nắng / bình thường)
• Nhận lời nhắc nhẹ nhàng mỗi sáng, không phán xét

50 người đầu là Founding Member: dùng miễn phí bây giờ, và giảm 50% trọn đời
khi bản Pro ra mắt. Ai muốn thử, nhắn mình hoặc vào link dưới nhé 👇
👉 [invite link]
```

**C. `vn_finance_community` — group/cộng đồng tài chính**
```
Chào cả nhà, mình đang phát triển Bé Tiền — trợ lý quản lý tài sản cá nhân cho
người Việt (Telegram bot). Trọng tâm là giúp người dùng hình dung quỹ đạo tài
sản tương lai bằng mô phỏng, thay vì chỉ ghi chép chi tiêu.

Đang tuyển 50 người dùng đầu để lấy feedback nghiêm túc. Hoàn toàn miễn phí
giai đoạn này. Rất mong được nghe góc nhìn từ cộng đồng. Cảm ơn cả nhà.
👉 [invite link]
```

**D. `direct_msg` — DM người từng quan tâm**
```
Chào [tên] 👋 Hồi trước bạn có nói quan tâm tới chuyện quản lý tài chính cá
nhân — giờ Bé Tiền đã mở cho nhóm đầu tiên rồi. Mình giữ một suất Founding
Member cho bạn (miễn phí giai đoạn này + giảm 50% trọn đời khi có bản Pro).
Bạn thử nhé, mình rất muốn nghe bạn nghĩ gì.
👉 [invite link]
```

**E. `tg_finance_groups` — group Telegram (ngắn)**
```
Bé Tiền — trợ lý quản lý tài sản cá nhân trên Telegram, đang mở 50 suất dùng
sớm miễn phí. Ghi tài sản bằng 1 câu nhắn, xem quỹ đạo tài chính tương lai.
Ai muốn thử & góp ý: 👉 [invite link]
```

### 6.4 Checklist trước khi gửi mỗi đợt seeding

- [ ] Dán đúng link `src_<source>` của kênh (để `/cohort_stats` đo sạch theo kênh)
- [ ] Người Việt đọc lại 1 lượt — nghe tự nhiên, không sượng, không "CFO"
- [ ] Founder đọc cuối cùng trước khi post
- [ ] Không hứa gì ngoài cam kết ở 6.1
- [ ] Đăng đúng nơi được phép (tránh spam group vi phạm rule cộng đồng)

### 6.5 Theo dõi cohort theo kênh (sau khi phát)

- [ ] `/cohort_stats` — breakdown user theo source mỗi sáng
- [ ] So redemption rate giữa các kênh → biết kênh nào hiệu quả cho lần scale 50 → 500
- [ ] Ghi lại insight vào retro (kênh nào convert tốt, message nào resonate)

---

## 7. 📊 Success metrics (theo dõi qua admin dashboard + KPI digest)

| Metric | Target |
|---|---|
| D1 retention | ≥70% |
| D7 retention | ≥40% |
| Twin shown trong session 1 | ≥70% |
| Real assets logged (7 ngày) | ≥60% |
| Intent classification accuracy | ≥85% confirmed |
| Feedback SLA <24h | ≥95% |
| In-onboarding emoji 😍 | ≥50% |
| Twin satisfaction (D7, định tính) | phỏng vấn tay 10 founding member |

---

## 8. ⛔ Kill criteria (đã document ở Story C.3)

Dừng/điều chỉnh nếu chạm bất kỳ ngưỡng nào:
- 4-week retention <20%
- Cost >50k VND/user/tháng
- P1 bug rate >1/ngày
- Persona violation >5/tuần
- In-onboarding emoji 😕 >30%
- Twin calibration <40% within-band

### Rollback

**Trước khi phát hết 50 invite:** ngừng phát, DM người chưa redeem
("Bé Tiền đang chỉnh sửa, sẽ quay lại sau X ngày"), điều tra theo action plan.

**Sau khi phát hết:** nhắn cohort ("Tuần tới Bé Tiền tạm dừng để cải thiện X.
Tài sản & lịch sử được giữ nguyên."), feature-flag-off surface bị ảnh hưởng.
**Cam kết founding vẫn giữ nguyên** dù cohort tạm dừng.

---

## 9. Cam kết vận hành của operator (soft launch fail nếu bỏ)

- [ ] Block **1 giờ/ngày × 7 ngày** cho feedback triage (đặt lịch lặp trên calendar)
- [ ] Theo dõi KPI digest mỗi sáng, phản hồi feedback trong SLA 24h
- [ ] Sau soft launch: viết retro → đưa insight vào kế hoạch scale 50 → 500

---

*Tạo cho soft launch tháng 6/2026. Sau launch: chuyển file này vào
`docs/archive/` cùng retro, hoặc cập nhật thành runbook cho đợt scale tiếp theo.*
