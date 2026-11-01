# Phase 5.2 — Zalo Mini App

> Đưa dashboard tương tác (Twin, tài sản, chi tiêu, dòng tiền) vào Zalo dưới dạng **Zalo Mini App**. Đây **không** phải port một trang web — Mini App Zalo là **bundle tĩnh chạy trên hạ tầng Zalo**, không phải HTML server render từ FastAPI như Mini App Telegram hiện tại. Issue list: [`phase-5.2-issues.md`](phase-5.2-issues.md).

**Chốt lịch:** Tháng 11-12/2026, ~3-4 tuần. **Phụ thuộc cứng:** Phase 5.1 xong (media URL + parity) và **OA đã xác thực, không bị hạn chế** — Zalo chỉ cho phép Mini App triển khai dưới một OA đã xác thực.

**Trạng thái build:** chưa bắt đầu. Toàn bộ nằm sau `ZALO_MINIAPP_ENABLED` (mặc định false).

---

## 📋 Changelog vs Strategy V4

| Nguồn | Điều khoản | Ảnh hưởng 5.2 |
|---|---|---|
| Roadmap 5.2 | "Zalo Mini App — dashboard tương tác trong Zalo" | Phạm vi |
| phase-status.yaml (5.2 cũ) | "initData verification trên Zalo SDK" | **Sai — Zalo KHÔNG có initData.** Đã sửa mô tả; xem §Design Philosophy #2 |
| Ladder of Engagement | Mini App là bậc "xem sâu", không phải bậc đầu | Mini App bổ sung chat, không thay thế |
| CLAUDE.md layer contract | Business logic ở backend, client là vỏ | Mini App gọi API, không tự tính |

---

## 🧠 Design Philosophy

1. **Mini App Zalo là *ứng dụng tĩnh*, không phải trang web của mình.** Mini App Telegram hiện tại là HTML server-render từ `backend/miniapp/routes.py` (`/miniapp/wealth`, `/miniapp/twin`…). Zalo triển khai bundle qua `zmp deploy` lên hạ tầng Zalo. Hệ quả kiến trúc: **mọi màn hình Zalo phải chạy được chỉ với JSON API** — không còn đường "trả HTML kèm dữ liệu". Phần API đã có sẵn một nửa (`/miniapp/api/*`), phần render server thì không tái dùng được.
2. **Không có `initData`.** Telegram ký `initData` bằng bot token, server verify offline (`backend/miniapp/auth.py`). Zalo dùng `getAccessToken()` từ `zmp-sdk` phía client, và server phải **gọi ngược Zalo để xác thực token** — tức là một network call trong đường xác thực. Khác biệt này kéo theo: cần cache token đã verify, cần xử lý Zalo API down, cần timeout ngắn. Đây là rủi ro vận hành mới, không phải chi tiết nhỏ.
3. **Cross-origin từ ngày đầu.** Mini App chạy từ origin của Zalo, gọi API của mình → CORS thật (hiện `allow_origins=[settings.admin_allowed_origin]` — một origin duy nhất). Phải mở đúng origin, không mở `*`, và tách khỏi cấu hình admin.
4. **Một API, hai vỏ.** Không được fork endpoint theo kênh. Nếu `/miniapp/api/overview` cần đổi để phục vụ Zalo → đổi cho cả hai, hoặc thêm field. **Không** tạo `/zalo-miniapp/api/overview`.
5. **Xét duyệt là một phần của lịch, không phải rủi ro cuối.** OA xác thực 3-7 ngày; hồ sơ Mini App duyệt 3-5 ngày làm việc; kiểm duyệt nội dung nghiêm. Nộp hồ sơ **song song với build**, không đợi build xong.
6. **Mini App không phải nơi ở của user.** Thang tương tác: chat là nhà, Mini App là phòng xem chi tiết. Mọi màn hình phải có đường quay lại chat và một hành động tiếp theo bằng chữ.

---

## 🎬 Choreography

