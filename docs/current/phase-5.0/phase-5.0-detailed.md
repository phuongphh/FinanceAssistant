# Phase 5.0 — Zalo Channel Launch

> Bé Tiền bước ra khỏi Telegram. 5.0 **không** làm tính năng mới — nó làm *đường ống Zalo đủ chắc để chở sản phẩm*: auth token tự xoay, webhook verify đúng thuật toán Zalo, dedup tin vào, và kỷ luật cửa sổ 48h/8-tin của Zalo OA. Issue list: [`phase-5.0-issues.md`](phase-5.0-issues.md).

**Chốt lịch:** Tháng 10/2026, ~2 tuần. **Không gate G1** — Zalo là mở kênh phân phối, độc lập với quyết định bật Guardian Layer (4.7 pending). Chạy song song được với mọi việc khác vì toàn bộ nằm sau `ZALO_CHANNEL_ENABLED` (đã có, default false).

**Trạng thái nền (Phase 4B Epic 4 đã merged):** `zalo_oa.py` (transport), `zalo_notifier.py` (Notifier port + strip_markdown + truncate 300), `zalo_linking_service.py` + `zalo_link_token` (pairing `BT-XXXXXX`), `routers/zalo.py` (webhook), `content/zalo.yaml` (copy linking + cashflow_alert), `notifier_resolver` fan-out 2 kênh. **Nền này chỉ đủ để gửi cảnh báo cashflow cho user đã link** — 5.0 vá 2 lỗi chặn-production và bổ sung 3 mảnh còn thiếu (xem §Phát hiện).

---

## 📋 Changelog vs Strategy V4

| Nguồn | Điều khoản | Ảnh hưởng 5.0 |
|---|---|---|
| Roadmap 5.0 | "Zalo OA đã sẵn sàng (founder decision 08/07/2026 — đôn lên từ deferred)" | Mở phase |
| Ladder of Engagement | Zalo là kênh phổ cập VN, hạ rào tiếp cận cho Level 0→1 (22-35 tuổi) | Lý do chiến lược |
| CLAUDE.md Layer Contract | Zalo webhook phải theo đúng luồng `router → dedup → worker → handler → service` như Telegram | Kiến trúc E2 |
| Phase 4.1 channel discipline | `ZALO_CHANNEL_ENABLED=false` → webhook không mount | Rollback |

---

## 🔎 Phát hiện khi audit nền 4B (đây là lý do 5.0 tồn tại)

| # | Vấn đề | Hiện trạng | Hệ quả nếu ship nguyên trạng |
|---|---|---|---|
| **P1** | **Webhook verify SAI thuật toán** | `routers/zalo.py:_verify_zalo_signature` dùng `HMAC-SHA256(secret, raw_body)`, chấp prefix `sha256=` | Zalo gửi `X-ZEvent-Signature: mac=<sha256(app_id + data + timestamp + OA_SecretKey)>` — **plain SHA256 trên chuỗi nối, KHÔNG phải HMAC trên body**. Prod bật secret → **100% webhook bị 403**. Dev không lộ vì secret rỗng = bypass. |
| **P2** | **Access token không bao giờ refresh** | `get_zalo_oa_client()` đọc `settings.zalo_oa_access_token` một lần lúc process start | Zalo access_token **sống 1 giờ**. Sau 1h mọi tin nhắn fail-open im lặng. Refresh_token sống 3 tháng nhưng **single-use, xoay mỗi lần refresh** → nếu lưu hỏng là mất kết nối OA, phải link tay lại. |
| **P3** | **Không có dedup tin vào** | Webhook xử lý thẳng trong request, không có bảng nào như `telegram_updates` | Zalo retry khi non-200 → user gõ 1 lần, Bé Tiền ghi 2 giao dịch. Vi phạm layer contract ("mọi update phải dedup trước khi xử lý"). |
| **P4** | **Không có intent dispatch** | Webhook chỉ nhận diện token `BT-XXXXXX`, còn lại trả copy linking | User trên Zalo gõ "ăn trưa 50k" → nhận về "Mã không hợp lệ". |
| **P5** | **Không đếm cửa sổ 48h / 8 tin** | Mọi outbound gọi thẳng `/message/cs` | Zalo chỉ cho gửi **tối đa 8 tin tư vấn miễn phí trong 48h** kể từ lần user tương tác cuối; ngoài cửa sổ là **tính phí hoặc bị chặn**. Job briefing/empathy có thể đốt quota rồi im lặng fail. |

