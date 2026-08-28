# Zalo Console — Checklist thao tác (một lần, cho người vận hành)

Tài liệu này dành cho **người ngồi trước Zalo Developer Console**, không
phải cho người đọc code. Đi hết từ trên xuống, kết quả là:

1. Ba giá trị nằm đúng ba biến env: `ZALO_APP_ID`, `ZALO_APP_SECRET`,
   `ZALO_OA_SECRET_KEY`.
2. Một cặp `access_token` + `refresh_token` đã nằm trong bảng
   `zalo_oa_credentials` (từ đó app tự xoay, không cần vào console nữa).
3. Webhook trỏ về server và Zalo nhận URL đó — làm **sau** bước 2, vì lý do
   ở đầu §4.
4. Một **nhật ký `ASSUMED`** đã bắt đầu được ghi — để đối chiếu lúc soak.

Thời gian: ~40 phút thao tác, cộng 3–7 ngày chờ duyệt xác thực OA (bước
§7, chạy nền, **không** chặn 5.0).

Vận hành hằng ngày, sự cố, quota, rollback → không nằm ở đây mà ở
[`zalo-operations.md`](zalo-operations.md). File này chỉ là *lần cài đặt đầu tiên*.

> **Cảnh báo về chính tài liệu này.** Docs chính chủ `developers.zalo.me`
> bị network policy của môi trường build chặn (đã kiểm lại 03/08/2026:
> `CONNECT tunnel failed, 403`), nên **mọi tên menu / nhãn nút bên dưới là
> `ASSUMED`** — viết theo hiểu biết về console tại thời điểm lập kế hoạch,
> chưa nhìn tận mắt. Cái *không* `ASSUMED` là: giá trị nào đi vào biến nào,
> và cách chứng minh mình lấy đúng (§6). Nếu nhãn thật khác, **sửa file này
> ngay trong lúc thao tác** — đó là mục đích của các ô "Ghi lại".
>
> **Cập nhật 27/08/2026.** §3 đã bị sửa vì nó **sai**: bản trước chỉ người
> vận hành sang `oa.zalo.me` để tìm OA Secret Key, và ở đó không có giá trị
> nào tên như vậy. Chỗ đúng là `developers.zalo.me` → app → mục *Official
> Account* / *Webhook*. Nguồn của lần sửa này là kết quả tìm kiếm web (docs
> chính chủ + community threads của Zalo), **không phải** trang chính chủ đã
> mở tận mắt — trang đó vẫn bị chặn từ môi trường build. Nên nó tốt hơn
> `ASSUMED` một bậc, chưa phải `DOC`: vẫn phải xác nhận bằng mắt lúc thao
> tác và ghi vào §8 dòng #7.

---

## 0. Chuẩn bị trước khi mở console

- [ ] Tài khoản Zalo cá nhân là **admin** của Official Account Bé Tiền.
      Không phải admin thì không liên kết được OA vào app ở §3 — mà chưa
      liên kết thì không có OA Secret Key nào để lấy.
- [ ] Biết host prod/staging sẽ nhận webhook (`https://<host>`).
- [ ] Có quyền đặt file tĩnh ở **thư mục gốc public** của host đó. Bước xác
      thực domain (§3 bước 2) cần đúng quyền này.
- [ ] Có quyền sửa `.env` trên server và chạy `python -m scripts.seed_zalo_credentials`.
- [ ] **Chưa** bật `ZALO_CHANNEL_ENABLED=true`. Bật ở §5, đúng thứ tự, vì
      bật sớm với env rỗng thì app **không boot** (invariant fail-closed) —
      và bật trước khi có token thì tin nhắn đầu tiên bị nuốt (xem đầu §4).

---

## 1. Ba giá trị — nhìn tổng thể trước khi đi lấy

Đây là bảng quan trọng nhất của tài liệu. Hai trong ba giá trị đều được
console gọi là **"Secret Key"**, ở hai màn hình khác nhau của **cùng một
console** (`developers.zalo.me`), và **không thể thay cho nhau**.

