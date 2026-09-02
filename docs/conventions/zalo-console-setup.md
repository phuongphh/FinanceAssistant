# Zalo Console — Checklist thao tác (một lần, cho người vận hành)

Tài liệu này dành cho **người ngồi trước Zalo Developer Console**, không
phải cho người đọc code. Đi hết từ trên xuống, kết quả là:

1. Ba giá trị nằm đúng ba biến env: `ZALO_APP_ID`, `ZALO_APP_SECRET`,
   `ZALO_OA_SECRET_KEY`. Hai cái đầu lấy ở §2; cái thứ ba **chỉ hiện ra
   sau khi đã đăng ký Webhook URL** (§5 bước 5) — nó là thứ lấy sau cùng,
   không phải thứ lấy đầu tiên.
2. Một cặp `access_token` + `refresh_token` đã nằm trong bảng
   `zalo_oa_credentials` (từ đó app tự xoay, không cần vào console nữa).
3. Webhook trỏ về server, Zalo nhận URL đó, và **các sự kiện cần dùng đã
   được bật từng cái một** (console mặc định tắt hết — §5 bước 4).
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
>
> **Cập nhật 02/09/2026 — lần cài prod thật, nhìn tận mắt.** Ba chỗ trong
> file này đã được sửa từ `ASSUMED` thành quan sát thật, và cả ba đều là
> *sửa vì sai*, không phải sửa cho rõ hơn:
>
> 1. **Thứ tự §3 ↔ §5 bị đảo.** Trang *Webhook* không hiện ô OA Secret Key
>    nào cho tới khi Webhook URL đã đăng ký thành công. §3 bước 3 cũ bảo
>    lấy key ngay tại đó — không lấy được. Xem §3 và §5 bước 5.
> 2. **Mọi sự kiện webhook mặc định TẮT.** Bảng *Danh sách sự kiện webhook*
>    hiện ra với toàn bộ toggle off; không bật `user_send_text` thì tin
>    nhắn thật không bao giờ tới server, dù URL đã xác minh xong. §5 bước 4.
> 3. **`redirect_uri` đăng ký ở OA Manager**, không ở Developer Console:
>    *Official Account → Thiết lập chung → Official Account Callback Url*.
>    §4 bước 1.

---

## 0. Chuẩn bị trước khi mở console

- [ ] Tài khoản Zalo cá nhân là **admin** của Official Account Bé Tiền.
      Không phải admin thì không liên kết được OA vào app ở §3 — mà chưa
      liên kết thì không có OA Secret Key nào để lấy.
- [ ] Biết host prod/staging sẽ nhận webhook. Prod hiện tại:
      `https://finance.nuitruc.ai` (Caddy chạy ngoài Docker, reverse proxy
      về container `finance-backend` cổng `8002`).
- [ ] Có quyền đặt file tĩnh ở **thư mục gốc public** của host đó. Bước xác
      thực domain (§3 bước 2) cần đúng quyền này.
- [ ] Có quyền sửa `.env` trên server và chạy `python -m scripts.seed_zalo_credentials`.
- [ ] Biết rằng `.env` trên prod là **file chép tay**: `.env.example` không
      bao giờ tự lan sang nó, và `scripts/rebuild-finance-prod.sh` chỉ
      *kiểm tra* một danh sách khoá bắt buộc (`REQUIRED_ENV_KEYS`) mà trong
      đó **không có biến ZALO nào**. Nên ba biến ở §2–§3 sẽ không tự xuất
      hiện — phải tự thêm vào cuối `.env`. Tuyệt đối không `cp .env.example
      .env`, không `> .env`: prod `.env` không có backup ở đâu cả.
- [ ] Biết rằng đổi `.env` **bắt buộc** `docker compose … up -d
      --force-recreate`, không phải `docker restart`: compose chỉ đọc
      `env_file` lúc *tạo* container, restart dùng lại env cũ.
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
| `ZALO_OA_SECRET_KEY` | Cùng console, **khác màn hình**: app Bé Tiền → *Webhook*, nhãn *"OA Secret Key"* — che sẵn, bấm con mắt để hiện. **Ô này chỉ tồn tại sau khi Webhook URL đã đăng ký** (§5 bước 5) | Thành phần cuối của MAC webhook | Chỉ hỏng webhook — 100% tin vào bị 403 (chế độ enforce) |