P1 + P2 là **blocking production**. P3-P5 là điều kiện để 5.1 chở sản phẩm thật.

---

## 🧠 Design Philosophy

1. **Zalo là transport, không phải sản phẩm thứ hai.** Không fork handler, không fork service. Inbound Zalo đi vào **đúng intent pipeline của Telegram**; khác biệt duy nhất nằm ở renderer + notifier. Fork logic = 2 sản phẩm lệch nhau sau 3 tháng.
2. **Ràng buộc nền tảng là first-class citizen, không phải try/except.** Cửa sổ 48h, trần 8 tin, token 1h, refresh single-use — đều thành **state trong DB + guard ở service**, không phải "gửi thử rồi log warning".
3. **Fail sang Telegram, đừng fail im.** Zalo không gửi được (ngoài cửa sổ / hết quota / token hỏng) → user đã link Telegram vẫn nhận. `notifier_resolver` đã fan-out; 5.0 thêm điều kiện *có nên gửi Zalo lúc này không*.
4. **Kỷ luật kênh giữ nguyên.** Toàn bộ sau `ZALO_CHANNEL_ENABLED`. Off → `main.py` không mount webhook, `notifier_resolver` không trả kênh zalo → byte-identical pre-5.0.
5. **Thin slice trước, parity sau.** 5.0 mở đúng 3 luồng (link, capture chi tiêu, xem số dư/báo cáo ngắn) để *validate ràng buộc 300 ký tự + không Markdown trên flow thật*. Parity đầy đủ là 5.1 — mở hết ở 5.0 sẽ phát hiện lỗi format khi đã có user.

---

## 🎬 Choreography

**Inbound (mới — theo đúng contract Telegram):**
```
Zalo OA → POST /api/v1/zalo/webhook
  → verify mac = sha256(app_id + data + timestamp + oa_secret_key)   (P1)
  → INSERT zalo_updates(msg_id) ON CONFLICT DO NOTHING               (P3)
  → asyncio.create_task(zalo_worker) → return 200 (≤100ms)
       worker → resolve user theo zalo_user_id
              → stamp last_interaction_at (mở cửa sổ 48h)            (P5)
              → nếu chưa link: luồng token BT-XXXXXX (như 4B)
              → nếu đã link: intent classifier → dispatcher → handler (P4)
              → render qua ZaloContentRenderer → ZaloNotifier
              → commit MỘT LẦN ở biên worker
```

**Outbound (thêm guard):**
```
service/job → get_notifiers_for_user(user)
   → kênh zalo chỉ được thêm khi:
        token còn hạn (auto-refresh nếu <5 phút)                     (P2)
        AND còn trong cửa sổ 48h kể từ last_interaction_at           (P5)
        AND chưa chạm trần 8 tin tư vấn trong cửa sổ đó
   → không đủ điều kiện → bỏ kênh zalo, Telegram vẫn gửi, log lý do
```

**Token lifecycle (mới):**
```
zalo_oa_credentials (1 row/OA) { access_token, refresh_token, expires_at }
   → mỗi lần gửi: nếu expires_at - now < 5 phút → refresh
   → POST https://oauth.zaloapp.com/v4/oa/access_token
        headers: secret_key = APP_SECRET
        body: app_id, grant_type=refresh_token, refresh_token
   → response trả refresh_token MỚI → ghi đè ATOMIC trong 1 transaction
   → refresh cũ chết ngay. Lỗi ghi = mất OA → phải có lock + retry an toàn
```

---

## 📁 Files Touched