| Biến env | Console nào | Dùng để làm gì | Lấy sai thì hỏng cái gì |
|---|---|---|---|
| `ZALO_APP_ID` | Developer Console (`developers.zalo.me`) → app Bé Tiền | Thành phần đầu của MAC webhook; body của refresh token | Hỏng **cả hai** — webhook mismatch *và* refresh fail |
| `ZALO_APP_SECRET` | Cùng màn hình với `app_id`, nhãn ~ *"Secret Key"* của **ứng dụng** | Header `secret_key` khi refresh token | Chỉ hỏng refresh — im lặng đúng 1 giờ rồi bot câm |
| `ZALO_OA_SECRET_KEY` | Cùng console, **khác màn hình**: app Bé Tiền → *Official Account* / *Webhook*, nhãn ~ *"OA Secret Key"* — che sẵn, bấm con mắt để hiện | Thành phần cuối của MAC webhook | Chỉ hỏng webhook — 100% tin vào bị 403 (chế độ enforce) |

**Chỗ dễ nhầm nhất, nói thẳng:** app secret và OA secret key là hai chuỗi
khác nhau, tên hiển thị gần giống nhau, và — trái với những gì tài liệu này
viết trước 27/08/2026 — **nằm trong cùng một console**, chỉ khác màn hình.
Không có cái nào ở `oa.zalo.me`. Đảo hai giá
trị này cho nhau là lỗi cài đặt phổ biến nhất — và nó **không báo lỗi lúc
boot**, vì invariant chỉ kiểm tra "có rỗng không", không kiểm tra "có
đúng chỗ không". Triệu chứng của việc đảo là *cả hai* thứ cùng hỏng, xem
§6.

Công thức trong code cho thấy vì sao không thể thay nhau:

```
MAC webhook  = sha256(app_id + body + timestamp + OA_SECRET_KEY)   ← ZALO_OA_SECRET_KEY
refresh call = POST /v4/oa/access_token, header secret_key: APP_SECRET   ← ZALO_APP_SECRET
```

Một cái đi vào hàm băm, một cái đi vào HTTP header. Không có đường nào để
một giá trị sai "gần đúng".

---

## 2. Màn hình A — Developer Console: lấy `app_id` + `app_secret`

1. Mở `https://developers.zalo.me` → đăng nhập bằng tài khoản admin.
2. Vào mục ứng dụng (*Ứng dụng của tôi* / *My Apps*) → chọn app Bé Tiền.
   Chưa có app thì tạo mới, loại **Official Account**.
3. Vào phần thông tin ứng dụng (*Thông tin ứng dụng* / *Settings*). Tại
   đây có cả hai giá trị của màn hình này:
   - **App ID** — dãy số. Đối chiếu nhanh: nó cũng nằm trong URL trình
     duyệt lúc bạn đang mở app (`.../app/<app_id>/...`). Hai chỗ khác nhau
     là bạn đang nhìn nhầm app.
   - **App Secret Key** — bấm hiện/copy. Đây là `ZALO_APP_SECRET`,
     **không** phải giá trị của §3.
4. Dán vào `.env` trên server:

   ```dotenv
   ZALO_APP_ID=<dãy số>
   ZALO_APP_SECRET=<secret key của ỨNG DỤNG>
   ```

   Dán bằng tay dễ dính khoảng trắng/xuống dòng ở cuối; §6 bước 1 bắt lỗi đó.

**Ghi lại (điền lúc thao tác):**

| Câu hỏi | Thực tế bạn thấy |
|---|---|
| Đường dẫn menu thật tới màn hình này | |
| Nhãn hiển thị của app secret | |
| `app_id` có phải toàn chữ số không? Dài bao nhiêu ký tự? | |

---

## 3. Màn hình B — vẫn ở Developer Console: liên kết OA, xác thực domain, lấy OA Secret Key

> **Mục này đã bị sửa 27/08/2026.** Bản trước bảo mở `oa.zalo.me`. Trên
> `oa.zalo.me` **không có** giá trị nào tên "OA Secret Key" — ai làm theo
> bản cũ sẽ tìm mãi không thấy. Chỗ đúng: **cùng console với §2**,
> `developers.zalo.me` → app Bé Tiền → mục *Official Account* / *Webhook*.

Nó vẫn là secret của **OA**, không phải của ứng dụng: mỗi OA liên kết vào
app có một OA Secret Key riêng (đó là lý do nó chỉ xuất hiện **sau** khi
liên kết). Chỉ là chỗ hiển thị nằm trong app, không nằm trong OA Manager.