**Chỗ dễ nhầm nhất, nói thẳng:** app secret và OA secret key là hai chuỗi
khác nhau, tên hiển thị gần giống nhau, và — trái với những gì tài liệu này
viết trước 27/08/2026 — **nằm trong cùng một console**, chỉ khác màn hình.
Không có cái nào ở `oa.zalo.me`. Đảo hai giá
trị này cho nhau là lỗi cài đặt phổ biến nhất — và nó **không báo lỗi lúc
boot**, vì invariant chỉ kiểm tra "có rỗng không", không kiểm tra "có
đúng chỗ không". Triệu chứng của việc đảo là *cả hai* thứ cùng hỏng, xem
§6.

Cái bẫy đi kèm, đã dính thật lúc cài prod: vì invariant chỉ kiểm tra rỗng,
mà OA Secret Key thật lại chưa lấy được cho tới §5, người vận hành rất dễ
dán tạm **app secret** vào `ZALO_OA_SECRET_KEY` cho app chịu boot. Nó boot
thật — nhưng từ lúc đó một secret thật nằm sai ô, và không có gì nhắc bạn
thay nó. Nếu cần giá trị tạm để qua invariant thì dùng một chuỗi rác nhìn
là biết, ví dụ `placeholder-until-webhook-registered`, đừng dùng một secret
thật (xem ô "con gà và quả trứng" đầu §5).

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

## 3. Màn hình B — vẫn ở Developer Console: liên kết OA + xác thực domain

> **Mục này đã bị sửa hai lần, vì hai lỗi khác nhau — đọc cả hai.**
>
> - **27/08/2026 — sai trang.** Bản đầu bảo mở `oa.zalo.me`. Trên
>   `oa.zalo.me` **không có** giá trị nào tên "OA Secret Key". Chỗ đúng là
>   **cùng console với §2**: `developers.zalo.me` → app Bé Tiền → *Webhook*.
> - **02/09/2026 — sai thứ tự.** Bản sau vẫn để việc lấy OA Secret Key làm
>   bước 3 của mục này. Không lấy được: trang *Webhook* **chưa hiện ô nào**
>   tên OA Secret Key cho tới khi Webhook URL đã đăng ký thành công. Bước
>   đó đã chuyển hẳn xuống **§5 bước 5**, và mục này chỉ còn hai bước.

Lý do thứ tự đúng lại là như vậy, chứ không phải console dấu đi cho khó:
key này gắn với bộ ba *(app, OA, webhook)*. Chưa có webhook đăng ký thì
chưa có gì để nó ký, nên nó chưa tồn tại — không phải "tồn tại nhưng ẩn".
Vì thế đừng đi tìm nó ở màn hình nào khác; nó vẫn là secret của **OA**
(mỗi OA liên kết vào app có một key riêng), chỉ là nơi hiển thị nằm trong
app chứ không nằm trong OA Manager.

Hai bước, đúng thứ tự — bước sau chỉ mở ra khi bước trước xong:

1. **Liên kết OA vào app.** Vẫn trong app ở §2: menu trái → *Official
   Account* → *Quản lý Official Account* → chọn OA Bé Tiền → *Liên kết* →
   đọc thông tin hiện ra → *Đồng ý*. Cần tài khoản admin của OA (§0).
   Chưa liên kết thì mục Webhook chưa dùng được.

   > **Liên kết ≠ cấp quyền.** Sau bước này, màn hình *Quản lý Official
   > Account* vẫn hiển thị **"0 OA được cấp quyền"**, và đó là bình thường,
   > không phải dấu hiệu liên kết hỏng. Bộ đếm chỉ nhảy lên 1 sau khi luồng
   > OAuth ở **§4** chạy xong (chính lúc bấm *Đồng ý* trên trang cấp quyền).
   > Đừng đi liên kết lại nhiều lần vì con số 0 đó.