**E1 — Auth & transport hardening:**
- `backend/routers/zalo.py` — thay `_verify_zalo_signature` bằng công thức MAC đúng (P1)
- `backend/models/zalo_oa_credential.py` *(mới)* — token state 1 row/OA, `access_token`/`refresh_token`/`expires_at`
- `backend/services/zalo_token_service.py` *(mới)* — refresh + xoay refresh_token atomic, advisory lock chống double-refresh
- `backend/adapters/zalo_oa.py` — client nhận token **provider** (callable async) thay vì string cố định; bỏ singleton đọc settings (P2)
- `alembic/versions/*_zalo_oa_credentials.py` *(mới)*

**E2 — Inbound pipeline:**
- `backend/models/zalo_update.py` *(mới)* — dedup theo `msg_id` (PK), `status`, `user_id`, payload JSONB — mirror `telegram_updates` (P3)
- `backend/workers/zalo_worker.py` *(mới)* — claim → dispatch → commit một lần ở biên
- `backend/routers/zalo.py` — chỉ parse + verify + claim + enqueue, không xử lý business (P4)
- `backend/bot/handlers/zalo_inbound.py` *(mới)* — route: chưa-link → token flow; đã-link → intent dispatcher
- `alembic/versions/*_zalo_updates.py` *(mới)*

**E3 — Outbound discipline (cửa sổ 48h + quota):**
- `backend/models/zalo_message_window.py` *(mới)* — `user_id`, `last_interaction_at`, `free_msg_count`, `window_started_at` (P5)
- `backend/services/zalo_window_service.py` *(mới)* — pure/flush-only: `can_send()`, `record_inbound()`, `record_outbound()`
- `backend/services/notifier_resolver.py` — hỏi window service trước khi thêm kênh zalo
- `alembic/versions/*_zalo_message_window.py` *(mới)*

**E4 — Thin-slice flows + vận hành:**
- `content/zalo.yaml` — thêm section `capture`, `report_short`, `fallback`, `window_closed`
- `backend/adapters/zalo_content_renderer.py` — implement **tối thiểu** `render_briefing` dạng text ngắn (3 method còn lại vẫn raise → 5.1)
- `docs/conventions/zalo-operations.md` *(mới)* — runbook: đăng ký webhook, xác thực OA, xoay token thủ công, đọc quota

---

## 🗄️ New DB Tables

| Bảng | Mục đích | Ghi chú |
|---|---|---|
| `zalo_oa_credentials` | Token state (access/refresh/expires) | **Không** có `user_id` — đây là credential cấp OA, không phải per-user. Là ngoại lệ duy nhất của quy tắc multi-tenant; ghi rõ trong docstring. Token **không được log**, không vào audit trail. |
| `zalo_updates` | Dedup tin vào | PK = `msg_id` (Zalo cấp per-message). `user_id` nullable (resolve sau, giống `telegram_updates`). Có `status` + orphan recovery. |
| `zalo_message_window` | Cửa sổ 48h + đếm 8 tin miễn phí | `user_id` NOT NULL indexed. Reset khi user tương tác mới. |

Không sửa migration đã apply. Không đụng `users.zalo_user_id` (đã có, String(64)).

---

## 📦 Epics & Stories

Chi tiết sub-issue + DoD: [`phase-5.0-issues.md`](phase-5.0-issues.md).

### Epic E1 — Auth & Transport Hardening ⭐ *(blocking production)*
Vá P1 (MAC đúng công thức Zalo) + P2 (token 1h tự refresh, refresh_token single-use xoay atomic). Không có E1 thì mọi thứ sau nó chạy được 60 phút rồi chết im.

### Epic E2 — Inbound Pipeline (dedup + worker + dispatch)
Đưa Zalo về đúng layer contract: webhook mỏng, dedup `msg_id`, worker commit một lần, tin nhắn của user đã link đi vào intent dispatcher chung.

