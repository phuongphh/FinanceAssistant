# Phase 5.2 — Issues Breakdown

> Zalo Mini App: dashboard tương tác (Twin, tài sản, chi tiêu, dòng tiền) chạy trong Zalo dưới dạng bundle tĩnh, xác thực bằng access token của `zmp-sdk` (KHÔNG phải initData). GitHub-ready issue list. Detail: [`phase-5.2-detailed.md`](phase-5.2-detailed.md).

## 📊 Tổng Quan

| Epic | Tên | Issues | Ưu tiên | Ước lượng |
|---|---|---|---|---|
| E1 | Xác thực Zalo Mini App ⭐ | 4 | P0 (chặn mọi màn hình) | ~4 ngày |
| E2 | API-only hoá màn hình | 3 | P0 (bundle tĩnh không có HTML server) | ~3 ngày |
| E3 | Client Mini App (`zmp-sdk`) | 5 | P0 | ~6-7 ngày |
| E4 | Đường vào & deep link | 2 | P1 | ~2 ngày |
| E5 | Hồ sơ, xét duyệt & vận hành | 3 | P0 (phụ thuộc bên ngoài — làm sớm) | ~2 ngày + thời gian chờ duyệt |

**Tổng:** 5 Epics / 17 issues. Thứ tự build: E5 #5.1 khởi động ngày 1 → E1 → E2 → E3 → E4.

**Phụ thuộc cứng:** Phase 5.1 done (media URL + parity) **và** OA đã xác thực, không bị hạn chế — điều kiện Zalo đặt ra để được triển khai Mini App.

## 🏷️ Label Conventions
- `phase-5.2`, `epic-1`/`epic-2`/`epic-3`/`epic-4`/`epic-5`
- `zalo-miniapp-auth` / `miniapp-api` / `miniapp-client` / `miniapp-entry` / `zalo-ops`
- `security-critical` (mọi issue chạm xác thực, cache token, CORS — bắt buộc test đa người dùng)
- `persona-critical` (mọi issue chạm copy Bé Tiền)
- `platform-verify` (fact về Zalo Mini App phải đối chiếu docs chính chủ trước khi code)
- `regression-guard` (mọi issue chạm đường Telegram Mini App đang chạy production)

---

## 🅰️ Epic #E1 — Xác thực Zalo Mini App ⭐ `zalo-miniapp-auth`

### Description
Telegram ký `initData` bằng bot token, server verify **offline** (`backend/miniapp/auth.py`). Zalo không có cơ chế tương đương: client gọi `getAccessToken()` từ `zmp-sdk`, server phải **gọi ngược Zalo** để xác thực token và lấy `zalo_user_id`. Một network call nằm trong đường xác thực → cần cache, timeout ngắn, và xử lý Zalo down mà **không fail-open**.

### Success criteria (Epic-level)
- Token hợp lệ → resolve đúng user qua `users.zalo_user_id`; token sai/hết hạn/`"DEFAULT ACCESS TOKEN"` → 401.
- Zalo API chậm/down → 503 có copy tử tế, **không** cho qua.
- Đường Telegram Mini App byte-identical so với trước 5.2.

### Child issues

#### Issue #1.1 — Đối chiếu docs Zalo Mini App auth `platform-verify` `security-critical`
- Xác nhận với docs chính chủ trước khi code: API `getAccessToken()` (phiên bản `zmp-sdk` tối thiểu, điều kiện trả token thật vs `"DEFAULT ACCESS TOKEN"`), **endpoint + tham số chính xác** để server xác thực token và lấy user id, thời hạn token, cơ chế xin quyền dữ liệu cá nhân, và giới hạn dung lượng bundle (ảnh hưởng lựa chọn thư viện biểu đồ ở E3). Ghi bảng fact vào mục Mini App của `docs/conventions/zalo-operations.md`.
- **DoD:** bảng fact trong runbook, mỗi dòng kèm link docs + ngày kiểm; mọi hằng số/endpoint trong `zalo_auth.py` trỏ về một dòng trong bảng; sai lệch so với giả định trong phase doc ghi lại rõ ràng.