**Xác thực (khác hoàn toàn Telegram):**
```
Mini App (zmp-sdk) → getAccessToken() → token
   → gọi API mình với header X-Zalo-Access-Token
   → backend: cache lookup (hash token → user) HIT?  → dùng luôn
                                              MISS? → gọi Zalo xác thực token, lấy zalo_user_id
   → tra users.zalo_user_id → user
        không thấy → 401 kèm hướng dẫn nhắn OA để liên kết (KHÔNG tự tạo user ở đây)
   → cache (hash token → user_id) TTL ngắn
```

**Vào Mini App:**
```
tin OA có nút oa.open.url  → link Mini App (5.1 #3.2 đã có ánh xạ)
QR / zalo.me/s/<appId>     → mở trực tiếp
deep link có tham số       → ?sh_type=<type>&sh_data=<base64>  → route tới đúng màn hình
```

**Dữ liệu màn hình:**
```
màn hình → GET /miniapp/api/<...> (JSON, cùng endpoint Telegram dùng)
   → handler → service → DB
   → ảnh (nếu có) → media URL từ 5.1 E1
```

---

## 📁 Files Touched

**E1 — Auth Zalo Mini App:**
- `backend/miniapp/zalo_auth.py` *(mới)* — verify access token qua Zalo, cache, trả `zalo_user_id`
- `backend/miniapp/auth.py` — tách phần chung; **không sửa đường Telegram** (regression-safe)
- `backend/miniapp/routes.py` — dependency xác thực đa kênh thay cho `require_miniapp_auth` cứng
- `backend/main.py` — CORS cho origin Mini App Zalo
- `backend/config/__init__.py` — `zalo_miniapp_enabled`, `zalo_miniapp_app_id`, `zalo_miniapp_allowed_origin`

**E2 — API-only hoá màn hình:**
- `backend/miniapp/routes.py` — bổ sung endpoint JSON cho những màn hình hiện chỉ có HTML (`wealth`, `cashflow`, `twin` phần còn thiếu)
- Không đổi hợp đồng dữ liệu của endpoint đang có (Telegram đang dùng)

**E3 — Client Mini App:**
- `zalo-miniapp/` *(mới)* — dự án `zmp-sdk` + `zmp-ui`, build tĩnh, deploy qua `zmp-cli`
- `zalo-miniapp/src/api.ts` *(mới)* — client gắn header `X-Zalo-Access-Token`
- `zalo-miniapp/src/views/*` — Twin, Wealth, Expense, Cashflow
- `miniapp/src/` — rà phần logic biểu đồ có thể tách dùng chung (nếu chi phí thấp; không ép)

**E4 — Đường vào + deep link:**
- `backend/miniapp/urls.py` — thêm helper URL Mini App Zalo (song song với helper Telegram hiện có)
- `backend/adapters/zalo_button_mapper.py` — nút mở Mini App
- `content/zalo.yaml` — copy các nút/lời mời mở Mini App

**E5 — Hồ sơ, xét duyệt, vận hành:**
- `docs/conventions/zalo-operations.md` — mục Mini App: quy trình deploy, xét duyệt, rollback
- `.github/workflows/*` — build/kiểm tra bundle Zalo Mini App trong CI

---

## 🗄️ New DB Columns / Tables

| Thay đổi | Mục đích | Ghi chú |
|---|---|---|
| *(không bắt buộc)* `zalo_miniapp_sessions` | Cache token đã verify nếu chọn cache ở DB | Đề xuất **cache trong Redis**, không tạo bảng. Chỉ tạo bảng nếu cần audit truy cập. `user_id` NOT NULL nếu có. |

5.2 **không** cần cột mới trên `users` — `zalo_user_id` đã có từ 4B và là khoá liên kết duy nhất cần thiết.

---

## 📦 Epics & Stories

Chi tiết sub-issue + DoD: [`phase-5.2-issues.md`](phase-5.2-issues.md).

### Epic E1 — Xác thực Zalo Mini App ⭐ *(chặn mọi thứ)*
`getAccessToken()` → verify server-side → `zalo_user_id` → user. Cache để không gọi Zalo mỗi request. Đường Telegram giữ nguyên byte-identical.

