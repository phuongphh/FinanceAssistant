# Phase 5.1 — Issues Breakdown

> Zalo Core Product Parity: chở toàn bộ sản phẩm (Twin, briefing, advisory, decision queries, asset entry, onboarding) qua đường ống 5.0, với ràng buộc Zalo. GitHub-ready issue list. Detail: [`phase-5.1-detailed.md`](phase-5.1-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E1 | Media URL Infrastructure ⭐ | 4 | P0 (chặn mọi surface có ảnh) | ~3-4 ngày |
| E2 | `ZaloContentRenderer` Đầy Đủ | 4 | P0 (bỏ `NotImplementedError`) | ~4 ngày |
| E3 | Rich Message & Button Mapping | 3 | P0 (không nút nào mất im lặng) | ~2-3 ngày |
| E4 | Intent Parity + Onboarding từ Zalo | 4 | P0 (định nghĩa "parity") | ~4-5 ngày |
| E5 | ZNS cho tin ngoài cửa sổ 48h | 3 | P2 (có điều kiện — owner ký) | ~2-3 ngày |

**Tổng:** 5 Epics / 18 issues. Thứ tự build: E1 → E3 → E2 → E4; E5 song song sau khi owner ký + template nộp duyệt sớm.

**Phụ thuộc cứng:** Phase 5.0 done (token refresh, dedup, `zalo_message_window`) **và** OA đã xác thực (điều kiện của ZNS ở E5).

## 🏷️ Label Conventions
- `phase-5.1`, `epic-1`/`epic-2`/`epic-3`/`epic-4`/`epic-5`
- `media-url` / `zalo-render` / `zalo-buttons` / `zalo-parity` / `zns`
- `persona-critical` (mọi issue chạm copy Bé Tiền — bắt buộc prompt-tester / vi-localization-checker)
- `privacy-critical` (mọi issue chạm URL ảnh public — bắt buộc test hết hạn + không đoán được)
- `platform-verify` (fact về Zalo phải đối chiếu docs chính chủ trước khi code)
- `blocked-owner` (chờ owner ký mới build)

---

## 🅰️ Epic #E1 — Media URL Infrastructure ⭐ `media-url`

### Description
`ChannelContent.images` là `tuple[bytes, ...]` vì Telegram nhận bytes trực tiếp. Zalo **chỉ nhận URL public**. Dựng tầng: publish bytes → URL ký ngắn hạn → endpoint phục vụ → job dọn. Hạ tầng này 5.2 (Mini App) dùng lại, nên thiết kế cho tái sử dụng chứ không nhét riêng vào adapter Zalo.

### Success criteria (Epic-level)
- `media_url_service.publish(bytes, content_type, ttl)` trả URL tuyệt đối truy cập được từ ngoài.
- URL không đoán được (token ngẫu nhiên ≥32 byte), hết hạn trả 404, DB lưu **hash** của token.
- Job dọn xoá mềm object hết hạn; không có object nào sống quá TTL + grace.

### Child issues

#### Issue #1.1 — `media_objects` model + migration `privacy-critical`
- `backend/models/media_object.py`: `id`, `user_id` (UUID NOT NULL, indexed), `token_hash` (String, unique indexed), `content_type`, `byte_size`, `storage_key`, `expires_at`, `created_at`, `deleted_at`. **Lưu hash của token (sha256), KHÔNG lưu token gốc** — DB rò rỉ không đủ để dựng lại URL. Migration mới trong `alembic/versions/`.
- **DoD:** migration up/down sạch; `user_id` NOT NULL + index; unique index trên `token_hash`; soft delete `deleted_at`; test khẳng định không cột nào chứa token gốc.

#### Issue #1.2 — `media_url_service` (publish + resolve) `privacy-critical`
- `backend/services/media_url_service.py`: `publish(user_id, data: bytes, content_type, ttl_seconds) -> str` (lưu bytes vào storage, sinh token `secrets.token_urlsafe(32)`, ghi row với hash, trả URL); `resolve(token) -> bytes | None` (hash → tra row → kiểm `expires_at`/`deleted_at` → đọc storage). **Flush-only, không commit, không đọc env** — base URL và TTL mặc định truyền vào từ edge.
- Storage v1: filesystem dưới thư mục cấu hình được (không commit file vào repo). Interface đủ hẹp để đổi sang object storage sau mà không sửa caller.
- **DoD:** service pure theo layer contract (no commit, no env read); unit test publish→resolve round-trip; token hết hạn → `None`; token sai → `None`; token đã soft-delete → `None`; test khẳng định 2 lần publish cùng bytes cho 2 token khác nhau.

#### Issue #1.3 — `GET /api/v1/media/{token}` router `privacy-critical`
- `backend/routers/media.py`: endpoint no-auth (token tự chứng), gọi `media_url_service.resolve`, trả `Response(content=..., media_type=...)` với header `Cache-Control: no-store` + `X-Content-Type-Options: nosniff`. Hết hạn/không tồn tại → **404 giống hệt nhau** (không phân biệt để tránh dò). Mount trong `backend/main.py`. Rate limit cơ bản theo IP.
- **DoD:** integration test 200 với token hợp lệ, 404 với token hết hạn/sai/đã xoá và **body 404 giống nhau ở cả 3 case**; header `Cache-Control: no-store` có mặt; router không chứa business logic; đo p95 < 100ms cho ảnh ~200KB.

#### Issue #1.4 — Job dọn media hết hạn
- `backend/jobs/cleanup_media.py`: chạy định kỳ (đề xuất hằng giờ), soft-delete row hết hạn + xoá file storage tương ứng. Đăng ký vào scheduler. Đọc cấu hình grace period ở job edge.
- **DoD:** unit test chọn đúng tập row hết hạn (không đụng row còn hạn); file bị xoá khỏi storage; job idempotent (chạy 2 lần không lỗi); log số object dọn được.

---

## 🅱️ Epic #E2 — `ZaloContentRenderer` Đầy Đủ `zalo-render`

### Description
`backend/adapters/zalo_content_renderer.py` hiện là stub — cả 4 method `raise NotImplementedError`. 5.0 đã làm `render_briefing` (text-only). 5.1 làm nốt `render_twin_view`, `render_twin_comparison`, `render_milestone`, và nối ảnh qua `media_url_service`. **Copy viết riêng cho Zalo** — không cắt copy Telegram bằng `truncate_for_zalo`.

### Success criteria (Epic-level)
- 0 `NotImplementedError` trong `ZaloContentRenderer`.
- Ảnh chart Twin hiển thị thật trên Zalo (qua URL từ E1).
- Mọi copy Zalo ≤300 ký tự hiển thị, không Markdown, ≤2 emoji, đọc to nghe tự nhiên.

### Child issues

#### Issue #2.1 — Mở rộng `content/zalo.yaml` `persona-critical`
- Thêm section: `twin` (snapshot p10/p50/p90 + narrative rút gọn), `twin_comparison`, `milestone`, `advisory`, `decision`, `asset_entry`, `onboarding`. Mỗi section có biến thể **3 xưng hô** (anh/chị/bạn) theo `users.salutation`. Copy viết ngắn từ đầu — không phải bản cắt của Telegram. Giữ nguyên header rules đang có trong file (plain text, ~300 ký tự, ≤2 emoji).
- **DoD:** vi-localization-checker pass; prompt-tester × 3 xưng hô cho từng section; 0 chuỗi "Decision Engine"/"CFO"/"GPS tài chính"; 0 ký tự Markdown (`*`, `_`, `` ` ``, `[]()`); mỗi string ≤300 ký tự (test tự động duyệt toàn file).

#### Issue #2.2 — `render_twin_view` + `render_twin_comparison`
- Implement 2 method từ `TwinViewSnapshot` / `TwinComparisonSnapshot`: text ngắn (con số p10/p50/p90 format qua `currency_utils.format_money_short`) + ảnh chart. Trả `ChannelContent` với `images` giữ nguyên bytes — việc đổi sang URL là việc của notifier (#2.4), renderer **không** biết media service.
- **DoD:** unit test snapshot → text đúng con số, đúng xưng hô, ≤300 ký tự; `is_stale=True` render thêm dòng cảnh báo cũ; không dùng `truncate_for_zalo`; renderer pure (không I/O).

#### Issue #2.3 — `render_milestone`
- Implement từ dữ liệu milestone: mốc đạt được + hệ quả Twin ngắn. Giọng ăn mừng nhưng không sáo. Ảnh (nếu có) đi cùng cơ chế #2.4.
- **DoD:** unit test 3 xưng hô; ≤300 ký tự; prompt-tester đánh giá "đọc to không cringy"; test khẳng định không có ngôn ngữ áp lực/trách móc.

#### Issue #2.4 — `ZaloNotifier` xử lý ảnh qua media URL `privacy-critical`
- `backend/adapters/zalo_notifier.py`: khi `ChannelContent.images` không rỗng → gọi `media_url_service.publish` (TTL truyền từ edge, mặc định 15 phút) → `zalo_oa.send_image_message` với URL. Publish thất bại → gửi text-only + log warning, **không** ném lỗi lên trên (giữ fail-open như adapter hiện tại). Bỏ áp `truncate_for_zalo` cho các surface đã có copy riêng ở #2.1.
- **DoD:** integration test ảnh → URL → payload `template_type: "media"` đúng dạng; publish lỗi → vẫn gửi text, có log; test khẳng định surface có copy riêng KHÔNG đi qua `truncate_for_zalo`; adapter không chứa business logic.

---

## 🅲 Epic #E3 — Rich Message & Button Mapping `zalo-buttons`

### Description
Telegram `Button(text, callback_data, web_app_url)` có `callback_data` đi ngược về bot. Zalo có `oa.open.url` (mở link) và `oa.query.show` (gửi lại một câu text thay người dùng). Ánh xạ **mất mát** — phải cố ý, có test, và không bao giờ im lặng nuốt nút.

### Success criteria (Epic-level)
- Mỗi `Button` đầu vào → hoặc một nút Zalo hợp lệ, hoặc một dòng gợi ý text. Không có đường thứ ba.
- `send_message_with_buttons()` gửi được attachment template có nút, hiển thị đúng trên Zalo app.

### Child issues

#### Issue #3.1 — Đối chiếu docs Zalo về button/template `platform-verify`
- Xác nhận với docs chính chủ (`developers.zalo.me`) trước khi code: danh sách button type hợp lệ (`oa.open.url`, `oa.query.show`, `oa.query.hide`, `oa.open.sms`, `oa.open.phone`), số nút tối đa mỗi tin, độ dài title nút, cấu trúc `attachment.payload` cho template có nút, và hành vi thực tế của `oa.query.show` (payload hiện ra như tin của user hay không). Ghi bảng fact đã verify vào `docs/conventions/zalo-operations.md` (file do 5.0 #4.3 tạo).
- **DoD:** bảng fact có mặt trong runbook, mỗi dòng kèm link docs + ngày kiểm; mọi hằng số trong `zalo_button_mapper` trỏ về một dòng trong bảng này; sai lệch so với giả định trong phase doc được ghi lại rõ ràng.

#### Issue #3.2 — `zalo_button_mapper` (pure)
- `backend/adapters/zalo_button_mapper.py`: pure. `map_buttons(rows: tuple[tuple[Button,...],...]) -> tuple[list[dict], list[str]]` — trả (payload nút Zalo, danh sách dòng gợi ý text cho nút không ánh xạ được). Quy tắc: `web_app_url` → `oa.open.url`; `callback_data` → `oa.query.show` với payload là câu người dùng "nói"; vượt số nút tối đa → phần dư thành dòng text. Cắt title nút theo giới hạn đã verify ở #3.1.
- **DoD:** unit test từng nhánh ánh xạ; **test khẳng định `len(nút) + len(dòng text) == len(nút đầu vào)`** (không nút nào biến mất) trên mọi input, kể cả vượt giới hạn; module pure (không I/O, không env).

#### Issue #3.3 — `send_message_with_buttons()` trong `zalo_oa`
- `backend/adapters/zalo_oa.py`: method mới dựng `attachment` template với nút từ #3.2, giữ nguyên cơ chế retry/backoff và fail-open hiện có. `ZaloNotifier` gọi method này khi `ChannelContent.buttons` không rỗng, và **nối các dòng gợi ý text vào cuối phần text** trước khi kiểm giới hạn ký tự.
- **DoD:** integration test payload đúng schema đã verify; test dòng gợi ý xuất hiện trong text gửi đi; tin có nút + dòng gợi ý vẫn ≤ giới hạn ký tự (nếu vượt → ưu tiên giữ nội dung chính, log cảnh báo); giữ nguyên hành vi retry với `-32`/`-239`/429.

---

## 🅳 Epic #E4 — Intent Parity + Onboarding từ Zalo `zalo-parity`

### Description
5.0 chỉ mở whitelist thin-slice (`capture`, `report_short`). 5.1 mở **toàn bộ dispatcher** cho Zalo và cho phép user mới **bắt đầu thẳng từ Zalo**. Đây là điểm biến Zalo từ kênh thông báo thành kênh tăng trưởng. Ràng buộc kiến trúc: **0 nhánh `if channel == "zalo"` trong `backend/services/`**.

### Success criteria (Epic-level)
- Cùng input trên Telegram và Zalo → cùng con số, cùng kết luận (chữ có thể khác).
- User mới đăng ký từ Zalo đi hết onboarding, không cần Telegram.
- `grep -r 'channel == "zalo"' backend/services/` trả 0 kết quả.

### Child issues

#### Issue #4.1 — Mở toàn bộ dispatcher cho `zalo_inbound`
- `backend/bot/handlers/zalo_inbound.py`: bỏ whitelist thin-slice, route mọi intent qua dispatcher chung. Intent nào renderer Zalo chưa phục vụ được → fallback có copy tử tế (không phải lỗi kỹ thuật), log intent để biết còn thiếu gì.
- **DoD:** integration test ≥6 intent chính đi qua Zalo ra kết quả; intent chưa hỗ trợ → copy fallback trong `content/zalo.yaml` (không hardcode); handler đọc flag ở edge; layer-contract-checker sạch.

#### Issue #4.2 — Rà `users.telegram_id` nullable + user chỉ-Zalo
- Kiểm tra schema hiện tại: `telegram_id` có NOT NULL/unique không. Nếu chặn user chỉ-Zalo → migration làm nullable (giữ unique partial cho row non-null). Rà mọi query/service giả định user luôn có `telegram_id`.
- **DoD:** báo cáo danh sách chỗ giả định có Telegram (kể cả nếu kết luận là "không cần migration"); migration sạch nếu có; test suite chạy được với fixture user chỉ có `zalo_user_id`; không query nào nổ `None`.

#### Issue #4.3 — Onboarding bắt đầu từ Zalo `persona-critical`
- `backend/services/zalo_linking_service.py`: tạo user mới từ `zalo_user_id` khi chưa có link và tin đến không phải token `BT-XXXXXX`. Chạy đúng flow onboarding hiện tại (salutation → goal → asset → Twin) qua renderer Zalo. Giữ nguyên luồng redeem token cho user Telegram sẵn có — **không được regress**.
- **DoD:** integration test user mới từ Zalo đi hết onboarding ra Twin; test regression luồng token `BT-XXXXXX` vẫn nguyên; service flush-only; copy onboarding Zalo qua prompt-tester × 3 xưng hô.

#### Issue #4.4 — Parity test suite (chạy trong CI)
- Bộ test bảng: cùng input → chạy qua đường Telegram và đường Zalo → khẳng định **cùng con số và cùng kết luận**, chỉ khác trình bày. Phủ tối thiểu: capture, report, twin view, decision query, advisory, milestone. Thêm assertion CI: 0 file trong `backend/services/` chứa nhánh theo kênh.
- **DoD:** suite xanh trong CI; thất bại khi cố tình đổi một con số ở một kênh (test tự kiểm chứng); assertion "no channel branching in services" chạy như một test, không phải checklist thủ công.

---

## 🅴 Epic #E5 — ZNS cho tin ngoài cửa sổ 48h `zns` `blocked-owner`

### Description
Ngoài cửa sổ 48h không được gửi `/message/cs`. ZNS là đường hợp lệ duy nhất: **template phải được Zalo duyệt trước**, giới hạn ~400 ký tự, tính phí theo tin gửi thành công (OA đã xác thực có hạn mức miễn phí hằng tháng). Epic này **chỉ build sau khi owner ký** Decision #1 trong phase doc. Template nên nộp duyệt sớm vì thời gian xét duyệt tính bằng ngày.

### Success criteria (Epic-level)
- Briefing/cảnh báo ngoài cửa sổ gửi được qua ZNS, hoặc bỏ kênh Zalo **có log lý do** — không bao giờ gọi `/message/cs` ngoài cửa sổ.
- Hạn mức được đếm; hết hạn mức → dừng gửi, không đốt ngân sách ngoài dự tính.

### Child issues

#### Issue #5.1 — Đối chiếu docs ZNS + nộp template duyệt `platform-verify` `blocked-owner`
- Xác nhận với docs chính chủ: endpoint gửi ZNS, cấu trúc `template_id` + `template_data`, giới hạn ký tự thực tế, quy trình + thời gian duyệt, cách tra hạn mức còn lại, bảng giá hiện hành. Soạn 2 template tối thiểu (briefing rút gọn, cảnh báo cashflow) và nộp duyệt. Ghi fact + `template_id` vào `docs/conventions/zalo-operations.md`.
- **DoD:** bảng fact ZNS trong runbook kèm link + ngày kiểm; 2 template đã nộp, trạng thái duyệt ghi lại; ước tính chi phí/tháng theo số user dự kiến trình owner.

#### Issue #5.2 — `zalo_zns` adapter + `zns_service` `persona-critical`
- `backend/adapters/zalo_zns.py`: gửi theo `template_id` + params, retry/backoff + fail-open như `zalo_oa`. `backend/services/zns_service.py`: chọn template theo loại nội dung, đếm hạn mức, quyết định gửi hay bỏ — flush-only, không env. `content/zns_templates.yaml`: map nội dung ↔ `template_id` đã duyệt + tên tham số.
- **DoD:** unit test chọn template đúng; hết hạn mức → trả quyết định "bỏ" + lý do, không gọi API; adapter fail-open không ném lỗi lên job; params khớp schema template đã duyệt; copy trong template qua vi-localization-checker.

#### Issue #5.3 — Nối vào đường proactive + đếm hạn mức
- Job briefing/empathy: `zalo_message_window.can_send()` trả `window_closed` → hỏi `zns_service`; gửi được thì gửi, không thì bỏ kênh Zalo và log. Thêm `zns_send_log` (`user_id` NOT NULL) nếu cần audit + đếm hạn mức chính xác. Đếm hạn mức reset theo tháng.
- **DoD:** integration test 3 nhánh (trong cửa sổ → `/message/cs`; ngoài cửa sổ + có template + còn hạn mức → ZNS; ngoài cửa sổ + hết hạn mức → bỏ có log); **test khẳng định không bao giờ gọi `/message/cs` khi `window_closed`**; metric hạn mức đã dùng/còn lại quan sát được.

---

## 🔗 Dependency Graph

```
E1 #1.1 → #1.2 → #1.3 → #1.4        (media URL: model → service → router → job)
E1 ──────────────> E2 #2.4          (notifier cần URL mới gửi được ảnh)
E3 #3.1 → #3.2 → #3.3 ──> E2 #2.4   (notifier gắn nút + dòng gợi ý)
E2 #2.1 → #2.2, #2.3                (copy trước, renderer sau)
E2 ──────────────> E4 #4.1          (mở dispatcher khi renderer đã phục vụ được)
E4 #4.2 ──> #4.3                    (nullable trước, onboarding-từ-Zalo sau)
E4 #4.1 + #4.3 ──> #4.4             (parity suite chốt Epic)
E5 #5.1 (nộp template — làm SỚM, song song) ──> #5.2 ──> #5.3
```

E1 đi trước vì Twin và briefing đều có ảnh — làm renderer trước sẽ phải viết lại phần gửi. E3 #3.1 và E5 #5.1 là hai issue `platform-verify`/nộp duyệt, khởi động sớm nhất có thể vì phụ thuộc bên ngoài (docs Zalo, thời gian xét duyệt template) chứ không phụ thuộc code.
