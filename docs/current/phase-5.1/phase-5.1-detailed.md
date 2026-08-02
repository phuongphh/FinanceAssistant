# Phase 5.1 — Zalo Core Product Parity

> 5.0 dựng đường ống. 5.1 chở **toàn bộ sản phẩm** qua đó: Twin, briefing, advisory, decision queries, asset entry — với ràng buộc Zalo (không Markdown, ~300 ký tự hiển thị, ảnh phải là URL public, nút bấm khác Telegram, ngoài cửa sổ 48h là im lặng). Issue list: [`phase-5.1-issues.md`](phase-5.1-issues.md).

**Chốt lịch:** Tháng 10-11/2026, ~2-3 tuần. **Phụ thuộc cứng:** Phase 5.0 xong (token refresh + dedup + window service). *Không* phụ thuộc OA xác thực — xác thực chỉ còn cần cho Mini App ở 5.2.

> ✅ **Chốt 02/08/2026 — Zalo là kênh reactive-first.** Không làm ZNS (tốn tiền, template cứng phải duyệt trước). Bé Tiền chỉ nói trên Zalo khi user vừa nói trước, trong cửa sổ 48h. Toàn bộ *proactive* (briefing hằng ngày, empathy, cảnh báo khi user im lặng) ở lại **Telegram**. Epic E5 (ZNS) trong bản nháp trước **đã bị loại**, không hoãn. Chi tiết: Decision #2 trong [phase 5.0 doc](../phase-5.0/phase-5.0-detailed.md#-product-decisions-cần-owner-ký).

**Nguyên tắc xuyên suốt:** không có "phiên bản Zalo" của bất kỳ service nào. Mọi thứ khác biệt phải nằm gọn trong `ZaloContentRenderer` + `ZaloNotifier` + `content/zalo.yaml`. Nếu một PR ở 5.1 phải sửa file trong `backend/services/` để "cho hợp Zalo" → thiết kế sai, dừng lại.

---

## 📋 Changelog vs Strategy V4

| Nguồn | Điều khoản | Ảnh hưởng 5.1 |
|---|---|---|
| Roadmap 5.1 | "Toàn bộ product hiện tại trên Zalo... content layer adapted cho Zalo constraints" | Phạm vi |
| Ladder of Engagement | User Zalo phải leo được đúng thang như user Telegram | Parity là mục tiêu, không phải subset |
| CLAUDE.md `ports/content_renderer` | Renderer là điểm khác biệt kênh duy nhất được phép | Ranh giới kiến trúc |
| Persona | Cắt chữ để vừa 300 ký tự **không được** làm giọng Bé Tiền cụt lủn | E4 |

---

## 🧠 Design Philosophy

1. **Ràng buộc kênh là bài toán *biên tập*, không phải bài toán *cắt chuỗi*.** `truncate_for_zalo()` hiện cắt bằng dấu ba chấm — đủ cho cảnh báo cashflow, **không đủ** cho briefing hay Twin. 5.1 cần **copy viết riêng cho Zalo** (ngắn từ đầu), không phải copy Telegram bị cắt cụt.
2. **Ảnh là điểm gãy kiến trúc lớn nhất.** `ChannelContent.images` là `tuple[bytes, ...]` vì Telegram nhận bytes. Zalo **chỉ nhận URL public**. Không thể giải bằng cách đổi renderer — cần một tầng lưu trữ + URL ký ngắn hạn. Đây là hạ tầng, làm sớm (E1).
3. **Nút bấm không phải inline keyboard.** Telegram có `callback_data` đi ngược về bot. Zalo có `oa.open.url` (mở link) và `oa.query.show` (gửi lại một câu hỏi dạng text). Ánh xạ mất mát: mọi flow phụ thuộc callback state phải được thiết kế lại thành **text-driven** trên Zalo.
4. **Ngoài 48h là im lặng, và đó là lựa chọn có chủ đích.** Trong cửa sổ: tin tự do (trần 8 tin tư vấn). Ngoài cửa sổ: **không gửi gì cả** — không ZNS, không tin trả phí. Briefing hằng ngày phần lớn rơi ra ngoài cửa sổ, nên trên Zalo briefing **chỉ đến với user đang hoạt động**; user im lặng nhận briefing qua Telegram. Parity ở 5.1 là parity của *câu trả lời*, không phải parity của *lời mở đầu*.
5. **Parity đo bằng hành vi, không bằng danh sách file.** Mỗi intent có test "cùng input, hai kênh, cùng *kết luận*" — chữ khác nhau được, con số và quyết định thì không.

---

## 🎬 Choreography