#### Issue #1.2 — `backend/miniapp/zalo_auth.py` (verify + cache) `security-critical`
- Module mới: `verify_zalo_access_token(token) -> str | None` (trả `zalo_user_id`). Gọi Zalo với timeout ≤2s, phân biệt rõ 3 kết quả: **hợp lệ** / **không hợp lệ** / **không xác định được** (network lỗi). Từ chối thẳng chuỗi `"DEFAULT ACCESS TOKEN"`. Cache trong Redis: khoá = `sha256(token)`, giá trị = `zalo_user_id`, TTL ngắn (đề xuất 5 phút) — **không cache kết quả "không xác định được"**.
- **DoD:** unit test 4 nhánh (hợp lệ / không hợp lệ / `"DEFAULT ACCESS TOKEN"` / network lỗi); test khẳng định khoá cache là hash chứ không phải token gốc; **test đa người dùng: token A không bao giờ resolve ra user B**; timeout được áp thật (test với stub chậm).

#### Issue #1.3 — Dependency xác thực đa kênh trong `miniapp/routes.py` `regression-guard` `security-critical`
- Thay `require_miniapp_auth` cứng bằng dependency chọn theo header: có `X-Telegram-Init-Data` → đường cũ **nguyên vẹn**; có `X-Zalo-Access-Token` → `zalo_auth`. Trả về cùng shape `auth: dict` để `_resolve_user` không phải rẽ nhánh nhiều. Với Zalo: tra `users.zalo_user_id`, **không tìm thấy → 401 kèm mã lỗi để client hiện copy hướng dẫn nhắn OA** — không tự tạo user (khác 5.1 #4.3, ở đó user đến từ chat). Gate `ZALO_MINIAPP_ENABLED` đọc ở edge.
- **DoD:** test regression toàn bộ endpoint `/miniapp/api/*` với header Telegram → hành vi không đổi; test Zalo token hợp lệ + user đã liên kết → 200; chưa liên kết → 401 có mã lỗi; cả hai header cùng lúc → chọn một quy tắc rõ ràng và có test; flag off → header Zalo bị từ chối.

#### Issue #1.4 — CORS cho origin Mini App Zalo `security-critical`
- `backend/main.py`: hiện `allow_origins=[settings.admin_allowed_origin]`. Thêm origin Mini App Zalo qua biến cấu hình **riêng** (`zalo_miniapp_allowed_origin`), không dùng chung với admin, **không** `*`. Cho phép header `X-Zalo-Access-Token`. Thêm `zalo_miniapp_enabled`, `zalo_miniapp_app_id` vào `backend/config/__init__.py`.
- **DoD:** integration test origin hợp lệ qua được preflight; origin lạ bị chặn; `allow_origins` không chứa `*` (test khẳng định); biến chưa cấu hình → không mở thêm origin nào.

---

## 🅱️ Epic #E2 — API-only Hoá Màn Hình `miniapp-api`

### Description
Mini App Telegram hiện có màn hình sống bằng HTML server-render (`/miniapp/wealth`, `/miniapp/cashflow`, `/miniapp/twin`). Bundle tĩnh của Zalo **không dùng được đường đó** — mọi màn hình phải chạy chỉ với JSON. Nguyên tắc cứng: **không fork endpoint theo kênh**; thiếu dữ liệu thì bổ sung field cho endpoint chung, không tạo `/zalo-miniapp/api/*`.

### Success criteria (Epic-level)
- 4 màn hình dựng được đầy đủ chỉ từ JSON API, không cần HTML server.
- Hợp đồng dữ liệu của endpoint đang có **không thay đổi phá vỡ** (Telegram đang dùng production).

### Child issues

#### Issue #2.1 — Kiểm kê khoảng trống API `regression-guard`
- Rà từng màn hình (`twin`, `wealth`, `expense`, `cashflow`): liệt kê dữ liệu HTML server đang chèn sẵn mà JSON API chưa trả. Ra một bảng "màn hình × field thiếu × endpoint sẽ bổ sung". Đây là issue **khảo sát**, không code.
- **DoD:** bảng kiểm kê trong `docs/current/phase-5.2/`; mỗi field thiếu gắn với một issue con cụ thể; khẳng định rõ endpoint nào **không** cần đổi.

#### Issue #2.2 — Bổ sung endpoint/field còn thiếu
- Theo bảng #2.1: thêm field vào response đang có (chỉ **thêm**, không đổi/xoá) hoặc thêm endpoint JSON mới cho màn hình chưa có. Business logic gọi service sẵn có — **0 thay đổi trong `backend/services/`**.
- **DoD:** test regression khẳng định mọi field cũ còn nguyên tên + kiểu; field mới có test; `git diff --stat backend/services/` rỗng; layer-contract-checker sạch.

#### Issue #2.3 — Test hợp đồng API (chạy CI)
- Bộ test khoá hợp đồng JSON của các endpoint Mini App dùng (snapshot schema: tên field, kiểu, nullable). Mục đích: hai codebase frontend không trôi dạt âm thầm khi backend đổi.
- **DoD:** suite xanh trong CI; cố tình đổi tên một field → test đỏ (tự kiểm chứng); tài liệu ngắn chỉ cách cập nhật snapshot khi đổi hợp đồng có chủ ý.

---

## 🅲 Epic #E3 — Client Mini App (`zmp-sdk` + `zmp-ui`) `miniapp-client`

### Description
Dự án frontend thứ hai: `zalo-miniapp/`, build tĩnh, deploy qua `zmp-cli`. Chấp nhận có chủ đích (Owner Decision #2) — ranh giới là **hợp đồng API**, không phải code dùng chung. Client là vỏ hiển thị: **không tính toán tài chính phía client**.

### Success criteria (Epic-level)
- 4 màn hình chạy thật trong Zalo với dữ liệu thật.
- Bundle nằm trong giới hạn dung lượng đã verify ở #1.1.
- Không có phép tính tiền nào trong client (số liệu lấy nguyên từ API).

### Child issues

#### Issue #3.1 — Khởi tạo dự án `zalo-miniapp/` + `api.ts`
- Scaffold `zmp-sdk` + `zmp-ui`, cấu hình build, `.gitignore` cho artifact. `src/api.ts`: gọi `getAccessToken()`, gắn header `X-Zalo-Access-Token`, xử lý 401 (hiện copy hướng dẫn liên kết) và 503 (hiện copy bảo trì + nút quay lại chat). Token dev qua biến môi trường, **không** bypass xác thực.
- **DoD:** `npm run build` ra bundle; `zmp deploy` chạy được lên bản thử; 401/503 hiện đúng copy (lấy từ file copy tập trung, không hardcode rải rác); không commit token/secret.

#### Issue #3.2 — Màn hình Twin `persona-critical`
- Dựng từ API Twin: p10/p50/p90, narrative, cone. Ảnh chart dùng media URL từ 5.1 E1 hoặc vẽ client — chọn theo giới hạn bundle ở #1.1, ghi lý do trong PR.
- **DoD:** khớp con số với bản Telegram (test hợp đồng + kiểm tay); `is_stale` hiện cảnh báo; copy qua vi-localization-checker; 0 "Decision Engine/CFO/GPS".

#### Issue #3.3 — Màn hình Tài sản + Dòng tiền
- Hai màn hình đọc từ endpoint tương ứng. Định dạng tiền hiển thị lấy **nguyên chuỗi từ API** nếu API đã format; nếu client phải format thì dùng đúng quy ước `format_money_short` (45k / 1.5tr / 1.2 tỷ) và có test.
- **DoD:** số liệu khớp bản Telegram; test format tiền theo 4 mốc độ lớn; không có phép cộng/trừ tiền trong client (review khẳng định).

#### Issue #3.4 — Màn hình Chi tiêu (đọc + sửa/xoá)
- Danh sách + breakdown; sửa/xoá dùng endpoint đã có (`PATCH`/`DELETE /miniapp/api/expenses/{id}`). Nhập tài sản nhiều bước **không** làm ở v1 (Owner Decision #1).
- **DoD:** sửa/xoá chạy thật, lỗi hiện thông báo tử tế; test khẳng định client không gọi endpoint ngoài danh sách cho phép; copy qua vi-localization-checker.

#### Issue #3.5 — Điều hướng + đường quay lại chat `persona-critical`
- Thanh điều hướng 4 màn hình; mỗi màn hình có **một hành động tiếp theo bằng chữ** và đường quay lại chat OA. Mini App là phòng xem chi tiết, không phải nơi ở.
- **DoD:** mọi màn hình có đường về chat; copy hành động tiếp theo qua prompt-tester × 3 xưng hô; điều hướng chạy được khi vào từ deep link (phối hợp #4.2).

---

## 🅳 Epic #E4 — Đường Vào & Deep Link `miniapp-entry`

### Description
User vào Mini App từ: nút trong tin OA, QR, link chia sẻ `zalo.me/s/<appId>`. Deep link có tham số phải mở **đúng màn hình**, không đổ hết về trang chủ.

### Child issues

#### Issue #4.1 — URL helper + nút mở Mini App `persona-critical`
- `backend/miniapp/urls.py`: thêm helper URL Mini App Zalo (song song helper Telegram hiện có, cùng quy ước `source` để quy công funnel). `backend/adapters/zalo_button_mapper.py`: nút mở Mini App ánh xạ sang `oa.open.url`. `content/zalo.yaml`: copy lời mời mở Mini App.
- **DoD:** unit test helper trả `None` khi chưa cấu hình (giống hành vi Telegram hiện tại); nút hiện đúng trong tin OA; copy qua vi-localization-checker; tham số `source` có mặt để đo.

#### Issue #4.2 — Deep link route tới đúng màn hình `platform-verify`
- Xử lý tham số deep link (`sh_type` / `sh_data` base64 — **verify lại định dạng ở docs chính chủ trước khi code**) → route tới màn hình tương ứng trong client. Dữ liệu nhúng trong deep link chỉ được là **định danh màn hình + tham số vô hại** (ví dụ tháng cần xem), **tuyệt đối không** nhúng dữ liệu tài chính hay định danh nhạy cảm.
- **DoD:** test 4 loại deep link mở đúng màn hình; tham số rác → về trang chủ, không lỗi trắng; test khẳng định payload deep link không chứa số tiền/định danh cá nhân; định dạng đã đối chiếu docs (ghi vào runbook).

---

## 🅴 Epic #E5 — Hồ Sơ, Xét Duyệt & Vận Hành `zalo-ops`

### Description
Xét duyệt là phần của lịch, không phải rủi ro cuối: OA xác thực 3-7 ngày, hồ sơ Mini App 3-5 ngày làm việc, kiểm duyệt nội dung nghiêm. **#5.1 khởi động ngày 1**, song song build.

### Child issues

#### Issue #5.1 — Nộp hồ sơ Mini App `platform-verify`
- Xác nhận điều kiện triển khai (OA đã xác thực, không bị hạn chế), chuẩn bị hồ sơ: mô tả tính năng tiếng Việt, ảnh màn hình, chính sách dữ liệu cá nhân, phạm vi quyền xin của user. Rà toàn bộ copy hồ sơ theo cấm kỵ CLAUDE.md. Nộp và theo dõi trạng thái.
- **DoD:** hồ sơ đã nộp, trạng thái + ngày ghi trong runbook; 0 "Decision Engine/CFO/GPS" trong mọi văn bản nộp; danh sách quyền xin được liệt kê tối thiểu-cần-thiết và có lý do từng quyền.

#### Issue #5.2 — Runbook deploy + rollback Mini App
- Mục Mini App trong `docs/conventions/zalo-operations.md`: quy trình `zmp deploy`, cách kiểm tra bản đang chạy, cách rollback về bản trước, cách tắt khẩn cấp (`ZALO_MINIAPP_ENABLED=false` + hệ quả với user đang mở app), ai được deploy.
- **DoD:** runbook có mặt; thao tác rollback đã diễn tập một lần và ghi lại kết quả; nêu rõ tắt flag khiến Mini App hiện màn hình bảo trì chứ không lỗi trắng.

#### Issue #5.3 — CI build bundle + phase-status sync
- `.github/workflows/*`: build `zalo-miniapp/` trong CI (bắt lỗi TypeScript + kiểm dung lượng bundle so với giới hạn đã verify). Cập nhật `docs/current/phase-status.yaml` (5.2 status/detail_doc/issues_doc) + chạy `scripts/sync_phase_status.py`.
- **DoD:** CI đỏ khi build client lỗi hoặc bundle vượt giới hạn; phase-status.yaml trỏ đúng doc, không còn `skeleton: true`; sync render sạch vào CLAUDE.md/README.

---

## 🔗 Dependency Graph

```
E5 #5.1 (nộp hồ sơ — NGÀY 1, không phụ thuộc code)
E1 #1.1 (verify docs) → #1.2 (zalo_auth) → #1.3 (dependency đa kênh) → #1.4 (CORS)
E1 ──────────────> E3 #3.1 (client gọi API thật; trước đó dùng mock)
E2 #2.1 (kiểm kê) → #2.2 (bổ sung field) → #2.3 (test hợp đồng)
E2 ──────────────> E3 #3.2, #3.3, #3.4
E3 #3.1 → #3.2, #3.3, #3.4 → #3.5
E3 #3.5 + E4 #4.1 ──> #4.2 (deep link route)
E3 + E4 ──> E5 #5.2 (runbook), #5.3 (CI + phase-status)
```

E1 đi trước mọi thứ vì không xác thực được thì không màn hình nào có dữ liệu. E5 #5.1 chạy song song từ ngày đầu vì thời gian chờ duyệt nằm ngoài tầm kiểm soát — phát hiện muộn rằng OA chưa đủ điều kiện sẽ chặn toàn bộ phase.