### Epic E3 — Outbound Discipline (cửa sổ 48h + quota 8 tin)
Biến ràng buộc nền tảng thành state có thể kiểm tra. `notifier_resolver` chỉ fan-out Zalo khi thật sự gửi được; ngược lại Telegram gánh, có log lý do.

### Epic E4 — Thin Slice + Vận Hành
3 luồng thật trên Zalo (link, capture chi tiêu, báo cáo ngắn) để validate 300 ký tự / không Markdown; runbook vận hành OA; xác thực OA (mất 3-7 ngày — **khởi động ở ngày 1** vì nó chặn 5.2).

---

## 🏗️ Layer Mapping

| Layer | 5.0 |
|---|---|
| `routers/` | `zalo.py`: verify MAC, claim `msg_id`, `create_task`, trả 200. **Không** business logic |
| `workers/` | `zalo_worker.py`: mở session, dispatch, `commit()` **một lần** ở biên |
| `handlers/` | `zalo_inbound.py`: route token-flow vs intent-flow, extract dữ liệu Zalo |
| `services/` | `zalo_token_service`, `zalo_window_service` — flush-only, **không commit**, không đọc env |
| `adapters/` | `zalo_oa.py` transport thuần; token lấy qua provider callable, không đọc settings |
| `content/` | Toàn bộ copy ở `content/zalo.yaml` — không hardcode chuỗi VN |

**Ngoại lệ được ghi nhận:** `zalo_token_service` cần đọc `ZALO_APP_ID`/`ZALO_APP_SECRET`. Giải: env đọc ở edge (worker/job/lifespan) và **inject vào service qua tham số**, service vẫn pure với env.

---

## ⚠️ Risk & Rollback

| Rủi ro | Giảm thiểu |
|---|---|
| Refresh token xoay hỏng → mất kết nối OA, phải link tay | Ghi token mới trong **cùng transaction** với việc dùng nó; advisory lock (`pg_advisory_xact_lock`) chống 2 worker refresh song song; runbook link lại thủ công trong `zalo-operations.md` |
| MAC verify vẫn sai (chưa test được với traffic thật) | Test vector từ payload thật ở staging **trước** khi bật prod; giữ chế độ `ZALO_SIGNATURE_ENFORCE=false` log-only trong 48h đầu, rồi mới enforce |
| Zalo retry gây double-capture | Dedup `msg_id` với `ON CONFLICT DO NOTHING` trước mọi xử lý |
| Đốt hết 8 tin miễn phí bằng job proactive | `zalo_window_service.can_send()` gate mọi outbound proactive; alert user-initiated ưu tiên hơn briefing |
| Copy vỡ format vì 300 ký tự / không Markdown | Thin slice 3 luồng + test khẳng định output Zalo không chứa ký tự Markdown và ≤300 |
| Xác thực OA trễ, chặn 5.2 | Nộp hồ sơ ngày 1 của phase (3-7 ngày duyệt), không đợi code xong |

**Rollback:** `ZALO_CHANNEL_ENABLED=false` → webhook không mount + `notifier_resolver` bỏ kênh zalo → hành vi byte-identical pre-5.0. Env đổi có hiệu lực sau restart service, không cần deploy code.

---

## ✅ Definition of Done

- Webhook verify đúng MAC Zalo; test vector từ payload thật pass; sai chữ ký → 403, không leak `user_id` ra log.
- Access token tự refresh trước hạn; refresh_token xoay atomic; kill process giữa chừng → không mất OA (test).
- Tin nhắn Zalo trùng `msg_id` → xử lý đúng 1 lần (test retry).
- User đã link gõ "ăn trưa 50k" trên Zalo → giao dịch được ghi, phản hồi ≤300 ký tự, không Markdown.
- Ngoài cửa sổ 48h hoặc đã dùng 8 tin → không gọi `/message/cs`, Telegram vẫn nhận, log rõ lý do.
- `ZALO_CHANNEL_ENABLED=false` → toàn bộ suite Telegram byte-identical.
- ruff + layer-contract-checker sạch; vi-localization-checker pass; 0 chuỗi "Decision Engine/CFO/GPS".
- Runbook `zalo-operations.md` có: đăng ký webhook, xác thực OA, xoay token tay, đọc quota.