**Ảnh (chart Twin, briefing card):**
```
handler → renderer trả ChannelContent(images=bytes)
   → ZaloNotifier: cần URL, không có bytes
   → media_url_service.publish(bytes, ttl=15 phút)
        lưu vào storage + sinh token ký (HMAC, hết hạn)
   → GET /api/v1/media/{token} trả bytes (no-auth, token tự chứng)
   → gửi /message/cs attachment template media với url đó
   → job dọn media hết hạn
```

**Nút bấm:**
```
ChannelContent.buttons (transport-neutral)
   → Telegram: inline keyboard, callback_data
   → Zalo:  web_app_url / link  → oa.open.url
            callback_data       → oa.query.show với payload = câu người dùng "nói"
            không ánh xạ được   → hạ cấp thành dòng gợi ý text ("Nhắn 'xem twin' để…")
```

**Proactive ngoài cửa sổ 48h (reactive-first):**
```
job briefing/empathy → zalo_window_service.can_send()
   ok            → /message/cs như thường
   window_closed → bỏ kênh Zalo, log lý do. HẾT.
                   user có Telegram  → Telegram gánh (fan-out sẵn có)
                   user chỉ có Zalo  → không gửi; nội dung được giữ lại và
                                       kể lại ở lần user quay lại (#4.5)
```

---

## 📁 Files Touched

**E1 — Media URL infrastructure:**
- `backend/services/media_url_service.py` *(mới)* — publish bytes → URL ký ngắn hạn, flush-only
- `backend/routers/media.py` *(mới)* — `GET /api/v1/media/{token}`, verify chữ ký + hạn, trả bytes
- `backend/models/media_object.py` *(mới)* — `user_id`, `token_hash`, `content_type`, `expires_at`, `deleted_at`
- `backend/jobs/cleanup_media.py` *(mới)* — dọn object hết hạn
- `alembic/versions/*_media_objects.py` *(mới)*

**E2 — `ZaloContentRenderer` đầy đủ:**
- `backend/adapters/zalo_content_renderer.py` — implement `render_twin_view`, `render_twin_comparison`, `render_milestone` (5.0 đã làm `render_briefing`)
- `backend/adapters/zalo_notifier.py` — nhận `ChannelContent` có ảnh → gọi `media_url_service`; ánh xạ buttons; bỏ `truncate` thô cho luồng đã có copy riêng
- `content/zalo.yaml` — mở rộng: `twin`, `briefing`, `milestone`, `advisory`, `decision`, `asset_entry`, `onboarding`

**E3 — Rich message + buttons:**
- `backend/adapters/zalo_oa.py` — `send_message_with_buttons()` (attachment template + `oa.open.url` / `oa.query.show`)
- `backend/adapters/zalo_button_mapper.py` *(mới)* — pure: `Button` → payload Zalo, hoặc hạ cấp thành text