Ba bước, đúng thứ tự — bước sau chỉ mở ra khi bước trước xong:

1. **Liên kết OA vào app.** Vẫn trong app ở §2: menu trái → *Official
   Account* → *Quản lý Official Account* → chọn OA Bé Tiền → *Liên kết* →
   đọc thông tin hiện ra → *Đồng ý*. Cần tài khoản admin của OA (§0).
   Chưa liên kết thì mục Webhook chưa dùng được và **chưa có** OA Secret
   Key nào tồn tại.
2. **Xác thực domain** (*Domain Verification* / *Xác thực domain*). Console
   cho tải một file HTML; đặt nó ở **thư mục gốc public** của domain sẽ
   nhận webhook (`https://<host>/<tên file>.html` phải mở được từ ngoài),
   rồi bấm xác thực. Bỏ qua bước này thì hai thứ hỏng và triệu chứng **không
   nói gì về secret**:
   - console từ chối URL webhook ở §5 với lý do domain chưa xác thực;
   - luồng OAuth ở §4 trả `-14003 Invalid redirect uri` — dễ bị đọc nhầm
     thành "sai `redirect_uri`" rồi đi sửa URL vô ích.
3. **Lấy OA Secret Key** trong mục *Webhook* của app (cùng chỗ sẽ điền URL
   webhook ở §5 bước 4). Giá trị **bị che sẵn — bấm biểu tượng con mắt** để
   hiện rồi copy. Dán vào:

   ```dotenv
   ZALO_OA_SECRET_KEY=<OA Secret Key>
   ```

4. Kiểm tra ngay tại chỗ, bằng mắt: chuỗi này **phải khác** chuỗi ở §2.
   Giống nhau nghĩa là bạn copy lại đúng một giá trị — nhiều khả năng vì hai
   màn hình nằm cùng console nên bấm nhầm.

> **Nếu sau này bấm reset OA Secret Key trong console** thì giá trị cũ chết
> ngay: mọi webhook sẽ `mac_mismatch` cho tới khi `.env` được cập nhật và
> service restart. Đừng reset để "thử cho chắc".

**Ghi lại:**

| Câu hỏi | Thực tế bạn thấy |
|---|---|
| Đường dẫn menu thật tới OA Secret Key (khẳng định/bác bỏ: `developers.zalo.me` → app → Official Account/Webhook) | |
| Nhãn hiển thị | |
| Có phải bấm con mắt mới hiện không? | |
| Bước xác thực domain: tên file, đặt ở đâu, mất bao lâu để console chấp nhận | |
| Hai secret có độ dài khác nhau không? (chỉ ghi độ dài, **không ghi giá trị**) | |

> **Không bao giờ** viết giá trị thật của ba biến này vào bất kỳ file nào
> trong repo, kể cả tài liệu này, kể cả "tạm để nhớ". Ghi độ dài và
> fingerprint (§6) là đủ để đối chiếu.

---

## 4. Authorise OAuth — lấy cặp token đầu tiên

> **Vì sao bước này đứng trước việc bật flag (§5).** Nếu
> `ZALO_CHANNEL_ENABLED=true` khi bảng `zalo_oa_credentials` còn rỗng,
> webhook vẫn **nhận** tin nhắn bình thường — nhưng lúc trả lời, adapter
> không có access token nên bỏ qua lượt gửi (fail-open), và worker vẫn đánh
> dấu sự kiện là `done`. Tin đó mất hẳn: ta đã trả `200` nên Zalo không gửi
> lại, và dedup theo `msg_id` không cho xử lý lại. Có token trước rồi mới mở
> cửa là cách duy nhất không mất tin của người dùng đầu tiên.

App tự xoay token sau khi có cặp đầu tiên. Cặp đầu tiên phải lấy tay, và
đây là lần duy nhất (trừ khi phải khôi phục theo runbook).

1. Đăng ký `redirect_uri` trong console trước — Zalo từ chối callback tới
   URL chưa đăng ký. Dùng đúng URL bạn sẽ mở ở bước 2. Domain của URL đó
   phải **đã xác thực** ở §3 bước 2; chưa xác thực thì bước 3 dưới đây trả
   `-14003 Invalid redirect uri` dù URL gõ đúng từng ký tự.
