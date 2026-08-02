# Phase 5.1 — Issues Breakdown

> Zalo Core Product Parity: chở toàn bộ sản phẩm (Twin, briefing, advisory, decision queries, asset entry, onboarding) qua đường ống 5.0, với ràng buộc Zalo. GitHub-ready issue list. Detail: [`phase-5.1-detailed.md`](phase-5.1-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E1 | Media URL Infrastructure ⭐ | 4 | P0 (chặn mọi surface có ảnh) | ~3-4 ngày |
| E2 | `ZaloContentRenderer` Đầy Đủ | 4 | P0 (bỏ `NotImplementedError`) | ~4 ngày |
| E3 | Rich Message & Button Mapping | 3 | P0 (không nút nào mất im lặng) | ~2-3 ngày |
| E4 | Intent Parity + Onboarding từ Zalo | 5 | P0 (định nghĩa "parity") | ~5-6 ngày |

**Tổng:** 4 Epics / 16 issues. Thứ tự build: E1 → E3 → E2 → E4.

> ✅ **Chốt 02/08/2026 — Epic E5 (ZNS) đã loại.** Owner chốt không chi tiền cho ZNS và không nhận ràng buộc template duyệt trước. **Zalo là kênh reactive-first**: chỉ nói khi user vừa nói, trong cửa sổ 48h; toàn bộ proactive (briefing, empathy, cảnh báo) giữ trên **Telegram**. 3 issue #5.1-#5.3 bị huỷ. Phần bù duy nhất là **#4.5** (kể lại phần bỏ lỡ khi user chỉ-Zalo quay lại), nằm trong E4.

**Phụ thuộc cứng:** Phase 5.0 done (token refresh, dedup, `zalo_message_window`). Xác thực OA **không còn** là phụ thuộc của 5.1 (nó chỉ chặn Mini App 5.2).

## 🏷️ Label Conventions
- `phase-5.1`, `epic-1`/`epic-2`/`epic-3`/`epic-4`
- `media-url` / `zalo-render` / `zalo-buttons` / `zalo-parity`
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
- ⚠️ **Rò rỉ file mồ côi khi rollback:** service flush-only nên `publish()` ghi bytes ra storage *ngay* nhưng row `media_objects` chỉ tồn tại sau khi caller commit. Caller rollback/crash giữa chừng → **file nằm lại trên đĩa mà không có row nào trỏ tới**, và job dọn (#1.4) quét theo row nên **không bao giờ tìm thấy** — biểu đồ tài chính của user nằm vĩnh viễn trên đĩa. Bắt buộc chọn 1 trong 2: (a) **ghi row trước, ghi bytes sau** — `publish()` chỉ flush row (trạng thái `pending`), bytes được ghi ở edge sau khi commit thành công; hoặc (b) **quét theo storage** — #1.4 liệt kê file trên storage, đối chiếu ngược với DB, xoá file không có row và cũ hơn grace period. (b) rẻ hơn để làm ngay, (a) sạch hơn về lâu dài — chốt trong PR.
- **DoD:** service pure theo layer contract (no commit, no env read); unit test publish→resolve round-trip; token hết hạn → `None`; token sai → `None`; token đã soft-delete → `None`; test khẳng định 2 lần publish cùng bytes cho 2 token khác nhau; **test: publish rồi rollback → không còn file mồ côi sau khi job dọn chạy** (test này là điều kiện đủ cho cả 2 phương án trên).

#### Issue #1.3 — `GET /api/v1/media/{token}` router `privacy-critical`
- `backend/routers/media.py`: endpoint no-auth (token tự chứng), gọi `media_url_service.resolve`, trả `Response(content=..., media_type=...)` với header `Cache-Control: no-store` + `X-Content-Type-Options: nosniff`. Hết hạn/không tồn tại → **404 giống hệt nhau** (không phân biệt để tránh dò). Mount trong `backend/main.py`. Rate limit cơ bản theo IP.
- **DoD:** integration test 200 với token hợp lệ, 404 với token hết hạn/sai/đã xoá và **body 404 giống nhau ở cả 3 case**; header `Cache-Control: no-store` có mặt; router không chứa business logic; đo p95 < 100ms cho ảnh ~200KB.

#### Issue #1.4 — Job dọn media hết hạn
- `backend/jobs/cleanup_media.py`: chạy định kỳ (đề xuất hằng giờ), soft-delete row hết hạn + xoá file storage tương ứng. Đăng ký vào scheduler. Đọc cấu hình grace period ở job edge.
- **Quét cả file mồ côi** (nếu #1.2 chọn phương án (b)): liệt kê storage, file không có row `media_objects` tương ứng **và** mtime cũ hơn grace period → xoá. Grace period phải dài hơn khoảng cách publish→commit dài nhất để không xoá nhầm file đang chờ commit.
- **DoD:** unit test chọn đúng tập row hết hạn (không đụng row còn hạn); file bị xoá khỏi storage; **test file mồ côi (có file, không có row) bị dọn sau grace period, và KHÔNG bị dọn khi còn trong grace period**; job idempotent (chạy 2 lần không lỗi); log số object dọn được, tách riêng số row-driven và số orphan.

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
- User chỉ-Zalo quay lại sau khi cửa sổ đóng → nhận **một** dòng catch-up, không bị dội tin cũ.
- `grep -r 'channel == "zalo"' backend/services/` trả 0 kết quả.

### Child issues

#### Issue #4.1 — Mở toàn bộ dispatcher cho `zalo_inbound`
- `backend/bot/handlers/zalo_inbound.py`: bỏ whitelist thin-slice, route mọi intent qua dispatcher chung. Intent nào renderer Zalo chưa phục vụ được → fallback có copy tử tế (không phải lỗi kỹ thuật), log intent để biết còn thiếu gì.
- **DoD:** integration test ≥6 intent chính đi qua Zalo ra kết quả; intent chưa hỗ trợ → copy fallback trong `content/zalo.yaml` (không hardcode); handler đọc flag ở edge; layer-contract-checker sạch.

#### Issue #4.2 — Rà `users.telegram_id` nullable + user chỉ-Zalo
- Kiểm tra schema hiện tại: `telegram_id` có NOT NULL/unique không. Nếu chặn user chỉ-Zalo → migration làm nullable (giữ unique partial cho row non-null). Rà mọi query/service giả định user luôn có `telegram_id`.
- ⚠️ **Đã xác minh 1 chỗ vỡ chắc chắn — Pydantic response schema admin:** `backend/api/admin/users.py` khai báo `telegram_id: int` **bắt buộc, không nullable** trong cả `AdminUserListItem` và `AdminUserDetailResponse`. User chỉ-Zalo (telegram_id NULL) lọt vào list → Pydantic `ValidationError` lúc serialize → **500 làm hỏng cả trang danh sách user của admin**, không chỉ 1 row. Sửa thành `telegram_id: int | None = None` trong cùng PR với migration, và rà thêm mọi Pydantic schema/`response_model` khác có `telegram_id` non-optional.
- **DoD:** báo cáo danh sách chỗ giả định có Telegram (kể cả nếu kết luận là "không cần migration"); migration sạch nếu có; **test admin list + admin detail với user chỉ-Zalo → 200, không ValidationError**; test suite chạy được với fixture user chỉ có `zalo_user_id`; không query nào nổ `None`.

#### Issue #4.3 — Onboarding bắt đầu từ Zalo `persona-critical`
- `backend/services/zalo_linking_service.py`: tạo user mới từ `zalo_user_id` khi chưa có link và tin đến không phải token `BT-XXXXXX`. Chạy đúng flow onboarding hiện tại (salutation → goal → asset → Twin) qua renderer Zalo. Giữ nguyên luồng redeem token cho user Telegram sẵn có — **không được regress**.
- **Mời link Telegram đúng một lần:** vì Zalo là reactive-first (chốt 02/08/2026), user chỉ-Zalo sẽ không nhận briefing/cảnh báo khi im lặng >48h. Cuối onboarding Zalo, mời link Telegram **một lần**, nói thật lý do bằng giọng Bé Tiền ("để em nhắc anh/chị được cả khi mình bận"), có đường từ chối rõ ràng và **không hỏi lại**. Ghi lựa chọn để không nhắc lần hai.
- **DoD:** integration test user mới từ Zalo đi hết onboarding ra Twin; test regression luồng token `BT-XXXXXX` vẫn nguyên; service flush-only; copy onboarding Zalo qua prompt-tester × 3 xưng hô; **test khẳng định lời mời link Telegram xuất hiện tối đa 1 lần/user** và từ chối rồi thì không bao giờ hiện lại; copy lời mời không mang giọng nài ép/hù doạ (vi-localization-checker + prompt-tester).

#### Issue #4.4 — Parity test suite (chạy trong CI)
- Bộ test bảng: cùng input → chạy qua đường Telegram và đường Zalo → khẳng định **cùng con số và cùng kết luận**, chỉ khác trình bày. Phủ tối thiểu: capture, report, twin view, decision query, advisory, milestone. Thêm assertion CI: 0 file trong `backend/services/` chứa nhánh theo kênh.
- **DoD:** suite xanh trong CI; thất bại khi cố tình đổi một con số ở một kênh (test tự kiểm chứng); assertion "no channel branching in services" chạy như một test, không phải checklist thủ công.

#### Issue #4.5 — Catch-up cho user chỉ-Zalo `persona-critical`
- Hệ quả trực tiếp của chốt reactive-first: proactive rơi ngoài cửa sổ 48h **bị bỏ**, và user chỉ-Zalo không có Telegram để gánh. `backend/services/zalo_catchup_service.py`: khi user chỉ-Zalo nhắn lại sau khoảng im lặng, gom những gì đã bỏ lỡ (briefing/cảnh báo trong N ngày gần nhất, đề xuất N=3) thành **đúng một dòng ngắn** kèm vào phản hồi đầu tiên — không phát lại từng tin, không mở màn bằng catch-up nếu user đang hỏi việc khác gấp. Copy ở `content/zalo.yaml` section `catchup`, 3 xưng hô. Flush-only, không env.
- **Trạng thái:** ưu tiên dựng lại nội dung bỏ lỡ **từ dữ liệu sẵn có** (briefing sinh theo ngày). Chỉ thêm bảng `zalo_missed_notice` (`user_id` NOT NULL indexed) nếu không dựng lại được — chốt trong PR, không thêm bảng theo quán tính.
- **DoD:** integration test user chỉ-Zalo im lặng 5 ngày → nhắn lại → nhận **tối đa 1** dòng catch-up; test user có Telegram **không** nhận catch-up (đã nhận qua Telegram rồi); test không có gì bỏ lỡ → không có dòng thừa; copy qua prompt-tester × 3 xưng hô, **0 giọng trách móc** ("mấy hôm nay anh/chị đi đâu mất tiêu" ❌); tổng tin vẫn ≤300 ký tự.

---

## ~~🅴 Epic #E5 — ZNS cho tin ngoài cửa sổ 48h~~ — **ĐÃ LOẠI 02/08/2026**

Owner chốt: **không làm ZNS** (tốn tiền, template cứng phải duyệt trước). Zalo là kênh **reactive-first** — chỉ nói khi user vừa nói, trong cửa sổ 48h/8 tin; toàn bộ proactive giữ trên **Telegram**.

**Huỷ:** #5.1 (đối chiếu docs ZNS + nộp template), #5.2 (`zalo_zns` + `zns_service`), #5.3 (nối vào đường proactive + đếm hạn mức). Không tạo `backend/adapters/zalo_zns.py`, `backend/services/zns_service.py`, `content/zns_templates.yaml`, bảng `zns_send_log`.

**Ràng buộc thay thế (áp vào E4 và mọi job proactive):**
- `window_closed` → bỏ kênh Zalo + log lý do. Không có nhánh thứ hai. Test khẳng định repo **không** chứa đường gửi tin Zalo ngoài `/message/cs`.
- Phần bù cho user chỉ-Zalo: **#4.5** (catch-up khi quay lại) + lời mời link Telegram một lần ở **#4.3**.
- Mở lại quyết định này chỉ bằng **số liệu** (retention cohort chỉ-Zalo thấp hơn rõ rệt cohort có-Telegram), không bằng cảm tính.

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
E4 #4.3 ──> #4.5                    (biết ai là user chỉ-Zalo rồi mới catch-up được)
```

E1 đi trước vì Twin và briefing đều có ảnh — làm renderer trước sẽ phải viết lại phần gửi. E3 #3.1 là issue `platform-verify`, khởi động sớm nhất có thể vì phụ thuộc bên ngoài (docs Zalo) chứ không phụ thuộc code.