2. **Xác thực domain** (*Domain Verification* / *Xác thực domain*). Console
   cho tải một file HTML; đặt nó ở **thư mục gốc public** của domain sẽ
   nhận webhook (`https://finance.nuitruc.ai/<tên file>.html` phải mở được từ ngoài),
   rồi bấm xác thực. Bỏ qua bước này thì hai thứ hỏng và triệu chứng **không
   nói gì về secret**:
   - console từ chối URL webhook ở §5 với lý do domain chưa xác thực;
   - luồng OAuth ở §4 trả `-14003 Invalid redirect uri` — dễ bị đọc nhầm
     thành "sai `redirect_uri`" rồi đi sửa URL vô ích.

Đến đây **dừng**. `ZALO_OA_SECRET_KEY` chưa lấy được và sẽ chưa lấy được
cho tới §5 bước 5. Đi tiếp sang §4.

> **Nếu sau này bấm reset OA Secret Key trong console** thì giá trị cũ chết
> ngay: mọi webhook sẽ `mac_mismatch` cho tới khi `.env` được cập nhật và
> container được **recreate** (không phải restart — xem §5 bước 5). Đừng
> reset để "thử cho chắc".

**Ghi lại:**

| Câu hỏi | Thực tế bạn thấy |
|---|---|
| Đường dẫn menu thật tới *Quản lý Official Account* | |
| Sau khi liên kết, bộ đếm "OA được cấp quyền" hiện là bao nhiêu? | |
| Bước xác thực domain: tên file, đặt ở đâu, mất bao lâu để console chấp nhận | |
| Hai secret có độ dài khác nhau không? (chỉ ghi độ dài, **không ghi giá trị**) — điền sau khi xong §5 bước 5 | |

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