2. Mở link cấp quyền trên trình duyệt, đăng nhập bằng tài khoản admin OA:

   ```
   https://oauth.zaloapp.com/v4/oa/permission?app_id=<ZALO_APP_ID>&redirect_uri=<redirect_uri>
   ```

   `ASSUMED`: tham số và đường dẫn của luồng cấp quyền v4 (kể cả việc
   console có bắt buộc `code_challenge`/PKCE hay không) chưa đối chiếu được
   với docs chính chủ. **Ghi lại URL thật mà console hướng dẫn.**
3. Đồng ý cấp quyền → trình duyệt được redirect về `redirect_uri` kèm
   `code` (và `oa_id`) trên query string. Copy `code` — nó **rất ngắn hạn**,
   làm bước 4 ngay.
4. Đổi `code` lấy cặp token. Chạy trên server, nơi có `$ZALO_APP_SECRET`:

   ```bash
   curl -X POST https://oauth.zaloapp.com/v4/oa/access_token \
     -H "secret_key: $ZALO_APP_SECRET" \
     -d "app_id=$ZALO_APP_ID" \
     -d "grant_type=authorization_code" \
     -d "code=<code vừa lấy>"
   ```

   Nhớ: **lỗi của Zalo trả về HTTP 200 kèm `error` ≠ 0.** Đọc body, đừng
   đọc status code — và đọc **cả `error` lẫn `message`** trước khi kết luận.
   `ZALO_APP_SECRET` sai chỉ là một trong nhiều nguyên nhân, và ở lần cài
   đầu tiên nó thường không phải nguyên nhân có xác suất cao nhất:

   | `message` nói về | Nghĩ tới trước |
   |---|---|
   | `code` hết hạn / đã dùng | `code` chỉ sống vài chục giây — lấy lại từ bước 2–3, đừng sửa gì khác |
   | app / secret / xác thực | `ZALO_APP_SECRET` sai, hoặc đã đảo với OA secret key → §2 và §3 |
   | `redirect_uri` (đặc biệt `-14003`) | URL ở bước 1 không khớp URL đã đăng ký (khác dấu `/` cuối cũng tính là khác) — **hoặc** domain chưa xác thực ở §3 bước 2 |
   | tham số thiếu hoặc sai tên | Luồng v4 ở bước 2 là `ASSUMED` — rất có thể chính lệnh này sai, không phải secret sai |

   Ghi nguyên văn `error` + `message` vào ô "Ghi lại" bên dưới **trước khi**
   thử lại — đó là bằng chứng cho dòng #8 của nhật ký §8.
5. Nạp cặp token vào DB. Hai điều **không** được làm: truyền token qua argv
   (argv hiện trong `ps` của mọi process trên máy), và gõ token vào bất kỳ
   lệnh nào — mọi lệnh đã gõ đều nằm lại trong `~/.bash_history`, và `unset`
   chỉ xoá biến môi trường chứ không xoá history. Đọc vào biến bằng
   `read -rs` (không echo ra màn hình, không đi vào history):

   ```bash
   read -rs ZALO_BOOTSTRAP_ACCESS_TOKEN  && export ZALO_BOOTSTRAP_ACCESS_TOKEN
   read -rs ZALO_BOOTSTRAP_REFRESH_TOKEN && export ZALO_BOOTSTRAP_REFRESH_TOKEN
   python -m scripts.seed_zalo_credentials --app-id "$ZALO_APP_ID"
   unset ZALO_BOOTSTRAP_ACCESS_TOKEN ZALO_BOOTSTRAP_REFRESH_TOKEN
   ```

   Mỗi `read -rs` sẽ đứng đợi: dán token rồi Enter. Màn hình không hiện gì —
   đúng như vậy. Script tự che giá trị khi in log (`…abcd (128 chars)`).

   Lỡ gõ token vào một lệnh rồi? Coi cặp token đó là **đã lộ**: xoá dòng đó
   khỏi history (`history -d <số dòng>`), rồi quay lại bước 2 lấy `code`
   mới. Đừng dùng tiếp cặp token đã nằm trong history.
6. Xác nhận có row, không in token ra:

   ```sql
   SELECT app_id, expires_at, refresh_count, refresh_pending_at IS NOT NULL AS pending
   FROM zalo_oa_credentials;
   ```

   Mong đợi: đúng 1 row, `expires_at` ~1 giờ tới, `pending = false`.

