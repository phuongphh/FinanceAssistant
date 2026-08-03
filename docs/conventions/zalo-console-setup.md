# Zalo Console — Checklist thao tác (một lần, cho người vận hành)

Tài liệu này dành cho **người ngồi trước Zalo Developer Console**, không
phải cho người đọc code. Đi hết từ trên xuống, kết quả là:

1. Ba giá trị nằm đúng ba biến env: `ZALO_APP_ID`, `ZALO_APP_SECRET`,
   `ZALO_OA_SECRET_KEY`.
2. Webhook trỏ về server và Zalo nhận URL đó.
3. Một cặp `access_token` + `refresh_token` đã nằm trong bảng
   `zalo_oa_credentials` (từ đó app tự xoay, không cần vào console nữa).
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

---

## 0. Chuẩn bị trước khi mở console

- [ ] Tài khoản Zalo cá nhân là **admin** của Official Account Bé Tiền.
      Không phải admin thì không thấy được OA Secret Key ở §3.
- [ ] Biết host prod/staging sẽ nhận webhook (`https://<host>`).
- [ ] Có quyền sửa `.env` trên server và chạy `python -m scripts.seed_zalo_credentials`.
- [ ] **Chưa** bật `ZALO_CHANNEL_ENABLED=true`. Bật ở §4, đúng thứ tự,
      vì bật sớm với env rỗng thì app **không boot** (invariant fail-closed).

---

## 1. Ba giá trị — nhìn tổng thể trước khi đi lấy

Đây là bảng quan trọng nhất của tài liệu. Hai trong ba giá trị đều được
console gọi là **"Secret Key"**, ở hai nơi khác nhau, và **không thể thay
cho nhau**.

| Biến env | Console nào | Dùng để làm gì | Lấy sai thì hỏng cái gì |
|---|---|---|---|
| `ZALO_APP_ID` | Developer Console (`developers.zalo.me`) → app Bé Tiền | Thành phần đầu của MAC webhook; body của refresh token | Hỏng **cả hai** — webhook mismatch *và* refresh fail |
| `ZALO_APP_SECRET` | Cùng màn hình với `app_id`, nhãn ~ *"Secret Key"* của **ứng dụng** | Header `secret_key` khi refresh token | Chỉ hỏng refresh — im lặng đúng 1 giờ rồi bot câm |
| `ZALO_OA_SECRET_KEY` | OA Manager (`oa.zalo.me`) → cài đặt OA, nhãn ~ *"Secret Key"* của **OA** | Thành phần cuối của MAC webhook | Chỉ hỏng webhook — 100% tin vào bị 403 (chế độ enforce) |

**Chỗ dễ nhầm nhất, nói thẳng:** app secret và OA secret key là hai chuỗi
khác nhau, cùng tên hiển thị, lấy ở hai console khác nhau. Đảo hai giá
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

## 3. Màn hình B — OA Manager: lấy OA Secret Key

Đây là màn hình **khác console** với §2. Nếu bạn vẫn đang ở
`developers.zalo.me` và thấy một ô "Secret Key", khả năng cao đó vẫn là
secret của ứng dụng — dừng lại và kiểm tra tên miền trên thanh địa chỉ.

1. Mở `https://oa.zalo.me` → chọn Official Account Bé Tiền.
2. Vào phần cài đặt / thông tin OA (*Cài đặt OA* → *Thông tin xác thực* /
   tương đương). Ở một số phiên bản console, giá trị này nằm trong mục
   webhook của chính OA — nếu bạn tìm thấy nó ở đó, đó vẫn là giá trị đúng,
   miễn là nó thuộc **OA**, không thuộc **ứng dụng**.
3. Copy giá trị, dán vào:

   ```dotenv
   ZALO_OA_SECRET_KEY=<secret key của OA>
   ```

4. Kiểm tra ngay tại chỗ, bằng mắt: chuỗi này **phải khác** chuỗi ở §2.
   Giống nhau nghĩa là bạn copy lại đúng một giá trị.

**Ghi lại:**

| Câu hỏi | Thực tế bạn thấy |
|---|---|
| Đường dẫn menu thật tới OA Secret Key | |
| Nhãn hiển thị | |
| Nó nằm ở `oa.zalo.me` hay `developers.zalo.me`? | |
| Hai secret có độ dài khác nhau không? (chỉ ghi độ dài, **không ghi giá trị**) | |

> **Không bao giờ** viết giá trị thật của ba biến này vào bất kỳ file nào
> trong repo, kể cả tài liệu này, kể cả "tạm để nhớ". Ghi độ dài và
> fingerprint (§6) là đủ để đối chiếu.

---