1. Đăng ký `redirect_uri` trước — Zalo từ chối callback tới URL chưa đăng
   ký. Dùng đúng URL bạn sẽ mở ở bước 2. Domain của URL đó phải **đã xác
   thực** ở §3 bước 2; chưa xác thực thì bước 3 dưới đây trả `-14003
   Invalid redirect uri` dù URL gõ đúng từng ký tự.

   > **Chỗ đăng ký không nằm trong Developer Console** (quan sát thật
   > 02/09/2026 — trước đó file này chỉ nói chung chung "trong console").
   > Nó ở **OA Manager**: *Official Account → Thiết lập chung → Official
   > Account Callback Url*. Cùng lần cài đó cũng thấy: `Code Challenge`
   > (PKCE) và `State` là **tuỳ chọn**, bỏ trống vẫn qua.

   > **Đừng trỏ `redirect_uri` vào một đường dẫn do SPA phục vụ.** Admin
   > SPA có route catch-all `<Route path="*" element={<Navigate to="/"
   > replace />} />` (`betien-admin/src/App.jsx`), và cú `Navigate` đó **vứt
   > luôn query string** — trình duyệt nhảy về `/` và `code` biến mất trước
   > khi bạn kịp đọc. Triệu chứng đúng như vậy đã xảy ra thật: "redirect về
   > domain nhưng không có `code`". Dùng một path **không** do SPA phục vụ,
   > ví dụ `https://finance.nuitruc.ai/health`, rồi đọc `code` trên thanh
   > địa chỉ.
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
4. Đổi `code` lấy cặp token. Chạy trên server, nơi có `$ZALO_APP_SECRET`.
   Trên prod, biến env sống **trong container**, không có trong shell của
   VPS — nên chạy qua `exec` để không phải gõ secret ra dòng lệnh:

   ```bash
   cd /home/evg-user/FinanceAssistant
   docker compose -p financeassistant -f deploy/production/docker-compose.yml \
     exec backend sh -c '
       curl -sS -X POST https://oauth.zaloapp.com/v4/oa/access_token \
         -H "secret_key: $ZALO_APP_SECRET" \
         -d "app_id=$ZALO_APP_ID" \
         -d "grant_type=authorization_code" \
         -d "code=<code vừa lấy>"
     '
   ```

   Nháy đơn quanh khối `sh -c` là cố ý: nó để `$ZALO_APP_SECRET` được khai
   triển **bên trong** container chứ không phải ở shell VPS (nơi biến đó
   rỗng). Response có `access_token`/`refresh_token` — **đừng** chụp màn
   hình hay dán nguyên response đi đâu.

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
   lệnh nào — mọi lệnh đã gõ đều nằm lại trong history của shell
   (`~/.bash_history`, hoặc `~/.zsh_history` trên macOS), và `unset`
   chỉ xoá biến môi trường chứ không xoá history. Đọc vào biến bằng
   `read -rs` (không echo ra màn hình, không đi vào history):

   ```bash
   read -rs ZALO_BOOTSTRAP_ACCESS_TOKEN  && export ZALO_BOOTSTRAP_ACCESS_TOKEN
   read -rs ZALO_BOOTSTRAP_REFRESH_TOKEN && export ZALO_BOOTSTRAP_REFRESH_TOKEN
   python -m scripts.seed_zalo_credentials --app-id "$ZALO_APP_ID"
   unset ZALO_BOOTSTRAP_ACCESS_TOKEN ZALO_BOOTSTRAP_REFRESH_TOKEN
   ```

   Trên prod, script chạy trong container. Truyền hai biến qua `-e` (chỉ
   tên biến, **không** kèm giá trị — Docker tự lấy giá trị từ shell hiện
   tại, nên không có gì đi vào argv):

   ```bash
   docker compose -p financeassistant -f deploy/production/docker-compose.yml \
     exec -e ZALO_BOOTSTRAP_ACCESS_TOKEN -e ZALO_BOOTSTRAP_REFRESH_TOKEN \
     backend python -m scripts.seed_zalo_credentials --app-id "$ZALO_APP_ID"
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

   Trên prod:

   ```bash
   docker compose -p financeassistant -f deploy/production/docker-compose.yml \
     exec postgres psql -U finance -d finance -c \
     "SELECT app_id, expires_at, refresh_count, refresh_pending_at IS NOT NULL AS pending FROM zalo_oa_credentials;"
   ```

   Mong đợi: đúng 1 row, `pending = false`, và `expires_at` **~25 giờ tới**.

   > **Sửa 02/09/2026:** bản trước ghi "~1 giờ tới". Sai. Lần cài thật trả
   > `expires_in: 90000` giây = **25 giờ**. Con số này quan trọng vì §6
   > bước 3 bảo "đợi qua mốc hết hạn rồi nhắn tin để ép refresh" — đợi 1
   > giờ rồi kết luận "vòng xoay token hỏng" là kết luận sai.

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

> **Con gà và quả trứng — đọc trước khi sửa `.env`.**
>
> `assert_startup_invariant` (`backend/utils/zalo_signature.py`) chạy
> fail-closed lúc boot: `ZALO_CHANNEL_ENABLED=true` mà
> `ZALO_OA_SECRET_KEY` **rỗng** thì app không boot. Nhưng OA Secret Key
> thật lại chỉ hiện ra **sau** khi Webhook URL đăng ký xong (bước 5 dưới
> đây) — mà muốn đăng ký được URL thì route phải sống, tức flag phải bật.
> Vòng tròn khép kín.
>
> Lối ra: invariant chỉ kiểm tra **rỗng hay không**, nó không kiểm tra giá
> trị đúng hay sai. Nên đặt một giá trị tạm để qua invariant, rồi thay bằng
> key thật ở bước 5.
>
> **Giá trị tạm đó phải là một chuỗi rác nhìn là biết**, ví dụ
> `placeholder-until-webhook-registered`. **Tuyệt đối không dán một secret
> thật** (app secret chẳng hạn) vào đây cho "tiện" — đã xảy ra thật ngày
> 02/09/2026: app boot bình thường, và từ đó có một secret thật nằm sai ô,
> không có gì nhắc bạn thay nó, không có gì báo lỗi. Chuỗi rác thì bước 5
> nhìn phát biết ngay là chưa thay.

Vì vậy, đúng thứ tự này:

1. Trên server, đặt:

   ```dotenv
   ZALO_CHANNEL_ENABLED=true
   ZALO_SIGNATURE_ENFORCE=false     # soak — bắt buộc ở lần cài đầu tiên
   ZALO_OA_SECRET_KEY=placeholder-until-webhook-registered   # thay ở bước 5
   ```

   Ba biến này **sẽ không tự có** trong `.env` prod: file đó chép tay, và
   `REQUIRED_ENV_KEYS` của `scripts/rebuild-finance-prod.sh` không liệt kê
   biến ZALO nào. Thêm vào cuối file, đừng `cp .env.example .env`.

2. **Recreate container, không phải restart.** Compose chỉ đọc `env_file`
   lúc *tạo* container; `docker restart` dùng lại env cũ và bạn sẽ tưởng
   `.env` không có tác dụng:

   ```bash
   cd /home/evg-user/FinanceAssistant
   docker compose -p financeassistant -f deploy/production/docker-compose.yml \
     up -d --force-recreate backend
   ```

   App boot được nghĩa là cả ba biến đều **không rỗng** (invariant
   fail-closed đã chạy) — **không** nghĩa là chúng đúng. Boot fail thì
   thông báo lỗi gọi tên đúng biến còn thiếu — sửa rồi recreate lại.
3. Xác nhận route đã sống. Ghi lại **giờ bắt đầu soak** ngay lúc này (§8
   dòng #2 cần mốc đó):

   ```bash
   date -u +'%Y-%m-%dT%H:%M:%SZ'    # ghi vào §8 dòng #2
   curl -sS -o /dev/null -w "%{http_code}\n" \
     -X POST https://finance.nuitruc.ai/api/v1/zalo/webhook \
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
   | `404` | Flag chưa bật, hoặc container chưa được recreate (bước 2) |
   | `502` / `503` / `504` | Không tới được app (reverse proxy, hoặc service chết) — chưa phải chuyện của Zalo |
   | `407`, `3xx`, hoặc một trang HTML | Bạn đang nói chuyện với proxy/CDN, request chưa tới app |

   Chốt lại bằng log — chỉ log mới chứng minh chính app đã nhận:

   ```bash
   docker logs --tail 200 finance-backend 2>&1 | grep 'zalo.signature' | tail -1
   # zalo.signature valid=false reason=missing_header ... shape=absent
   ```

   `reason=missing_header` ở đây là **đúng mong đợi** cho một probe không ký.
   Nhớ nó: dòng này sẽ nằm trong log và không được tính vào tỉ lệ soak ở §8.

   > **Không thấy dòng nào cả?** Trước khi đi soi console, kiểm tra bản
   > build đang chạy có `_configure_logging()` trong `backend/main.py` hay
   > không. Dòng verdict này là `logger.info`; các bản trước 02/09/2026
   > không cấu hình root logger nào, nên uvicorn chỉ để lại
   > `logging.lastResort` (mức WARNING) — **mọi** `logger.info` của app bị
   > nuốt im lặng. Khi đó im lặng là trạng thái mặc định và **không chứng
   > minh được gì**: nó không phân biệt "chữ ký hợp lệ" với "chưa hề có sự
   > kiện nào tới". Nới rộng bộ lọc `grep` cũng vô ích. Nếu đang chạy bản
   > cũ: deploy bản mới rồi mới soak.
