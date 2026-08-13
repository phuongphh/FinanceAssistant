# Release 11 — Deploy Notes (1.5.1.0)

> **Ngày deploy:** 2026-08-13
> **Branch:** `claude/merge-prod-release-11-h0tfix` → `prod` (qua PR)
> **Diff:** `origin/prod..HEAD` (45 commits — 35 substantive, còn lại `docs(issues): sync …`; 144 files, +27.510 −434)
> **Commit prod trước release:** `8b8e5c4 Merge pull request #1009 from phuongphh/claude/phase-4-7-prod-deploy-u77gl7`
> **APP_VERSION:** `1.4.7.0.1` → `1.5.1.0` (hiển thị ở `/about`, đồng thời bust cache miniapp qua `APP_VERSION_MARKER`)

## Tổng quan

Release 11 gom toàn bộ work kể từ release 10, gồm 4 hướng:

1. **Hotfix capture — "ăn trưa 180k"** (PR #1025): câu mô-tả-trước-số-sau không còn rơi
   vào "Mình chưa nhận ra số tiền" khi LLM trả về rỗng/lỗi/cache hỏng. **Đây là lý do
   release này tồn tại** — xem section _Root cause_ bên dưới.
2. **Phase 5.0 — Zalo OA channel** (PR #1008, #1010, #1012, #1013, #1017): OAuth token
   refresh, webhook signature verify, adapter CS message trong cửa sổ 48h. **Flag OFF**
   (`ZALO_CHANNEL_ENABLED=false`) — deploy trần không đổi hành vi.
3. **Phase 5.1 — Parity Telegram ↔ Zalo** (PR #1014, #1015): media URL cho ảnh riêng tư,
   dispatcher dùng chung cho mọi intent, Twin view/comparison/milestone trên Zalo,
   `users.telegram_id` nullable để Zalo làm kênh signup. Cũng sau cùng flag.
4. **Security & regression fixes** (PR #1011, #1020, #1022, #1024): siết
   `X-Forwarded-For`, Twin cache miss nhanh hơn, market snapshot không còn phụ thuộc
   Notion, dashboard fixes.

> ⚠️ **Toàn bộ surface Zalo của 5.0/5.1 nằm sau `ZALO_CHANNEL_ENABLED`, default `false`.**
> Deploy trần = hành vi Telegram y hệt pre-5.0. Chỉ có **hotfix capture** và **security
> fixes** là active ngay khi deploy — đó cũng chính là phần cần verify sau deploy.

---

## Root cause — vì sao "ăn trưa 180k" fail trên prod mà pass trên test

Nghi vấn ban đầu là "prod thiếu PR từ main". **Không phải.** `origin/prod` đúng là đi sau
`origin/main` 44 commit, nhưng toàn bộ đường capture — `action_quick_transaction.py`,
`bot/handlers/message.py`, `services/llm_service.py`, `intent/classifier/*`,
`content/intent_patterns.yaml` — **byte-identical giữa hai branch**. Cả hai env chạy cùng
một code path; khác biệt nằm ở state runtime.

Chuỗi thực tế với `"Ăn trưa 180k"` (mô tả trước, số sau):

1. Tier-1 regex trong `message.py` (`_AMOUNT_LED_TX_RE`, `_SIGNED_TX_RE`) **không match** —
   số nằm cuối, không có dấu. Rơi xuống intent pipeline.
2. Rule classifier: `content/intent_patterns.yaml` **không có** pattern
   `<description> <amount>` cho `action_quick_transaction` → không match high-confidence.
3. LLM classifier (Groq) trả `action_quick_transaction` **nhưng không kèm `amount`**
   (prompt chỉ nói "extract nếu có").
4. Handler rơi vào `_extract_single_item_with_llm` → gọi Groq `parse_manual` → trả `None`
   → `_FALLBACK_REPLY`.

Bước 4 là điểm chết: **LLM là thứ duy nhất đứng giữa một câu hoàn toàn parse được và lời
xin lỗi.** Nó fail vì bất kỳ lý do nào không liên quan tới nội dung tin nhắn — Groq blip,
timeout, `GROQ_API_KEY` thiếu trên box đó, budget cap, hoặc **một JSON reply hỏng bị pin
trong `llm_cache` 30 ngày**. Cái cuối giải thích tại sao cùng một câu fail lúc 13:31,
13:31 và 13:57 trong khi câu khác vẫn chạy: cache `parse_manual` scoped theo user, TTL 30
ngày, và `call_llm` cache ở tầng transport — nó lưu mọi thứ provider trả về, kể cả rác.

Ngược lại `"180k ăn trưa"` (số trước) match Tier-1 regex, **không bao giờ chạm LLM** — nên
luôn chạy trên prod. Đó là lý do hai dạng câu hành xử khác nhau trong cùng một deploy.

**Fix (PR #1025) — hai lớp:**

- **Safety net deterministic** trong `_extract_items`: khi LLM không trả gì, một regex
  parse chạy tại chỗ, không network. Cố ý bảo thủ — một token tiền rõ ràng + mô tả
  không rỗng, không thì từ chối và giữ nguyên câu trả lời trung thực. Từ chối thì rẻ; ghi
  nhầm một khoản chi user không hề tiêu thì không. Bail-out có kiểm soát: `%` (lãi suất
  6%), compound tail (`1tr2`, `1tr rưỡi`), nhiều token có đơn vị (câu multi-item), số trần
  < 1.000 (`cà phê 45` là số lượng/bàn, không phải 45đ).
- **`invalidate_cache()`** trong `llm_service.py`: parse không dùng được thì entry cache bị
  xoá thay vì phục vụ tiếp hết TTL. Bọc try/except — bookkeeping cache không bao giờ được
  làm mất giao dịch của user.

LLM vẫn giữ phần fuzzy (số viết bằng chữ, câu phức, nhiều khoản); regex chỉ nhận phần
digits + đơn vị.

**Cố ý KHÔNG làm trong release này:** thêm pattern `<description> <amount>` vào
`content/intent_patterns.yaml` (rủi ro cướp "mục tiêu 500tr" / "tiết kiệm 10tr");
gỡ mismatch `LLM_CLASSIFIER_TIMEOUT_SECONDS = 2.0` vs `timeout=3.0` (inner timeout là dead
code, không gây lỗi); chuyển `_FALLBACK_REPLY` hardcode sang `content/*.yaml` (nợ có sẵn,
không thuộc scope hotfix).

---

## PRs trong release này

| PR | Mô tả | Phase |
|---|---|---|
| [#1008](https://github.com/phuongphh/FinanceAssistant/pull/1008) | `docs(phase-5.0-5.2)`: phase docs Zalo + roadmap + fix 8 lỗ hổng thiết kế từ review | — |
| [#1010](https://github.com/phuongphh/FinanceAssistant/pull/1010) | `feat(zalo)`: Phase 5.0 — Zalo OA channel launch (reactive-first, flag OFF) | 5.0 |
| [#1011](https://github.com/phuongphh/FinanceAssistant/pull/1011) | `fix`: correct morning delta + hide miniapp build label | — |
| [#1012](https://github.com/phuongphh/FinanceAssistant/pull/1012) | `fix(zalo)`: address Codex review findings on Phase 5.0 + tests | 5.0 |
| [#1013](https://github.com/phuongphh/FinanceAssistant/pull/1013) | `docs(zalo)`: checklist thao tác Zalo Developer Console cho người vận hành | 5.0 |
| [#1015](https://github.com/phuongphh/FinanceAssistant/pull/1015) | `feat(phase-5.1)`: parity Telegram ↔ Zalo — media URL, dispatcher, Twin, signup | 5.1 |
| [#1017](https://github.com/phuongphh/FinanceAssistant/pull/1017) | `docs(zalo)`: address Codex review on console checklist | 5.0 |
| [#1020](https://github.com/phuongphh/FinanceAssistant/pull/1020) | `fix`: security — trust `X-Forwarded-For` chỉ từ proxy peer đã cấu hình (Closes #1019) | — |
| [#1022](https://github.com/phuongphh/FinanceAssistant/pull/1022) | `fix`: speed up Twin cache miss + refresh VNIndex daily (Closes #1021) | — |
| [#1024](https://github.com/phuongphh/FinanceAssistant/pull/1024) | `fix`: persist market snapshots without Notion + seed stock cache (Closes #1023) | — |
| [#1025](https://github.com/phuongphh/FinanceAssistant/pull/1025) | `fix(capture)`: ghi được "ăn trưa 180k" kể cả khi LLM không trả về gì | — |

---

## Migrations

Chạy theo thứ tự (`alembic upgrade head`) — chain nối tiếp head hiện tại của prod
(`20260712dqcohort46`):

| Thứ tự | Revision | down_revision | File | Mô tả |
|---|---|---|---|---|
| 1 | `20260802zalo50` | `20260712dqcohort46` | `20260802_phase50_zalo_channel.py` | 3 bảng additive: credentials, inbound dedup, 48h window |
| 2 | `20260803media51` | `20260802zalo50` | `20260803_phase51_media_objects.py` | Bảng `media_objects` — short-lived public URL cho ảnh riêng tư |
| 3 | `20260803tgnullable` | `20260803media51` | `20260803_phase51_telegram_id_nullable.py` | `users.telegram_id` **nullable** để Zalo làm kênh signup |
| 4 | `20260803zaloinvite` | `20260803tgnullable` | `20260803_phase51_zalo_telegram_invite.py` | Marker invite "qua Telegram luôn nhé" một lần / user |

```bash
docker compose exec backend alembic upgrade head
```

3/4 migration là additive thuần (thêm bảng / cột nullable). Riêng
**`20260803tgnullable` nới constraint** (`telegram_id` NOT NULL → nullable) — nới thì an
toàn khi apply, nhưng **downgrade sẽ fail nếu đã có row `telegram_id IS NULL`** (user
signup từ Zalo). Với `ZALO_CHANNEL_ENABLED=false` thì không thể phát sinh row như vậy, nên
rollback ở release này an toàn; sau khi bật kênh Zalo thì không còn.

---

## Config / env

`.env.example` **có đổi** trong release này. Ba nhóm:

| Env var | Default trong code | Prod sau deploy | Ghi chú |
|---|---|---|---|
| `TRUSTED_PROXY_CIDRS` | `127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7` | **Nên narrow về địa chỉ thật của Caddy** | Peer nào được phép nói thay người khác qua `X-Forwarded-For` (rate-limit key). App port đang publish → caller bypass Caddy **không** được tự chọn rate-limit key. Để rỗng = không tin ai, key theo peer thật |
| `ZALO_CHANNEL_ENABLED` | `false` | **giữ `false`** | Bật mới mount webhook router + notifier resolver |
| `ZALO_APP_ID` | `""` | để rỗng | Bắt buộc non-empty **nếu** bật kênh |
| `ZALO_OA_SECRET_KEY` | `""` | để rỗng | Webhook MAC component |
| `ZALO_APP_SECRET` | `""` | để rỗng | **Mới.** Gửi làm header `secret_key` khi refresh token — **không cùng giá trị** với `ZALO_OA_SECRET_KEY` |
| `ZALO_SIGNATURE_ENFORCE` | `true` | giữ `true` | Soak switch. Chỉ set `false` cho đợt soak ngắn đối chiếu công thức MAC với traffic thật (verify + log, không reject) |
| `ZALO_OA_ACCESS_TOKEN` | `""` | để rỗng | Legacy Phase 4B, chỉ là fallback khi chưa có row trong `zalo_oa_credentials` |
| `NOTION_MARKET_DB_ID` | — | **xoá khỏi `.env`** | Không còn đọc — market snapshot nay persist vào Postgres, không phụ thuộc Notion |

> ⚠️ **Fail-closed boot.** Với `ZALO_CHANNEL_ENABLED=true`, cả `ZALO_APP_ID` +
> `ZALO_OA_SECRET_KEY` + `ZALO_APP_SECRET` phải non-empty, nếu không app **từ chối boot**
> (`backend/main.py`, `assert_startup_invariant` — cố ý không bọc try/except). Webhook
> không verify được thì tệ hơn một kênh tắt hẳn; và thiếu `ZALO_APP_SECRET` sẽ boot ngon
> lành cho tới lần refresh token hourly rồi để lại write-ahead marker chỉ người mới clear
> được. **Ở release này giữ flag `false` nên không chạm tới đường này.**
>
> Khi nào bật kênh Zalo: seed credential bằng `python -m scripts.seed_zalo_credentials`,
> theo `docs/conventions/zalo-operations.md`.

Feature flag 4.5/4.6/4.7 **không đổi** ở release này — giữ nguyên giá trị prod đang chạy.
Cách set flag (`launchctl setenv` + kickstart, hoặc block `EnvironmentVariables` trong
launchd plist template) vẫn như release 10 — `.env` **không** đủ.

---

## Thay đổi đáng chú ý

### Hotfix capture (#1025)

- Safety net regex trong `_extract_items` — mô-tả-trước-số-sau ghi được kể cả khi LLM im
  lặng. Deterministic, không network.
- `invalidate_cache()` trong `llm_service.py` — parse không dùng được bị đuổi khỏi
  `llm_cache` thay vì phục vụ tiếp 30 ngày. Flush-only, router/worker vẫn giữ transaction
  boundary.
- 5 test mới cho handler (3 kịch bản LLM: error / unparseable / poisoned cache) + 3 test
  key-parity cho `invalidate_cache`.

### Phase 5.0 — Zalo OA channel, flag OFF (#1010, #1012, #1013, #1017)

- **OAuth token refresh** — `refresh_token` single-use, xoay mỗi lần refresh, giữ trong
  `zalo_oa_credentials` với write-ahead marker chống mất token khi crash giữa chừng.
- **Webhook verify `X-ZEvent-Signature`** + dedup inbound theo event id.
- **Adapter CS message** trong cửa sổ 48h, tối đa 8 tin tư vấn.
- **Thin slice**: capture thu chi + báo cáo chạy trên Zalo sau flag.
- Checklist thao tác Zalo Developer Console cho người vận hành
  (`docs/conventions/zalo-operations.md`).

### Phase 5.1 — Parity Telegram ↔ Zalo (#1015)

- **Media URL infrastructure** — ảnh riêng tư (Twin, chart) phục vụ qua URL ngắn hạn để
  Zalo fetch được, không lộ vĩnh viễn.
- **Dispatcher dùng chung** — mọi intent đi qua một đường, Zalo không còn nhánh riêng.
- **Twin view / comparison / milestone** render được trên Zalo; nút Telegram ánh xạ sang
  Zalo button template (giữ fallback text khi cắt 300 ký tự).
- **`users.telegram_id` nullable** — Zalo thành kênh signup thật; broadcast Telegram loại
  user không có `telegram_id`; invite "qua Telegram luôn nhé" gửi một lần.
- **Bộ test parity Telegram ↔ Zalo** chạy trong CI.

### Security & regression fixes (#1011, #1020, #1022, #1024)

- **`X-Forwarded-For` chỉ tin từ proxy peer đã cấu hình** (`TRUSTED_PROXY_CIDRS`) — trước
  đó caller đi thẳng vào app port có thể tự chọn rate-limit key của mình. Kèm fix hai
  đường bypass forwarded-header khác.
- **Twin cache miss nhanh hơn** + VNIndex refresh daily.
- **Market snapshot persist không cần Notion** — stock cache seed từ snapshot; bỏ
  `NOTION_MARKET_DB_ID`.
- **Morning delta đúng số** + ẩn build label trong miniapp.

---

## Pre-deploy checklist

- [ ] PR #1025 đã merge vào `main` trước khi merge release PR này vào `prod`
- [ ] `ZALO_CHANNEL_ENABLED` trên prod **vẫn `false`** (chưa tới lúc bật kênh)
- [ ] `TRUSTED_PROXY_CIDRS` đã review — narrow về địa chỉ Caddy nếu biết chắc
- [ ] Xoá `NOTION_MARKET_DB_ID` khỏi `.env` prod (vô hại nếu quên, chỉ là rác)
- [ ] DB backup snapshot trong vòng 24h gần nhất
- [ ] Telegram bot token & webhook URL không đổi
- [ ] Disk space VPS còn ≥ 20%
- [ ] CI `test` trên PR này PASS
- [ ] `pip install -r backend/requirements.txt` vào **cả hai** venv (`venv/` service +
      `.venv/` tooling) nếu deps đổi — xem `scripts/rebuild-finance-prod.sh`

---

## Rollback

```bash
git checkout prod
git pull origin prod
git revert -m 1 <merge-commit-sha>
git push origin prod
```

Commit prod trước release này: `8b8e5c4 Merge pull request #1009 from phuongphh/claude/phase-4-7-prod-deploy-u77gl7` (APP_VERSION `1.4.7.0.1`).

> ⚠️ 3/4 migration additive → **không bắt buộc** downgrade DB khi rollback code. Nếu vẫn
> muốn revert: `alembic downgrade 20260712dqcohort46`. Lưu ý `20260803tgnullable` chỉ
> downgrade được khi **không có** row `users.telegram_id IS NULL` — với flag Zalo OFF thì
> không thể phát sinh, nên ở release này an toàn.

**Rollback riêng hotfix capture:** không có flag. Nếu safety net regex đọc sai một dạng câu
nào đó ngoài dự tính, cách nhanh nhất là revert đúng commit `f325f48` rồi deploy lại —
phần còn lại của release không phụ thuộc nó.

---

## Sanity checks sau deploy

- [ ] `/about` hiển thị version `1.5.1.0`
- [ ] `alembic upgrade head` chạy clean → có bảng `media_objects` + các bảng Zalo
- [ ] Bot phản hồi `/start` bằng welcome message Bé Tiền
- [ ] **Hotfix:** gõ `ăn trưa 180k` → ghi nhận `-180.000đ`, mô tả `ăn trưa`, category food
- [ ] **Hotfix:** gõ lại đúng câu đó lần 2, lần 3 → vẫn ghi nhận (không rơi vào
      "chưa nhận ra số tiền")
- [ ] **Hotfix:** gõ `180k ăn trưa` (số trước) → vẫn ghi nhận như cũ, không regression
- [ ] **Hotfix — không ghi bừa:** `lãi suất 6%` và `cà phê 45` **không** tạo transaction
- [ ] Gửi 1 ảnh receipt → OCR trả kết quả < 15s
- [ ] Menu → Twin trả về bubble, ảnh Twin render đúng
- [ ] Miniapp dashboard load không lỗi, không phục vụ HTML cache cũ sau deploy
- [ ] **Zalo OFF:** không có route `/webhook/zalo` phản hồi; log boot không nhắc Zalo
- [ ] Rate limit vẫn hoạt động sau khi siết `X-Forwarded-For` — gọi API bình thường qua
      Caddy không bị 429 oan
- [ ] Market snapshot job chạy được **không** cần Notion credential
- [ ] Scheduler / hourly job chạy đúng ở lần fire đầu tiên, log không ERROR
- [ ] `docker compose logs backend --tail 100` — không ERROR/CRITICAL