**E4 — Intent parity + onboarding từ Zalo:**
- `backend/bot/handlers/zalo_inbound.py` — bỏ whitelist thin-slice, mở toàn bộ dispatcher
- `backend/services/zalo_linking_service.py` — cho phép **onboarding bắt đầu từ Zalo** (tạo user mới từ `zalo_user_id`, không bắt buộc có Telegram trước)
- `backend/models/user.py` — `telegram_id` phải nullable được (kiểm tra + migration nếu cần)
- `backend/services/zalo_catchup_service.py` *(mới, #4.5)* — user chỉ-Zalo quay lại sau khi cửa sổ đóng: gom những gì đã bỏ lỡ thành **một** dòng ngắn kèm vào phản hồi đầu tiên
- `content/zalo.yaml` — thêm section `catchup`

**~~E5 — ZNS~~ — đã loại** (chốt 02/08/2026). Không tạo `zalo_zns.py`, `zns_service.py`, `content/zns_templates.yaml`.

---

## 🗄️ New DB Tables

| Bảng | Mục đích | Ghi chú |
|---|---|---|
| `media_objects` | Ảnh phục vụ URL public tạm thời | `user_id` NOT NULL indexed. Lưu **hash** của token, không lưu token. TTL mặc định 15 phút. Soft delete `deleted_at`. |
| *(có thể)* `zalo_missed_notice` | Ghi lại proactive bị bỏ vì cửa sổ đóng, để kể lại khi user quay lại (#4.5) | `user_id` NOT NULL indexed. Chỉ thêm nếu #4.5 cần state bền; nếu dựng lại được từ dữ liệu sẵn có (briefing sinh theo ngày) thì **không tạo bảng**. Chốt trong PR của #4.5. |

*(Bảng `zns_send_log` trong bản nháp trước đã bỏ cùng Epic E5.)*

**Migration cần rà:** `users.telegram_id` hiện có thể đang NOT NULL/unique — onboarding-từ-Zalo cần nó nullable. Kiểm tra ở #4.2 trước khi hứa.

---

## 📦 Epics & Stories

Chi tiết sub-issue + DoD: [`phase-5.1-issues.md`](phase-5.1-issues.md).

### Epic E1 — Media URL Infrastructure ⭐ *(chặn mọi thứ có ảnh)*
Zalo không nhận bytes. Dựng tầng publish bytes → URL ký ngắn hạn + endpoint phục vụ + job dọn. Đây là hạ tầng dùng lại cho 5.2 (Mini App cũng cần URL ảnh).

### Epic E2 — `ZaloContentRenderer` Đầy Đủ
Bỏ hết `NotImplementedError`. Twin/comparison/milestone render thành text ngắn + ảnh URL. Copy **viết riêng cho Zalo**, không cắt copy Telegram.

### Epic E3 — Rich Message & Button Mapping
`Button` transport-neutral → `oa.open.url` / `oa.query.show`, hoặc hạ cấp thành dòng gợi ý text. Ánh xạ mất mát phải **cố ý và có test**, không phải im lặng nuốt nút.

### Epic E4 — Intent Parity + Onboarding từ Zalo
Mở toàn bộ dispatcher cho Zalo. User mới có thể bắt đầu **thẳng từ Zalo** — đây là điểm khiến Zalo thành kênh tăng trưởng thật, không chỉ kênh thông báo. Vì Zalo là reactive-first, Epic này gánh thêm #4.5 (catch-up khi user quay lại) để user chỉ-Zalo không mất hẳn phần chủ động.

### ~~Epic E5 — ZNS cho tin ngoài cửa sổ 48h~~ — **ĐÃ LOẠI** (chốt 02/08/2026)
Owner chốt không chi tiền cho ZNS và không chấp nhận ràng buộc template duyệt trước. Zalo là kênh reactive-first; proactive giữ trên Telegram. Không có Epic thay thế — phần bù duy nhất là #4.5 (kể lại khi user quay lại), nằm trong E4.

---

## 🏗️ Layer Mapping

| Layer | 5.1 |
|---|---|
| `routers/` | `media.py`: verify token ký, trả bytes. Không business logic |
| `workers/` | `zalo_worker` không đổi (5.0 đã đúng) |
| `handlers/` | `zalo_inbound` chỉ mở dispatcher — **không** if/else theo kênh cho từng intent |
| `services/` | `media_url_service`, `zalo_catchup_service` — flush-only, không commit, không env |
| `adapters/` | `zalo_content_renderer`, `zalo_button_mapper` — nơi DUY NHẤT biết Zalo khác Telegram |
| `content/` | Copy Zalo riêng cho từng surface; không cắt chuỗi copy Telegram |

---

## ⚠️ Risk & Rollback

| Rủi ro | Giảm thiểu |
|---|---|
| URL ảnh public bị đoán/chia sẻ → lộ tài chính cá nhân | Token ký HMAC ngẫu nhiên ≥32 byte, TTL 15 phút, lưu hash không lưu token, không đánh số tuần tự, `Cache-Control: no-store`, job dọn. Test khẳng định URL hết hạn trả 404 |
| Copy Zalo cụt lủn làm hỏng persona | Copy viết riêng + prompt-tester × 3 xưng hô; test "đọc to" trong DoD; cấm dùng `truncate_for_zalo` cho surface đã có copy riêng |
| Nút bấm mất im lặng → user kẹt flow | `zalo_button_mapper` bắt buộc trả *một trong hai*: payload Zalo hoặc dòng text thay thế; test khẳng định không có nút nào biến mất |
| **User chỉ-Zalo im lặng >48h → không nhận bất kỳ proactive nào** (hệ quả trực tiếp của chốt reactive-first; user Telegram không dính vì có fan-out) | Chấp nhận có ý thức. Giảm thiểu: #4.5 kể lại phần bỏ lỡ ở lần quay lại; onboarding Zalo mời link Telegram *một lần*, không nài (#4.3); theo dõi retention riêng cho cohort chỉ-Zalo vs có-Telegram — nếu chênh lệch lớn thì mở lại quyết định ZNS bằng **số liệu**, không bằng cảm tính |
| #4.5 biến thành hộp thư dồn ứ → user quay lại bị dội 5 tin cũ | Catch-up là **một** dòng gộp, không phải phát lại từng tin; chỉ lấy nội dung trong N ngày gần nhất; test khẳng định không bao giờ vượt 1 tin catch-up mỗi lần quay lại |
| Onboarding từ Zalo tạo user mồ côi (không Telegram) | Rà `telegram_id` nullable + mọi truy vấn giả định có Telegram; test suite chạy với user chỉ-Zalo |
| Parity trôi dạt theo thời gian | Test bảng "cùng input → cùng kết luận" cho từng intent, chạy trong CI |

**Rollback:** `ZALO_CHANNEL_ENABLED=false` → về trạng thái 5.0/pre-5.0. Riêng E1 (media URL) là hạ tầng độc lập kênh — nếu cần tắt riêng, thêm `MEDIA_URL_ENABLED` đọc ở router edge.

---

## ✅ Definition of Done

- Mọi method của `ZaloContentRenderer` chạy thật, 0 `NotImplementedError`.
- Ảnh chart Twin hiển thị được trên Zalo; URL hết hạn sau TTL trả 404; job dọn chạy.
- Mỗi intent có test parity: cùng input trên Telegram và Zalo → cùng con số, cùng kết luận.
- Nút bấm: mỗi `Button` hoặc thành nút Zalo hoặc thành dòng gợi ý text — có test, không nút nào mất im lặng.
- User mới đăng ký thẳng từ Zalo đi hết onboarding, không cần Telegram.
- Proactive ngoài cửa sổ 48h: bỏ kênh Zalo **có log lý do** — **không bao giờ** gọi `/message/cs` ngoài cửa sổ, và **không có** đường gửi trả phí nào trong code (test khẳng định repo không có adapter ZNS).
- User chỉ-Zalo quay lại sau khi bỏ lỡ proactive → nhận **đúng một** dòng catch-up kèm phản hồi đầu tiên, đúng giọng Bé Tiền, không trách móc.
- prompt-tester + vi-localization-checker pass; 0 "Decision Engine/CFO/GPS"; mọi copy Zalo ≤300 ký tự, không Markdown, ≤2 emoji.
- ruff + layer-contract-checker sạch; toàn suite xanh; 0 file trong `backend/services/` có nhánh `if channel == "zalo"`.

---

## 🚫 Out of Scope (để 5.2 / sau)

- **ZNS / mọi hình thức gửi tin ngoài cửa sổ 48h** → đã loại hẳn (chốt 02/08/2026), không hoãn sang phase sau.
- Mini App (dashboard tương tác, cone kéo được) → **5.2**.
- Thanh toán / gói trả phí trên Zalo.
- Nhóm chat Zalo (OA hiện chỉ 1-1).
- Voice/ảnh **gửi vào** từ Zalo (OCR sao kê, ghi âm) → phase sau; v1 chỉ text vào.
- Zalo Ads / growth automation.

---

## 🔀 Execution Order (đề xuất)

```
E1 (media URL) ──> E2 (renderer đầy đủ) ──> E4 (parity + onboarding + catch-up)
E3 (buttons) ──> E2
E2 + E4 ──> parity test suite ──> persona QA ──> mở rộng cohort
```

(E5/ZNS đã loại — không còn nhánh gated owner decision nào trong 5.1.)

E1 trước vì Twin/briefing đều có ảnh — làm renderer trước sẽ phải viết lại.

---

## 🔓 Product Decisions Cần Owner Ký

1. ✅ **CHỐT 02/08/2026 — Không làm ZNS (E5 loại).** Zalo là kênh reactive-first, proactive giữ trên Telegram. Chấp nhận: user Zalo im lặng >48h **không nhận briefing trên Zalo**. Bù bằng #4.5 (catch-up khi quay lại), không bù bằng tiền.
2. **Onboarding từ Zalo: user chỉ-Zalo có phải công dân hạng nhất?** Nếu có → `telegram_id` nullable + rà toàn bộ giả định. Nếu không → Zalo mãi là kênh phụ. *Đề xuất: công dân hạng nhất về mặt **sản phẩm** (làm được mọi thứ khi mở app), nhưng sau chốt #1 thì **không** hạng nhất về mặt **nhắc nhở** — họ không có kênh proactive nào. Nếu owner thấy khoảng cách này quá lớn, lựa chọn còn lại là mời link Telegram trong onboarding Zalo (đang là mời một lần ở #4.3), chứ không phải mở lại ZNS.*
3. **TTL ảnh + mức riêng tư.** 15 phút có đủ không (user mở lại tin cũ sẽ thấy ảnh hỏng)? Đánh đổi tiện lợi ↔ rò rỉ. *Đề xuất: 15 phút, kèm dòng "ảnh hết hạn, nhắn 'xem twin' để xem lại".*
4. **Khi Zalo và Telegram cùng bật, gửi cả hai hay chọn một?** Hiện fan-out cả hai. Với Zalo có hạn mức, gửi trùng là lãng phí quota. *Đề xuất: thêm `users.preferred_channel`, mặc định fan-out, cho user chọn ở 5.1.*