## 4. Trỏ webhook — **thứ tự các bước là quan trọng**

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
3. Xác nhận route đã sống:

   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" -X POST https://<host>/api/v1/zalo/webhook \
     -H 'Content-Type: application/json' -d '{}'
   ```

   Mong đợi: **không** phải `404`. (`400`/`200` đều chấp nhận được ở bước
   này — ta chỉ đang hỏi "route có được mount không". `404` = flag chưa
   bật hoặc service chưa restart.)
4. Quay lại Developer Console → phần Webhook của app → điền:

   - URL: `https://<host>/api/v1/zalo/webhook`
   - Sự kiện cần bật: `user_send_text` và `user_send_message`.
     Các sự kiện khác (follow/unfollow/receipt) app vẫn trả `200` rồi bỏ
     qua, bật thêm không sai nhưng không có tác dụng gì ở 5.0.

5. Bấm xác minh / lưu. Rồi từ điện thoại, **nhắn một tin bất kỳ cho OA** và
   xem log — đây mới là bằng chứng thật:

   ```bash
   grep 'zalo.signature' <log> | tail -5
   # zalo.signature valid=true reason=ok bypassed=false enforced=false
   ```

   `valid=false reason=mac_mismatch` ở bước này gần như luôn là §3 lấy
   nhầm giá trị (hoặc dính khoảng trắng) — sang §6.

**Ghi lại:**

| Câu hỏi | Thực tế bạn thấy |
|---|---|
| Đường dẫn menu tới ô webhook | |
| Console có nút "xác minh URL" riêng không? Nó gửi gì? (status code server trả) | |
| Danh sách tên sự kiện console hiển thị (đúng chính tả) | |

---

## 5. Authorise OAuth — lấy cặp token đầu tiên

App tự xoay token sau khi có cặp đầu tiên. Cặp đầu tiên phải lấy tay, và
đây là lần duy nhất (trừ khi phải khôi phục theo runbook).

1. Đăng ký `redirect_uri` trong console trước — Zalo từ chối callback tới
   URL chưa đăng ký. Dùng đúng URL bạn sẽ mở ở bước 2.
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
   đọc status code. `error != 0` ở đây, với `code` còn hạn, nghĩa là
   `ZALO_APP_SECRET` sai → quay lại §2.
5. Nạp cặp token vào DB. Truyền qua env, **không** qua argv (argv hiện
   trong `ps` của mọi process trên máy):

   ```bash
   export ZALO_BOOTSTRAP_ACCESS_TOKEN='<access_token>'
   export ZALO_BOOTSTRAP_REFRESH_TOKEN='<refresh_token>'
   python -m scripts.seed_zalo_credentials --app-id "$ZALO_APP_ID"
   unset ZALO_BOOTSTRAP_ACCESS_TOKEN ZALO_BOOTSTRAP_REFRESH_TOKEN
   ```

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

**Bước 3 — App Secret đúng?** Nếu §5 chạy lọt (`error: 0`) thì đã chứng
minh rồi. Muốn chắc thêm, để service chạy qua mốc 1 giờ rồi:

```sql
SELECT refresh_count, last_refreshed_at, refresh_pending_at IS NOT NULL AS pending
FROM zalo_oa_credentials;
```

`refresh_count` tăng, `pending = false` ⇒ vòng xoay token đang chạy đúng.

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
| 1 | Header value format `mac=<hex>` | Log request thật: giá trị `X-ZEvent-Signature` có tiền tố `mac=` không | | | `DOC` / `STAGING` / **SAI** |
| 2 | Công thức MAC `sha256(app_id+data+timestamp+oa_secret_key)` | ≥24h `grep 'zalo.signature'` → **100%** `valid=true reason=ok bypassed=false` | | | |
| 3 | Digest là hex thường | Suy ra từ #2: so khớp có `.lower()`, nên #2 pass không loại được hex hoa. Chỉ ghi `STAGING` nếu đọc được digest thật trong log | | | |
| 4 | Trường message id `message.msg_id` | `SELECT count(*) FILTER (WHERE msg_id LIKE 'd:%') AS derived, count(*) AS total FROM zalo_updates;` — `derived = 0` ⇒ Zalo có gửi `msg_id`; `derived = total` ⇒ **không có**, khoá tổng hợp đang gánh | | | |
| 5 | Endpoint quota `/v3.0/oa/quota/message` → `data.remain`/`data.total` | `curl -sS -H "X-API-Key: $INTERNAL_API_KEY" https://<host>/api/v1/admin/zalo-quota/baseline` → `remain` khác `null` | | | |
| 6 | Mã lỗi token hết hạn `-216`, `-201` | Sau ≥2 lần xoay token, `grep 'zalo.send'` tìm mã lỗi thật kèm hành vi retry. Không dựng được thì để trống — **đừng suy đoán** | | | |
| 7 | Nhãn/menu console (§2–§5 file này) | Chính các ô "Ghi lại" ở trên | | | |
| 8 | Luồng cấp quyền OAuth v4 (§5) | URL thật đã dùng + có PKCE hay không | | | |

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
- [ ] Cần dừng gấp: `ZALO_CHANNEL_ENABLED=false` + restart. Console không
      phải đụng tới — webhook thành `404`, Zalo tự thôi.
