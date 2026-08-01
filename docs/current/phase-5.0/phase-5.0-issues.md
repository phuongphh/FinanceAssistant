# Phase 5.0 — Issues Breakdown

> Zalo Channel Launch: vá 2 lỗi chặn-production của nền 4B (webhook MAC sai, token không refresh), đưa Zalo về đúng layer contract (dedup + worker + dispatch), và biến ràng buộc 48h/8-tin thành state kiểm tra được. GitHub-ready issue list. Detail: [`phase-5.0-detailed.md`](phase-5.0-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E1 | Auth & Transport Hardening ⭐ | 4 | P0 (blocking production) | ~3-4 ngày |
| E2 | Inbound Pipeline (dedup + worker + dispatch) | 3 | P0 (layer contract) | ~3 ngày |
| E3 | Outbound Discipline (48h + quota 8 tin) | 3 | P0 (chống đốt quota) | ~2 ngày |
| E4 | Thin Slice + Vận Hành | 3 | P1 | ~2-3 ngày |

**Tổng:** 4 Epics / 13 issues. Thứ tự: E1 → E2 → E4; E3 song song E2. Hồ sơ xác thực OA nộp ngày 1 (3-7 ngày duyệt, chặn 5.2).

## 🏷️ Label Conventions
- `phase-5.0`, `epic-1`…`epic-4`
- `zalo-transport` / `zalo-inbound` / `zalo-quota`
- `blocking-prod` (P1/P2 — sai là prod chết im, không có alert)
- `persona-critical` (mọi issue chạm copy Bé Tiền — bắt buộc vi-localization-checker)
- `platform-verify` (bắt buộc đối chiếu docs chính chủ Zalo trước khi code)

---

## 🅰️ Epic #E1 — Auth & Transport Hardening ⭐ `blocking-prod`

### Description
Nền 4B có 2 lỗi khiến Zalo **không thể chạy production**: webhook verify dùng sai thuật toán (HMAC-over-body thay vì SHA256 chuỗi nối), và access token đọc một lần lúc start trong khi Zalo cấp token sống 1 giờ. Cả hai fail *im lặng* — không có alert nào nổ.

### Success criteria (Epic-level)
- Webhook thật từ Zalo pass verify; payload giả mạo → 403.
- Bot gửi được tin sau 3 giờ chạy liên tục (token đã xoay ≥2 lần).
- Kill process giữa lúc refresh → OA vẫn kết nối được (refresh_token không mất).

### Child issues

#### Issue #1.1 — Đối chiếu docs chính chủ Zalo `platform-verify`
- Xác nhận trước khi code: công thức MAC webhook, tên header, endpoint + body OAuth refresh, TTL token, giới hạn cửa sổ 48h/8 tin, rate limit, mã lỗi retryable. Ghi kết quả vào `docs/conventions/zalo-operations.md` §"Platform facts (verified <ngày>)". Nếu lệch với `phase-5.0-detailed.md` §Nguồn → cập nhật doc trong cùng PR.
- **DoD:** bảng platform facts có ngày verify + link docs; mọi hằng số dùng trong code trỏ về bảng này.

#### Issue #1.2 — Sửa webhook signature verification `blocking-prod`
- `backend/routers/zalo.py`: thay `_verify_zalo_signature` — tính `sha256(app_id + data + timestamp + oa_secret_key)` với `data` = raw body string, `timestamp` lấy từ payload; chấp header dạng `mac=<hex>`. So sánh constant-time. Thêm `ZALO_SIGNATURE_ENFORCE` (default true; đặt false trong soak 48h đầu → log-only, vẫn xử lý).
- **DoD:** unit test với vector dựng tay + ≥1 payload thật từ staging; sai chữ ký → 403 và log KHÔNG chứa `user_id`/token; enforce=false → log warning nhưng vẫn 200; secret rỗng (dev) vẫn bypass như cũ.

#### Issue #1.3 — `zalo_oa_credentials` + `zalo_token_service` (refresh atomic) `blocking-prod`
- `backend/models/zalo_oa_credential.py`: 1 row/OA — `access_token`, `refresh_token`, `expires_at`, `updated_at`. Docstring ghi rõ đây là **ngoại lệ multi-tenant có chủ ý** (credential cấp OA, không per-user) và token **không bao giờ được log**.
- `backend/services/zalo_token_service.py`: `get_valid_token()` — refresh khi còn <5 phút; gọi `POST https://oauth.zaloapp.com/v4/oa/access_token`; **ghi access_token + refresh_token mới trong CÙNG transaction**; `pg_advisory_xact_lock` chống 2 worker refresh song song (refresh_token single-use — refresh đôi = mất OA). Service flush-only, `app_id`/`app_secret` **inject qua tham số**, không đọc env.
- Migration `zalo_oa_credentials` + script seed token lần đầu (đọc từ env, ghi vào DB, chạy 1 lần).
- **DoD:** test refresh khi sắp hết hạn; test 2 coroutine gọi đồng thời → đúng 1 lần refresh; test crash sau khi Zalo trả token mới nhưng trước commit → row cũ giữ nguyên, retry thành công; token không xuất hiện trong log/`repr`.

#### Issue #1.4 — `ZaloOAClient` nhận token provider `blocking-prod`
- `backend/adapters/zalo_oa.py`: `__init__(token_provider: Callable[[], Awaitable[str]])` thay `access_token: str`; `_post` lấy token mỗi lần gửi; **retry 1 lần khi gặp mã lỗi token-hết-hạn** (mã chốt ở #1.1) sau khi force-refresh. Bỏ `get_zalo_oa_client()` đọc settings; giữ shim tương thích cho test cũ.
- **DoD:** test token hết hạn giữa chừng → tự refresh + gửi lại đúng 1 lần; `is_configured` phản ánh có credential trong DB; toàn bộ `tests/test_phase_4b/test_epic4_zalo.py` vẫn xanh (sửa fixture nếu cần, KHÔNG nới assertion).

---

## 🅱️ Epic #E2 — Inbound Pipeline `zalo-inbound`

### Description
Hiện webhook xử lý business ngay trong request, không dedup, và chỉ hiểu token `BT-XXXXXX`. Đưa về đúng contract Telegram: router mỏng → dedup → worker → dispatcher.

### Success criteria (Epic-level)
- Zalo gửi lại cùng `msg_id` → xử lý đúng 1 lần.
- Webhook trả 200 trong ≤100ms (không chờ LLM).
- User đã link gõ text tự nhiên → đi vào intent classifier chung, không phải copy linking.

### Child issues

#### Issue #2.1 — `zalo_updates` dedup table + claim
- `backend/models/zalo_update.py`: PK `msg_id` (String, Zalo cấp), `user_id` nullable + index, `status` (`processing`/`done`/`failed`), `payload` JSONB, `created_at`. Mirror `telegram_updates` kể cả orphan recovery. Nếu payload thiếu `msg_id` → khoá tổng hợp `sha256(app_id|sender|timestamp|text)` (chốt ở #1.1).
- `backend/routers/zalo.py`: `INSERT ... ON CONFLICT (msg_id) DO NOTHING` trước mọi xử lý; trùng → trả 200 ngay.
- **DoD:** migration sạch; test gửi trùng 2 lần → 1 row, 1 lần xử lý; test payload thiếu `msg_id` → fallback khoá tổng hợp vẫn dedup.

#### Issue #2.2 — `zalo_worker` + router mỏng
- `backend/workers/zalo_worker.py`: mở session, resolve user theo `zalo_user_id`, dispatch, `commit()` **một lần** ở biên, đánh dấu `done`/`failed`. `backend/routers/zalo.py`: chỉ verify → claim → `asyncio.create_task` → return 200. Orphan recovery ở lifespan startup như Telegram.
- **DoD:** webhook p95 ≤100ms trong test (LLM mock chậm 2s vẫn không chặn); worker exception → row `failed`, không mất 200; layer-contract-checker sạch (không commit ngoài worker).

#### Issue #2.3 — `zalo_inbound` handler: token flow + intent dispatch
- `backend/bot/handlers/zalo_inbound.py`: chưa link → giữ nguyên luồng token `BT-XXXXXX` của 4B (không đổi hành vi); đã link → gọi intent classifier + dispatcher chung. Intent ngoài whitelist thin-slice (#4.1) → copy `fallback` lịch sự trong `content/zalo.yaml`, KHÔNG lỗi.
- **DoD:** integration test: chưa-link + token → link thành công (regression 4B); đã-link + "ăn trưa 50k" → tạo transaction; đã-link + intent chưa hỗ trợ → copy fallback; mọi output ≤300 ký tự, không Markdown.

---

## 🅲 Epic #E3 — Outbound Discipline `zalo-quota`

### Description
Zalo chỉ cho gửi tối đa **8 tin tư vấn miễn phí trong 48h** kể từ tương tác cuối của user. Hiện mọi outbound gọi thẳng `/message/cs` — job briefing/empathy có thể đốt sạch quota rồi fail-open im lặng.

### Success criteria (Epic-level)
- Ngoài cửa sổ 48h → không gọi API Zalo lần nào.
- Chạm trần 8 tin → dừng Zalo, Telegram vẫn nhận đủ.
- Có metric đếm được: bao nhiêu lần bị chặn, vì lý do gì.

### Child issues

#### Issue #3.1 — `zalo_message_window` model + service
- `backend/models/zalo_message_window.py`: `user_id` NOT NULL indexed, `last_interaction_at`, `window_started_at`, `free_msg_count`. `backend/services/zalo_window_service.py`: `record_inbound()` (mở/reset cửa sổ), `record_outbound()` (tăng đếm), `can_send()` → `(bool, reason)`. Pure/flush-only, hằng số 48h/8 tin lấy từ bảng platform facts (#1.1).
- **DoD:** unit test cửa sổ mở/đóng theo mốc 48h; đếm reset khi user tương tác mới; `can_send` trả đúng `reason` (`window_closed`/`quota_exhausted`/`ok`); dùng UTC nhất quán, test qua mốc timezone Asia/Ho_Chi_Minh.

#### Issue #3.2 — Wire vào `notifier_resolver` + worker
- `backend/services/notifier_resolver.py`: chỉ thêm kênh zalo khi `can_send()` ok. `zalo_worker` gọi `record_inbound()` mỗi tin vào; đường gửi gọi `record_outbound()` sau khi gửi thành công.
- **DoD:** test job proactive khi cửa sổ đóng → 0 request Zalo, Telegram vẫn gửi; test đúng 8 tin rồi tin thứ 9 bị chặn; test user chưa link Zalo → hành vi không đổi.

#### Issue #3.3 — Observability quota
- Log có cấu trúc + counter cho mỗi lần bị chặn (theo `reason`). Endpoint/health snippet đọc `remain`/`total` từ quota API Zalo để đối chiếu đếm nội bộ với thực tế.
- **DoD:** log không chứa nội dung tin nhắn/PII; số đếm nội bộ và quota Zalo lệch >1 → cảnh báo trong runbook.

---

## 🅳 Epic #E4 — Thin Slice + Vận Hành

### Description
Mở đúng 3 luồng thật trên Zalo để validate ràng buộc format (300 ký tự, không Markdown, tối đa 2 emoji) **trước khi** 5.1 đổ toàn bộ sản phẩm sang. Kèm runbook vận hành OA.

### Success criteria (Epic-level)
- 3 luồng chạy end-to-end trên OA thật ở staging.
- Không output nào vỡ format.
- Người vận hành tự xoay token / đăng ký lại webhook được bằng runbook, không cần đọc code.

### Child issues

#### Issue #4.1 — Whitelist intent + copy `persona-critical`
- Chốt danh sách thin-slice (đề xuất: link account, capture chi tiêu, báo cáo ngắn số dư + chi tháng này). `content/zalo.yaml`: thêm `capture`, `report_short`, `fallback`, `window_closed`. Giọng Bé Tiền: ấm, không phán xét, ≤300 ký tự, ≤2 emoji, không Markdown.
- **DoD:** vi-localization-checker pass; 0 chuỗi "Decision Engine/CFO/GPS"; test khẳng định mọi copy Zalo ≤300 ký tự và không chứa `*_~[]()` dạng Markdown; đọc to nghe tự nhiên.

#### Issue #4.2 — Briefing text ngắn cho Zalo
- `backend/adapters/zalo_content_renderer.py`: implement `render_briefing` (text-only, không ảnh — ảnh cần URL public, để 5.1). 3 method còn lại giữ `NotImplementedError` với message trỏ Phase 5.1.
- **DoD:** unit test render briefing từ `BriefingSnapshot` thật; output ≤300 ký tự, không Markdown; gọi `render_twin_view` → raise message rõ ràng, không crash worker (handler bắt và trả copy fallback).

#### Issue #4.3 — Runbook `zalo-operations.md` + xác thực OA
- `docs/conventions/zalo-operations.md`: đăng ký/đổi webhook URL, quy trình xác thực OA (nộp hồ sơ, 3-7 ngày, **chặn 5.2 Mini App**), xoay token thủ công khi refresh_token chết, đọc quota, checklist bật `ZALO_CHANNEL_ENABLED`, soak 48h signature log-only. Kèm bảng platform facts (#1.1).
- **DoD:** runbook có mọi lệnh cần chạy (không nhắc secret cụ thể, chỉ tên biến); có mục "khi nào KHÔNG bật"; cập nhật `docs/current/phase-status.yaml` + chạy `scripts/sync_phase_status.py`.

---

## 🔗 Dependency Graph

```
#1.1 platform facts ──> #1.2 MAC, #1.3 token, #3.1 hằng số cửa sổ
#1.3 credentials ──> #1.4 token provider ──> mọi đường gửi
#2.1 dedup ──> #2.2 worker ──> #2.3 dispatch ──> #4.1 copy, #4.2 briefing
#3.1 window ──> #3.2 resolver ──> #3.3 observability
(nền) hồ sơ xác thực OA nộp ngày 1 ──> Phase 5.2 Mini App
E1 + E2 + E3 ──> soak staging 48h ──> bật ZALO_CHANNEL_ENABLED
```

#1.1 chặn tất cả vì mọi hằng số nền tảng đến từ nó — code trước rồi verify sau là cách nền 4B đã sai 2 lần.
