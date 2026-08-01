# Phase 5.1 — Zalo Core Product Parity

> 5.0 dựng đường ống. 5.1 chở **toàn bộ sản phẩm** qua đó: Twin, briefing, advisory, decision queries, asset entry — với ràng buộc Zalo (không Markdown, ~300 ký tự hiển thị, ảnh phải là URL public, nút bấm khác Telegram, tin ngoài 48h phải qua ZNS template duyệt trước). Issue list: [`phase-5.1-issues.md`](phase-5.1-issues.md).

**Chốt lịch:** Tháng 10-11/2026, ~2-3 tuần. **Phụ thuộc cứng:** Phase 5.0 xong (token refresh + dedup + window service) và **OA đã được xác thực** (điều kiện của ZNS).

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
4. **Ngoài 48h là thế giới khác.** Trong cửa sổ: tin tự do. Ngoài cửa sổ: **ZNS template duyệt trước, tối đa ~400 ký tự, có hạn mức**. Briefing hằng ngày phần lớn rơi ra ngoài cửa sổ → phải có template ZNS, hoặc chấp nhận chỉ gửi cho user đang hoạt động.
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

**Proactive ngoài cửa sổ 48h:**
```
job briefing/empathy → zalo_window_service.can_send()
   ok            → /message/cs như thường
   window_closed → nếu có ZNS template phù hợp + còn hạn mức → gửi ZNS
                 → nếu không → bỏ kênh Zalo, Telegram gánh, log lý do
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

**E5 — ZNS (tin ngoài cửa sổ):**
- `backend/adapters/zalo_zns.py` *(mới)* — gửi theo `template_id` + params
- `backend/services/zns_service.py` *(mới)* — chọn template, đếm hạn mức, quyết định gửi hay bỏ
- `content/zns_templates.yaml` *(mới)* — map nội dung ↔ `template_id` đã duyệt

---

## 🗄️ New DB Tables

| Bảng | Mục đích | Ghi chú |
|---|---|---|
| `media_objects` | Ảnh phục vụ URL public tạm thời | `user_id` NOT NULL indexed. Lưu **hash** của token, không lưu token. TTL mặc định 15 phút. Soft delete `deleted_at`. |
| *(có thể)* `zns_send_log` | Đếm hạn mức ZNS + audit | Chỉ thêm nếu E5 được duyệt (xem Owner Decisions). `user_id` NOT NULL. |

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
Mở toàn bộ dispatcher cho Zalo. User mới có thể bắt đầu **thẳng từ Zalo** — đây là điểm khiến Zalo thành kênh tăng trưởng thật, không chỉ kênh thông báo.

### Epic E5 — ZNS cho tin ngoài cửa sổ 48h *(có điều kiện — cần owner ký)*
Template duyệt trước, ~400 ký tự, hạn mức tháng. Chỉ làm nếu owner chấp nhận chi phí + quy trình duyệt template.

---

## 🏗️ Layer Mapping

| Layer | 5.1 |
|---|---|
| `routers/` | `media.py`: verify token ký, trả bytes. Không business logic |
| `workers/` | `zalo_worker` không đổi (5.0 đã đúng) |
| `handlers/` | `zalo_inbound` chỉ mở dispatcher — **không** if/else theo kênh cho từng intent |
| `services/` | `media_url_service`, `zns_service` — flush-only, không commit, không env |
| `adapters/` | `zalo_content_renderer`, `zalo_button_mapper`, `zalo_zns` — nơi DUY NHẤT biết Zalo khác Telegram |
| `content/` | Copy Zalo riêng cho từng surface; không cắt chuỗi copy Telegram |

---

## ⚠️ Risk & Rollback

| Rủi ro | Giảm thiểu |
|---|---|
| URL ảnh public bị đoán/chia sẻ → lộ tài chính cá nhân | Token ký HMAC ngẫu nhiên ≥32 byte, TTL 15 phút, lưu hash không lưu token, không đánh số tuần tự, `Cache-Control: no-store`, job dọn. Test khẳng định URL hết hạn trả 404 |
| Copy Zalo cụt lủn làm hỏng persona | Copy viết riêng + prompt-tester × 3 xưng hô; test "đọc to" trong DoD; cấm dùng `truncate_for_zalo` cho surface đã có copy riêng |
| Nút bấm mất im lặng → user kẹt flow | `zalo_button_mapper` bắt buộc trả *một trong hai*: payload Zalo hoặc dòng text thay thế; test khẳng định không có nút nào biến mất |
| ZNS template bị từ chối duyệt → briefing ngoài cửa sổ không gửi được | Nộp template sớm; fallback đã sẵn (bỏ kênh Zalo, Telegram gánh) — ZNS là *thêm*, không phải *phụ thuộc* |
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
- Proactive ngoài cửa sổ 48h: gửi ZNS (nếu E5 duyệt) hoặc bỏ kênh Zalo có log — **không bao giờ** gọi `/message/cs` ngoài cửa sổ.
- prompt-tester + vi-localization-checker pass; 0 "Decision Engine/CFO/GPS"; mọi copy Zalo ≤300 ký tự, không Markdown, ≤2 emoji.
- ruff + layer-contract-checker sạch; toàn suite xanh; 0 file trong `backend/services/` có nhánh `if channel == "zalo"`.

---

## 🚫 Out of Scope (để 5.2 / sau)

- Mini App (dashboard tương tác, cone kéo được) → **5.2**.
- Thanh toán / gói trả phí trên Zalo.
- Nhóm chat Zalo (OA hiện chỉ 1-1).
- Voice/ảnh **gửi vào** từ Zalo (OCR sao kê, ghi âm) → phase sau; v1 chỉ text vào.
- Zalo Ads / growth automation.

---

## 🔀 Execution Order (đề xuất)

```
E1 (media URL) ──> E2 (renderer đầy đủ) ──> E4 (parity + onboarding)
E3 (buttons) ──> E2
E5 (ZNS) song song, gated owner decision + template duyệt (nộp sớm)
E2 + E4 ──> parity test suite ──> persona QA ──> mở rộng cohort
```

E1 trước vì Twin/briefing đều có ảnh — làm renderer trước sẽ phải viết lại.

---

## 🔓 Product Decisions Cần Owner Ký

1. **Có làm ZNS không (E5)?** Cần OA xác thực, template duyệt trước, có hạn mức miễn phí hằng tháng rồi tính phí. Không làm → user Zalo im lặng >48h sẽ **không nhận briefing**. *Đề xuất: làm 1-2 template tối thiểu (briefing + cảnh báo cashflow), đo tỉ lệ đọc rồi quyết mở rộng.*
2. **Onboarding từ Zalo: user chỉ-Zalo có phải công dân hạng nhất?** Nếu có → `telegram_id` nullable + rà toàn bộ giả định. Nếu không → Zalo mãi là kênh phụ. *Đề xuất: công dân hạng nhất — đây là lý do làm Zalo.*
3. **TTL ảnh + mức riêng tư.** 15 phút có đủ không (user mở lại tin cũ sẽ thấy ảnh hỏng)? Đánh đổi tiện lợi ↔ rò rỉ. *Đề xuất: 15 phút, kèm dòng "ảnh hết hạn, nhắn 'xem twin' để xem lại".*
4. **Khi Zalo và Telegram cùng bật, gửi cả hai hay chọn một?** Hiện fan-out cả hai. Với Zalo có hạn mức, gửi trùng là lãng phí quota. *Đề xuất: thêm `users.preferred_channel`, mặc định fan-out, cho user chọn ở 5.1.*