4. Quay lại Developer Console → phần *Webhook* của app → điền:

   - URL: `https://finance.nuitruc.ai/api/v1/zalo/webhook`
   - Bấm xác minh / lưu.
   - Rồi kéo xuống bảng ***Danh sách sự kiện webhook*** và **bật từng
     toggle cần dùng**: tối thiểu `user_send_text`, và nếu định nhận ảnh /
     ghi âm thì thêm `user_send_image`, `user_send_audio`, `follow`.

   > **Mọi toggle trong bảng đó mặc định TẮT** (quan sát thật 02/09/2026 —
   > bản trước của file này không hề nói đến bảng này). Đây là cái bẫy im
   > lặng nhất của cả quy trình: URL xác minh xanh, `curl` trả `200`, log
   > sạch — mà tin nhắn thật **không bao giờ** tới server, vì Zalo không
   > được phép gửi sự kiện nào. Không có thông báo lỗi nào cả. Bật
   > `user_send_text` trước khi kết luận bất cứ điều gì về chữ ký.
   >
   > Code coi cả hai tên `user_send_text` và `user_send_message` là sự kiện
   > text (`TEXT_EVENTS`, `backend/utils/zalo_events.py`); console thật chỉ
   > hiện `user_send_text`. Sự kiện khác app vẫn trả `200` rồi bỏ qua.