### Epic E2 — API-only hoá màn hình
Những màn hình hiện sống bằng HTML server-render phải có endpoint JSON đủ dùng. Không fork endpoint theo kênh.

### Epic E3 — Client Mini App (`zmp-sdk` + `zmp-ui`)
Dự án tĩnh riêng, 4 màn hình, deploy qua `zmp-cli`. Đây là codebase frontend thứ hai — chấp nhận có chủ đích, ghi rõ ranh giới.

### Epic E4 — Đường vào & deep link
Nút trong tin OA, QR, `zalo.me/s/<appId>`, deep link có tham số route tới đúng màn hình.

### Epic E5 — Hồ sơ, xét duyệt & vận hành
Nộp hồ sơ sớm, runbook deploy/rollback, CI build bundle.

---

## 🏗️ Layer Mapping

| Layer | 5.2 |
|---|---|
| `routers/` + `miniapp/routes.py` | Xác thực ở edge, trả JSON. Không business logic |
| `miniapp/zalo_auth.py` | Adapter xác thực: gọi Zalo, cache. Không chạm DB business |
| `services/` | **Không đổi.** Nếu 5.2 phải sửa service → thiết kế sai |
| `adapters/` | `zalo_button_mapper` thêm nút mở Mini App |
| Client `zalo-miniapp/` | Vỏ hiển thị. **Không tính toán tài chính phía client** |

---

## ⚠️ Risk & Rollback