---

## 🚫 Out of Scope (để 5.1 / 5.2)

- Twin view, comparison, milestone trên Zalo (renderer đầy đủ) → **5.1**.
- Nút bấm / rich template (`oa.open.url`, `oa.query.show`) → **5.1**.
- ZNS (tin ngoài cửa sổ 48h, template duyệt trước) → **5.1**.
- Mini App → **5.2**.
- Ảnh/biểu đồ trên Zalo (cần URL public, không nhận bytes) → **5.1**.
- Onboarding người dùng mới *bắt đầu từ* Zalo (5.0 vẫn yêu cầu link từ Telegram) → **5.1**.

---

## 🔀 Execution Order (đề xuất)

```
Ngày 1: nộp hồ sơ xác thực OA (3-7 ngày, chạy nền, chặn 5.2)
E1 (MAC + token refresh) ──> E2 (dedup + worker + dispatch) ──> E4 (thin slice)
E3 (window + quota) ──> E4
E1 ──> staging soak 48h (signature log-only) ──> bật ZALO_CHANNEL_ENABLED
```

E1 đi trước vì P1/P2 chặn mọi thứ. E3 độc lập E2, chạy song song.

---

## 📚 Nguồn & điều cần verify lại lúc build

Thông tin nền tảng dưới đây thu thập qua web search (docs chính chủ `developers.zalo.me` bị network policy của môi trường chặn — xem runbook). **Bắt buộc đối chiếu lại với docs chính chủ ở issue đầu tiên của mỗi Epic trước khi code:**

- Endpoint tin nhắn: `POST https://openapi.zalo.me/v3.0/oa/message/cs`, auth qua header `access_token`; lỗi ứng dụng trả HTTP 200 + field `error` ≠ 0.
- OAuth: `POST https://oauth.zaloapp.com/v4/oa/access_token`, header `secret_key`, body `app_id` + `grant_type` + `refresh_token`. **access_token 1 giờ; refresh_token 3 tháng, single-use, xoay mỗi lần refresh.**
- Webhook: header `X-ZEvent-Signature` = `mac=<hex>`, `hex = sha256(app_id + data + timestamp + OA_SecretKey)` — dùng **OA Secret Key**, không phải app secret.
- Cửa sổ tin nhắn: 48 giờ kể từ tương tác cuối của user; **tối đa 8 tin tư vấn miễn phí** trong cửa sổ; ngoài cửa sổ tính phí theo bảng giá.
- Rate limit ~10 request/giây; quota API trả `remain`/`total` với `quota_type` ∈ {`welcome_msg`, `sub_quota`, `purchase_quota`}.

---

## 🔓 Product Decisions Cần Owner Ký

1. **Zalo là kênh phụ hay kênh ngang hàng?** 5.0 code theo hướng *ngang hàng nhưng ràng buộc nền tảng chặt hơn* (Telegram luôn là fallback). Nếu owner muốn Zalo thành kênh chính cho user mới → cần đổi thiết kế onboarding ở 5.1. *Đề xuất: kênh ngang hàng, Telegram fallback.*
2. **Ngân sách tin ngoài cửa sổ 48h.** Ngoài cửa sổ phải trả phí hoặc dùng ZNS (1000 tin miễn phí/tháng cho OA đã xác thực). Có chấp nhận chi phí không, trần bao nhiêu/tháng? *Đề xuất 5.0: không gửi ngoài cửa sổ, để dành quyết định cho 5.1 khi có số liệu thật.*
3. **Xác thực OA (verified).** Bắt buộc cho ZNS và **bắt buộc cho Mini App (5.2)**. Cần hồ sơ doanh nghiệp. *Đề xuất: nộp ngay ngày 1.*
4. **Thin slice gồm những intent nào?** *Đề xuất: link account, capture chi tiêu, báo cáo ngắn (số dư + chi tháng này). Chốt ở #4.1.*