Từ giờ **không copy `refresh_token` đi đâu nữa**. Nó single-use: mỗi lần
app refresh, token cũ chết ngay. Một bản copy để dành sẽ là token đã chết,
và dùng nó lúc sự cố sẽ làm sự cố nặng thêm. Đường khôi phục duy nhất là
[runbook re-authorise](zalo-operations.md#runbook-manual-oa-re-authorisation).

**Ghi lại:**

| Câu hỏi | Thực tế bạn thấy |
|---|---|
| URL cấp quyền thật (kèm mọi tham số bắt buộc) | |
| Có bắt buộc PKCE / `code_challenge` không? | |
| Ở đâu đăng ký `redirect_uri`? | |
| `expires_in` trong response là bao nhiêu giây? | |
| `error` + `message` của mọi lần đổi `code` thất bại (nguyên văn) | |

---

## 5. Trỏ webhook — **thứ tự các bước là quan trọng**

Chỉ làm phần này khi §4 đã cho ra đúng 1 row trong `zalo_oa_credentials`.
Bật flag sớm hơn thì tin nhắn đầu tiên của người dùng sẽ bị nuốt — xem ô
cảnh báo đầu §4.

Cái bẫy: webhook chỉ tồn tại khi `ZALO_CHANNEL_ENABLED=true`. Flag off thì
route **không được mount** và Zalo nhận `404` khi bấm nút xác minh URL.
Cái bẫy thứ hai: nút xác minh của console có thể gửi một request thăm dò
không phải sự kiện Zalo chuẩn (không có field `timestamp`) — ở chế độ
enforce, cái đó bị **403** dù mọi thứ đều đúng.

Vì vậy, đúng thứ tự này:

1. Trên server, đặt:

   ```dotenv
   ZALO_CHANNEL_ENABLED=true
   ZALO_SIGNATURE_ENFORCE=false     # soak — bắt buộc ở lần cài đầu tiên
   ```

2. Restart service. App boot được nghĩa là cả ba biến ở §2–§3 đều **không
   rỗng** (invariant fail-closed đã chạy). Boot fail thì thông báo lỗi sẽ
   gọi tên đúng biến còn thiếu — sửa rồi restart lại.
3. Xác nhận route đã sống. Ghi lại **giờ bắt đầu soak** ngay lúc này (§8
   dòng #2 cần mốc đó):

   ```bash
   date -u +'%Y-%m-%dT%H:%M:%SZ'    # ghi vào §8 dòng #2
   curl -sS -o /dev/null -w "%{http_code}\n" -X POST https://<host>/api/v1/zalo/webhook \
     -H 'Content-Type: application/json' -d '{}'
   ```

   Mong đợi: đúng **`200`**. Body `{}` không có chữ ký, nhưng ở chế độ soak
   request vẫn được nhận, parse ra không phải sự kiện Zalo nên app ack rồi
   bỏ qua — `200` chính là câu trả lời đúng. Bất cứ mã nào khác đều nói một
   chuyện khác nhau:

   | Nhận được | Nghĩa là |
   |---|---|
   | `200` | Route sống, đang ở chế độ soak. Đi tiếp. |
   | `403` | `ZALO_SIGNATURE_ENFORCE` đang là `true` — quay lại bước 1; lần cài đầu bắt buộc soak |
   | `404` | Flag chưa bật, hoặc service chưa restart |
   | `502` / `503` / `504` | Không tới được app (reverse proxy, hoặc service chết) — chưa phải chuyện của Zalo |
   | `407`, `3xx`, hoặc một trang HTML | Bạn đang nói chuyện với proxy/CDN, request chưa tới app |

   Chốt lại bằng log — chỉ log mới chứng minh chính app đã nhận:

   ```bash
   grep 'zalo.signature' <log> | tail -1
   # zalo.signature valid=false reason=missing_header ... shape=absent
   ```

   `reason=missing_header` ở đây là **đúng mong đợi** cho một probe không ký.
   Nhớ nó: dòng này sẽ nằm trong log và không được tính vào tỉ lệ soak ở §8.
4. Quay lại Developer Console → phần Webhook của app (**đúng chỗ đã lấy OA
   Secret Key ở §3 bước 3**) → điền:

   - URL: `https://<host>/api/v1/zalo/webhook`
   - Sự kiện cần bật: `user_send_text` và `user_send_message`.
     Các sự kiện khác (follow/unfollow/receipt) app vẫn trả `200` rồi bỏ
     qua, bật thêm không sai nhưng không có tác dụng gì ở 5.0.

5. Bấm xác minh / lưu. Rồi từ điện thoại, **nhắn một tin bất kỳ cho OA** và
   xem log — đây mới là bằng chứng thật:

   ```bash
   grep 'zalo.signature' <log> | tail -5
   # zalo.signature valid=true reason=ok bypassed=false enforced=false shape=prefix=mac,hex=lower,len=64
   ```

   `valid=false reason=mac_mismatch` ở bước này gần như luôn là §3 lấy
   nhầm giá trị (hoặc dính khoảng trắng) — sang §6.

   Chép nguyên `shape=…` của lần giao dịch thật đầu tiên vào §8 dòng #1 và
   #3: nó nói tiền tố header thật là gì và digest hoa hay thường, hai thứ mà
   `valid=true` **không** chứng minh được (bộ verify chấp nhận cả digest trần
   lẫn `mac=`/`sha256=`, và hạ chữ thường trước khi so).

**Ghi lại:**

| Câu hỏi | Thực tế bạn thấy |
|---|---|
| Đường dẫn menu tới ô webhook | |
| Console có nút "xác minh URL" riêng không? Nó gửi gì? (status code server trả) | |
| Danh sách tên sự kiện console hiển thị (đúng chính tả) | |

---

## 6. Kiểm chứng — chứng minh ba giá trị nằm đúng chỗ

Đừng tin vào việc "nhìn thấy mình copy đúng". Ba lệnh dưới đây, mỗi lệnh
chứng minh một chuyện khác nhau.

**Bước 1 — không dính khoảng trắng, không trùng nhau.** In dấu vân tay,
không in giá trị:

```bash
python - <<'PY'
import hashlib
from backend.config import get_settings
s = get_settings()
for name in ("zalo_app_id", "zalo_app_secret", "zalo_oa_secret_key"):
    v = getattr(s, name) or ""
    fp = hashlib.sha256(v.encode()).hexdigest()[:8] if v else "-"
    print(f"{name:20} len={len(v):<4} sạch={v == v.strip()!s:<5} fp={fp}")
PY
```

- `sạch=False` ⇒ dính khoảng trắng/xuống dòng lúc dán → MAC sẽ không bao
  giờ khớp. Sửa `.env`, restart.
- `fp` của `zalo_app_secret` **trùng** `fp` của `zalo_oa_secret_key` ⇒ bạn
  đã dán cùng một giá trị vào hai chỗ. Quay lại §3.

**Bước 2 — OA Secret Key đúng?** Nhắn một tin cho OA từ điện thoại rồi:

```bash
grep 'zalo.signature' <log> | tail -1
```

`valid=true reason=ok bypassed=false` ⇒ đúng. `bypassed=true` không phải
bằng chứng gì cả — đó là nhánh dev khi secret rỗng.

**Bước 3 — App Secret đúng?** Nếu §4 chạy lọt (`error: 0`) thì đã chứng
minh rồi — lần đổi `code` lấy token cũng gửi đúng cái header `secret_key`
đó. Đấy là bằng chứng đủ mạnh; phần dưới chỉ để chứng minh thêm rằng
**vòng xoay** token cũng chạy.

Muốn chứng minh vòng xoay: **chờ suông không đủ.** Không có job nền nào
refresh token cả — service token là read-through, chỉ xoay khi có một lần
gọi Zalo thật thấy token đã hết hạn. Một OA nằm im 3 tiếng vẫn có
`refresh_count = 0`, và điều đó **không** nói gì về app secret. Nên phải
tự tạo ra lần gọi đó:

1. Ghi lại `expires_at` hiện tại (`SELECT expires_at FROM zalo_oa_credentials;`).
2. Đợi qua mốc đó (token sống 1 giờ).
3. **Nhắn một tin cho OA từ điện thoại** để bot phải trả lời — chính lần
   gửi đó là thứ kích hoạt refresh.
4. Rồi mới đọc:

```sql
SELECT refresh_count, last_refreshed_at, refresh_pending_at IS NOT NULL AS pending
FROM zalo_oa_credentials;
```

`refresh_count` tăng, `pending = false` ⇒ vòng xoay token đang chạy đúng.
`pending = true` đọng lại ⇒ refresh đã bắt đầu mà không hoàn tất: đừng
retry mù, đi theo
[runbook `refresh_pending`](zalo-operations.md#runbook-refresh_pending-found-on-startup) — `refresh_token`
là **dùng một lần**, gọi lại bằng token cũ chỉ làm hỏng thêm.

### Bảng chẩn đoán — triệu chứng nào tố cáo giá trị nào

| Triệu chứng | Giá trị sai |
|---|---|
| App không boot, log gọi tên biến | Biến đó **rỗng** |
| Webhook `valid=false reason=mac_mismatch`, nhưng refresh token chạy tốt | `ZALO_OA_SECRET_KEY` |
| Webhook `valid=true`, nhưng refresh trả `error != 0` | `ZALO_APP_SECRET` |
| **Cả hai** cùng hỏng | `ZALO_APP_ID` sai — **hoặc** đã đảo app secret ↔ OA secret key (khả năng cao hơn nhiều) |
| `valid=false reason=missing_timestamp` | Không phải sai giá trị: request không phải sự kiện Zalo chuẩn (thường là ping xác minh của console, hoặc ai đó đang dò URL) |
| `valid=false reason=missing_header` | Request không đến từ Zalo |
| Mọi thứ đúng nhưng Zalo báo URL không hợp lệ | Flag `ZALO_CHANNEL_ENABLED` chưa bật hoặc service chưa restart → route 404 |

---

## 7. Xác thực OA (nộp hồ sơ) — làm ngày 1, không chặn 5.0

Xác thực OA cần hồ sơ doanh nghiệp và mất 3–7 ngày duyệt. Nó **không** cần
cho 5.0, nhưng **chặn Mini App ở 5.2**, nên nộp sớm là để dành thời gian,
không phải để mở khoá gì ở phase này. (ZNS đã loại hẳn ở Decision #2 nên
không còn là lý do nộp.)

- [ ] Nộp hồ sơ trong OA Manager.
- [ ] Ngày nộp: `______`  · Ngày duyệt: `______`

---

## 8. Nhật ký `ASSUMED` — bảng đối chiếu lúc soak

Mục đích của bảng này: lúc soak, mỗi dòng `ASSUMED` trong
[`zalo-operations.md` §Platform facts](zalo-operations.md#platform-facts)
phải được **một quan sát thật** xác nhận hoặc bác bỏ. Ghi vào đây trước,
rồi mới sửa bảng facts — để nếu có dòng nào bác bỏ, ta còn giữ được bằng
chứng thay vì chỉ có một dòng doc đã bị sửa.

Quy tắc: **ghi cái nhìn thấy, không ghi cái mong đợi.** Một ô trống trung
thực có ích hơn một ô "OK" đoán mò.

| # | Dòng `ASSUMED` | Bằng chứng cần lấy (lệnh cụ thể) | Quan sát thật | Ngày | Kết luận |
|---|---|---|---|---|---|
| 1 | Header value format `mac=<hex>` | Trường `shape=` của một request **thật** (§5 bước 5): `prefix=mac` ⇒ đúng; `prefix=sha256` hoặc `prefix=none` ⇒ **SAI**. `valid=true` không chứng minh được dòng này — bộ verify nhận cả ba dạng | | | `DOC` / `STAGING` / **SAI** |
| 2 | Công thức MAC `sha256(app_id+data+timestamp+oa_secret_key)` | Từ **giờ bắt đầu soak** (§5 bước 3, ghi ở đây: `______`), ≥24h `grep 'zalo.signature'` **chỉ trên các dòng sau mốc đó và chỉ của lượt giao dịch thật** → **100%** `valid=true reason=ok bypassed=false`. Probe không ký ở §5 bước 3 và mọi lần dò URL đều sinh `reason=missing_header shape=absent` — loại chúng ra trước khi tính tỉ lệ, nếu không tỉ lệ không bao giờ chạm 100% | | | |
| 3 | Digest là hex thường | Cũng từ `shape=` của request thật: `hex=lower` ⇒ đúng; `hex=upper`/`hex=mixed` ⇒ **SAI** (code vẫn chạy vì so khớp có `.lower()`, nhưng dòng facts sai và phải sửa). `hex=caseless` = digest toàn chữ số, không kết luận được — chờ mẫu khác | | | |
| 4 | Trường message id `message.msg_id` | `SELECT count(*) FILTER (WHERE msg_id LIKE 'd:%') AS derived, count(*) AS total FROM zalo_updates;` — `derived = 0` ⇒ Zalo có gửi `msg_id`; `derived = total` ⇒ **không có**, khoá tổng hợp đang gánh | | | |
| 5 | Endpoint quota `/v3.0/oa/quota/message` → `data.remain`/`data.total` | `curl -sS -H "X-API-Key: $INTERNAL_API_KEY" https://<host>/api/v1/admin/zalo-quota/baseline` → `remain` khác `null` | | | |
| 6 | Mã lỗi token hết hạn `-216`, `-201` | `grep 'token rejected' <log>` — adapter log đúng chuỗi `Zalo OA <path>: token rejected (code=<mã>)` khi Zalo từ chối token, kèm việc nó có refresh rồi thử lại được không. Chỉ xuất hiện khi token thật sự hết hạn giữa một lần gọi, nên phải chờ mốc 1 giờ + có traffic (xem §6 bước 3). Không dựng được thì để trống — **đừng suy đoán** | | | |
| 7 | Nhãn/menu console (§2–§5 file này), **gồm cả chỗ đứng của OA Secret Key** (sửa 27/08/2026: `developers.zalo.me` → app → Official Account/Webhook, **không** phải `oa.zalo.me`) | Chính các ô "Ghi lại" ở trên | | | |
| 8 | Luồng cấp quyền OAuth v4 (§4) | URL thật đã dùng + có PKCE hay không | | | |

**Điều kiện đóng nhật ký này:** mọi dòng có kết luận. Dòng nào **SAI** thì
sửa code + bảng facts trong cùng một PR, rồi soak lại từ đầu — không
"promote một nửa".

Khi dòng #2 đạt, và **chỉ khi đó**, mới sang bước enforce:

```dotenv
ZALO_SIGNATURE_ENFORCE=true
```

Bất kỳ `valid=false` nào trong lúc soak đều **dừng** rollout cho tới khi
giải thích được nó. Chi tiết trình tự:
[`zalo-operations.md` §Signature soak](zalo-operations.md#signature-soak-rollout).

---

## 9. Xong console — bàn giao

Sau khi §1–§6 xong và nhật ký §8 bắt đầu chạy, phần còn lại là vận hành
bình thường:

- [ ] Chạy hết [Rollout checklist](zalo-operations.md#rollout-checklist).
- [ ] Smoke thật trên điện thoại: link tài khoản → ghi một khoản chi →
      hỏi báo cáo ngắn. Cả ba đều nằm trong
      [thin slice 5.0](zalo-operations.md#the-50-thin-slice--what-zalo-actually-serves).
- [ ] Cần dừng gấp: `ZALO_CHANNEL_ENABLED=false` + restart. Route không
      được mount nữa, webhook trả `404`, không có gì được xử lý dở dang.
      Chi tiết: [Rollback](zalo-operations.md#rollback).

> **`404` không làm Zalo im.** Zalo redeliver mọi phản hồi non-2xx (xem
> docstring `backend/routers/zalo.py`), nên trong lúc flag off nó vẫn gõ
> cửa, và những tin đó **chưa từng** được claim `msg_id` — dedup không chặn
> chúng. Bật flag lại là có thể ăn nguyên một lô tin cũ, xử lý như tin mới:
> bot trả lời một câu hỏi từ nhiều giờ trước, hoặc gửi trượt vì cửa sổ CS
> 48h đã đóng. Zalo retry trong bao lâu thì **chưa xác minh được** — thêm
> vào nhật ký §8 nếu quan sát được.
>
> Nên: dừng ngắn (vài phút, restart, deploy) thì cứ flag off là đủ. Dừng
> dài, hoặc dừng vì sự cố chưa rõ nguyên nhân, thì **tắt webhook trong
> Developer Console** — đó mới là thứ thật sự chặn nguồn. Bật lại console
> **sau** khi flag đã bật và service đã boot, đúng thứ tự §5.