| Rủi ro | Giảm thiểu |
|---|---|
| Xác thực phụ thuộc network tới Zalo → Zalo chậm/down thì Mini App chết | Cache token đã verify (Redis, TTL ngắn); timeout ≤2s; lỗi → 503 kèm copy tử tế + gợi ý quay lại chat; **không** fail-open cho phép truy cập dữ liệu |
| Cache token sai → user A thấy dữ liệu user B | Khoá cache là **hash của token**, giá trị là `user_id`; test đa người dùng; TTL ngắn; xoá cache khi unlink |
| CORS mở rộng làm lộ API | Chỉ allow đúng origin Zalo Mini App, không `*`, không dùng chung biến với admin origin; test khẳng định origin lạ bị chặn |
| Hồ sơ Mini App bị từ chối / kiểm duyệt nội dung | Nộp sớm song song build; rà copy theo cấm kỵ CLAUDE.md (0 "Decision Engine/CFO/GPS"); chuẩn bị bản mô tả tính năng bằng tiếng Việt |
| Codebase frontend thứ hai trôi dạt khỏi bản Telegram | Hợp đồng API là điểm chung duy nhất; test hợp đồng chạy CI; ranh giới ghi trong runbook |
| User mở Mini App nhưng chưa liên kết OA | 401 có copy hướng dẫn nhắn OA; **không tự tạo user từ Mini App** (khác #4.3 của 5.1 — ở đó user đến từ chat, danh tính rõ) |
| `getAccessToken()` trả "DEFAULT ACCESS TOKEN" khi dev trên trình duyệt | Nhận diện chuỗi này và từ chối ở server; dev dùng biến môi trường dev-token riêng, **không** bypass xác thực |

**Rollback:** `ZALO_MINIAPP_ENABLED=false` → API từ chối header Zalo, Mini App hiện màn hình bảo trì; chat + Mini App Telegram không ảnh hưởng. Bundle Zalo có thể rollback về bản deploy trước qua `zmp-cli`.

---

## ✅ Definition of Done

- User đã liên kết mở Mini App từ tin OA → thấy đúng dữ liệu của mình, không cần đăng nhập lại.
- 4 màn hình (Twin, tài sản, chi tiêu, dòng tiền) chạy đủ trên Zalo.
- Xác thực: token hợp lệ → 200; token sai/hết hạn/"DEFAULT ACCESS TOKEN" → 401; Zalo API timeout → 503 có copy, không rò dữ liệu.
- Đường Telegram Mini App **byte-identical** so với trước 5.2 (test regression).
- CORS: origin Zalo cho qua, origin lạ bị chặn — có test.
- Deep link mở đúng màn hình.
- Copy Mini App qua vi-localization-checker; 0 "Decision Engine/CFO/GPS".
- ruff + layer-contract-checker sạch; 0 thay đổi trong `backend/services/`.
- Hồ sơ Mini App đã nộp/duyệt; runbook deploy + rollback viết xong.

---

## 🚫 Out of Scope (để sau)

- Thanh toán trong Mini App (Zalo Pay).
- Ghi dữ liệu phức tạp từ Mini App (nhập tài sản nhiều bước) — v1 ưu tiên **xem**; sửa/xoá chi tiêu giữ như bản Telegram nếu API đã có.
- Thông báo đẩy riêng của Mini App.
- Chia sẻ ảnh Twin ra ngoài Zalo từ Mini App.
- Gộp hai codebase frontend làm một — cân nhắc sau khi cả hai ổn định.

---

## 🔀 Execution Order (đề xuất)

```
E5 (nộp hồ sơ) khởi động NGÀY 1, song song mọi thứ
E1 (auth) ──> E2 (API-only) ──> E3 (client) ──> E4 (deep link)
E3 cần E1 xong mới gọi được API thật; trước đó dùng mock
```

E1 trước vì mọi màn hình đều phải qua nó; E5 chạy song song vì phụ thuộc bên ngoài, không phụ thuộc code.

---

## 📚 Nguồn & điều cần verify lại lúc build

Các fact nền tảng dưới đây lấy từ tìm kiếm web (docs chính chủ `developers.zalo.me` / `miniapp.zaloplatforms.com` bị chặn bởi network policy của môi trường phát triển này), **phải đối chiếu lại docs chính chủ ở issue đầu tiên của E1 và E3** trước khi code:

- `getAccessToken()` trả "DEFAULT ACCESS TOKEN" khi chạy trên trình duyệt dev (không có user Zalo đăng nhập).
- Xác thực server-side đi qua Zalo Graph API (`graph.zalo.me/v2.0/...`) — **endpoint và tham số chính xác cần verify**.
- `zmp-sdk` ≥ 2.31.1 cho cơ chế xin quyền dữ liệu cá nhân mới.
- Mini App chỉ triển khai được dưới OA **đã xác thực và không bị hạn chế**; một OA có thể gắn nhiều Mini App.
- Deploy bundle tĩnh qua `zmp-cli` (`zmp deploy`); **giới hạn dung lượng bundle chưa xác nhận** — verify trước khi chốt thư viện biểu đồ.
- Link chia sẻ `https://zalo.me/s/<appId>`; deep link `<miniapp_base_url>?sh_type=<type>&sh_data=<base64>`.
- Thời gian duyệt: OA 3-7 ngày, hồ sơ Mini App 3-5 ngày làm việc.

---

## 🔓 Product Decisions Cần Owner Ký

1. **Mini App có cho *nhập liệu* không, hay chỉ *xem*?** Chỉ-xem rẻ và duyệt dễ hơn; có nhập liệu thì Mini App thành nơi user ở lại. *Đề xuất: v1 chỉ xem + sửa/xoá chi tiêu (API đã có), nhập tài sản vẫn qua chat.*
2. **Hai codebase frontend hay gộp một?** Gộp tốn công refactor bản Telegram đang chạy ổn. *Đề xuất: giữ hai, ràng nhau bằng hợp đồng API + test CI; xét gộp sau 5.2.*
3. **User chưa liên kết mở Mini App thì sao?** Tự tạo user tiện nhưng danh tính mù mờ (không có ngữ cảnh chat). *Đề xuất: 401 + hướng dẫn nhắn OA một câu là xong — giữ chat là cửa vào.*
4. **TTL cache token verify.** Ngắn thì gọi Zalo nhiều, dài thì unlink chậm có hiệu lực. *Đề xuất: 5 phút, xoá cache ngay khi unlink.*