5. **Bây giờ mới lấy được OA Secret Key.** Đăng ký URL xong, trang *Webhook*
   mọc thêm ô **OA Secret Key** — che sẵn, bấm biểu tượng con mắt để hiện
   (cạnh nó là nút *Reset*: đừng đụng vào, xem cảnh báo cuối §3). Copy rồi:

   1. thay giá trị tạm ở bước 1 trong `.env`:
      `ZALO_OA_SECRET_KEY=<OA Secret Key thật>`;
   2. `up -d --force-recreate backend` một lần nữa (lại là recreate, không
      phải restart);
   3. kiểm tra bằng mắt: chuỗi này **phải khác** `ZALO_APP_SECRET` ở §2.
      Giống nhau nghĩa là đã copy nhầm, hoặc giá trị tạm chưa được thay.
      §6 bước 1 bắt được cả hai trường hợp bằng fingerprint.

6. Từ điện thoại, **nhắn một tin bất kỳ cho OA** rồi xem log — đây mới là
   bằng chứng thật:

   ```bash
   docker logs --tail 500 finance-backend 2>&1 | grep 'zalo.signature' | tail -5
   # zalo.signature valid=true reason=ok bypassed=false enforced=false shape=prefix=mac,hex=lower,len=64
   ```

   `valid=false reason=mac_mismatch` ở bước này gần như luôn là bước 5 lấy
   nhầm giá trị, dính khoảng trắng, hoặc quên recreate — sang §6.

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
| Ô OA Secret Key có thật sự chỉ hiện ra sau khi đăng ký URL không? | |
| Độ dài OA Secret Key (chỉ độ dài, **không ghi giá trị**) | |

---

## 6. Kiểm chứng — chứng minh ba giá trị nằm đúng chỗ

Đừng tin vào việc "nhìn thấy mình copy đúng". Ba lệnh dưới đây, mỗi lệnh
chứng minh một chuyện khác nhau.

**Bước 1 — không dính khoảng trắng, không trùng nhau.** In dấu vân tay,
không in giá trị:

```bash
# Trên prod, chạy trong container để đọc đúng env đã nạp:
#   docker compose -p financeassistant -f deploy/production/docker-compose.yml \
#     exec -T backend python - <<'PY'
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
  giờ khớp. Sửa `.env`, rồi `up -d --force-recreate backend` (§5 bước 2).
- `fp` của `zalo_app_secret` **trùng** `fp` của `zalo_oa_secret_key` ⇒ bạn
  đã dán cùng một giá trị vào hai chỗ, hoặc giá trị tạm ở §5 bước 1 chính
  là app secret và chưa được thay. Quay lại §5 bước 5.

**Bước 2 — OA Secret Key đúng?** Nhắn một tin cho OA từ điện thoại rồi:

```bash
docker logs --tail 500 finance-backend 2>&1 | grep 'zalo.signature' | tail -1
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
2. Đợi qua mốc đó — token sống **~25 giờ** (`expires_in: 90000`), không
   phải 1 giờ như bản trước của file này ghi. Nghĩa là bước kiểm chứng này
   không làm gọn trong một buổi được; lên lịch quay lại hôm sau.
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
| Mọi thứ đúng nhưng Zalo báo URL không hợp lệ | Flag `ZALO_CHANNEL_ENABLED` chưa bật hoặc container chưa recreate → route 404 |
| **Không có dòng `zalo.signature` nào trong log** | Không phải sai giá trị nào cả: bản build đang chạy thiếu `_configure_logging()` (`backend/main.py`) nên mọi `logger.info` bị nuốt — xem §5 bước 3 và §8 dòng #9. Cũng có thể toggle `user_send_text` chưa bật (§5 bước 4) nên chưa hề có sự kiện nào tới |

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
| 1 | Header value format `mac=<hex>` | Trường `shape=` của một request **thật** (§5 bước 6): `prefix=mac` ⇒ đúng; `prefix=sha256` hoặc `prefix=none` ⇒ **SAI**. `valid=true` không chứng minh được dòng này — bộ verify nhận cả ba dạng | | | `DOC` / `STAGING` / **SAI** |
| 2 | Công thức MAC `sha256(app_id+data+timestamp+oa_secret_key)` | Từ **giờ bắt đầu soak** (§5 bước 3, ghi ở đây: `______`), ≥24h `grep 'zalo.signature'` **chỉ trên các dòng sau mốc đó và chỉ của lượt giao dịch thật** → **100%** `valid=true reason=ok bypassed=false`. Probe không ký ở §5 bước 3 và mọi lần dò URL đều sinh `reason=missing_header shape=absent` — loại chúng ra trước khi tính tỉ lệ, nếu không tỉ lệ không bao giờ chạm 100% | | | |
| 3 | Digest là hex thường | Cũng từ `shape=` của request thật: `hex=lower` ⇒ đúng; `hex=upper`/`hex=mixed` ⇒ **SAI** (code vẫn chạy vì so khớp có `.lower()`, nhưng dòng facts sai và phải sửa). `hex=caseless` = digest toàn chữ số, không kết luận được — chờ mẫu khác | | | |
| 4 | Trường message id `message.msg_id` | `SELECT count(*) FILTER (WHERE msg_id LIKE 'd:%') AS derived, count(*) AS total FROM zalo_updates;` — `derived = 0` ⇒ Zalo có gửi `msg_id`; `derived = total` ⇒ **không có**, khoá tổng hợp đang gánh | | | |
| 5 | Endpoint quota `/v3.0/oa/quota/message` → `data.remain`/`data.total` | `curl -sS -H "X-API-Key: $INTERNAL_API_KEY" https://finance.nuitruc.ai/api/v1/admin/zalo-quota/baseline` → `remain` khác `null` | | | |
| 6 | Mã lỗi token hết hạn `-216`, `-201` | `docker logs --tail 500 finance-backend 2>&1 \| grep 'token rejected'` — adapter log đúng chuỗi `Zalo OA <path>: token rejected (code=<mã>)` khi Zalo từ chối token, kèm việc nó có refresh rồi thử lại được không. Chỉ xuất hiện khi token thật sự hết hạn giữa một lần gọi, nên phải chờ hết vòng đời token (~25 giờ, xem §6 bước 3) + có traffic. Không dựng được thì để trống — **đừng suy đoán** | | | |
| 7 | Nhãn/menu console (§2–§5 file này), **gồm cả chỗ đứng của OA Secret Key** | Chính các ô "Ghi lại" ở trên | Đã quan sát 02/09/2026: key nằm ở `developers.zalo.me` → app → *Webhook*, và **chỉ hiện sau khi đăng ký Webhook URL** (§5 bước 5); mọi toggle trong *Danh sách sự kiện webhook* mặc định **TẮT** (§5 bước 4) | 02/09/2026 | **SAI** (đã sửa §3/§5) |
| 8 | Luồng cấp quyền OAuth v4 (§4) | URL thật đã dùng + có PKCE hay không | Đã quan sát 02/09/2026: `redirect_uri` đăng ký ở **OA Manager** → *Thiết lập chung → Official Account Callback Url*, không ở Developer Console; `Code Challenge`/PKCE và `State` **tuỳ chọn**; `expires_in` = `90000`s (~25 giờ) | 02/09/2026 | **SAI** (đã sửa §4) |
| 9 | *(mới 02/09/2026)* Dòng verdict `zalo.signature` có thật sự vào được log prod không | `docker logs finance-backend 2>&1 \| grep 'zalo.signature'` | Trước 02/09/2026: **không**. `backend/main.py` không cấu hình root logger, uvicorn cũng không, nên mọi `logger.info` rơi vào `logging.lastResort` (mức WARNING) và bị nuốt. Mọi mẫu soak lấy trước bản có `_configure_logging()` là **vô giá trị** — im lặng không phân biệt "hợp lệ" với "chưa có sự kiện nào" | 02/09/2026 | Đã sửa — soak lại từ đầu trên bản mới |

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
- [ ] Cần dừng gấp: `ZALO_CHANNEL_ENABLED=false` + `up -d --force-recreate
      backend` (§5 bước 2 — restart không đọc lại `.env`). Route không
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
