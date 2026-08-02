# Zalo OA — Operations & Platform Facts

Phase 5.0 (Zalo Channel Launch). This document is the **single source of
truth for every Zalo platform constant used in code**. If a number, a
header name, a URL or an event name appears in `backend/`, it must trace
back to a row in [Platform facts](#platform-facts) below.

> Why this file exists: Phase 4B shipped the Zalo adapter twice against
> assumed platform behaviour and was wrong both times (signature formula,
> token lifetime). "Code first, verify later" is banned for this channel.

---

## Platform facts

**Provenance legend**

| Tag | Meaning |
|---|---|
| `DOC` | Read off Zalo's developer documentation |
| `STAGING` | Reproduced against the real OA on staging |
| `ASSUMED` | Taken from the Phase 5.0 plan, **not yet reproduced** |

Rows marked `ASSUMED` are the ones that can still burn us. `#1.1` is not
closed until every row below reads `DOC` **and** the rows marked
"needs staging" also read `STAGING`.

**Verified: pending operator sign-off (drafted 02/08/2026).**

### Webhook

| Fact | Value | Provenance |
|---|---|---|
| Signature header | `X-ZEvent-Signature` | `DOC` (4B, in production) |
| Header value format | `mac=<hex>` — bare `<hex>` also accepted defensively | `ASSUMED` — needs staging |
| MAC formula | `sha256(app_id + data + timestamp + oa_secret_key)` where `data` is the **raw request body string** and `timestamp` is the `timestamp` field **inside** that body | `ASSUMED` — needs staging |
| MAC is *not* | HMAC keyed on the secret over the raw body (what 4B shipped) | `ASSUMED` |
| Digest encoding | lowercase hex | `ASSUMED` |
| Retry behaviour | Zalo re-delivers on any non-2xx response | `DOC` |
| Inbound text events | `user_send_text`, `user_send_message` | `DOC` (4B, in production) |
| Message id field | `message.msg_id` | `ASSUMED` — needs staging |

Consequences encoded in code:

- `backend/utils/zalo_signature.py` implements the MAC formula and
  nothing else. One function, one test vector, no callers reimplementing it.
- Because the formula row is `ASSUMED`, `ZALO_SIGNATURE_ENFORCE=false`
  exists: it verifies and **logs** the verdict without rejecting, so the
  formula can be confirmed against live traffic during a soak before the
  channel starts rejecting real users. See
  [Signature soak](#signature-soak-rollout).
- Because Zalo retries on non-2xx, the webhook returns `200` for every
  well-formed event, including ones we deliberately ignore. Dedup is on
  `msg_id` (`zalo_updates`), not on "did we reply".

### OAuth / token lifecycle

| Fact | Value | Provenance |
|---|---|---|
| Refresh endpoint | `POST https://oauth.zaloapp.com/v4/oa/access_token` | `DOC` |
| Refresh auth | header `secret_key: <APP_SECRET>` | `DOC` |
| Refresh body | form-encoded `app_id`, `grant_type=refresh_token`, `refresh_token` | `DOC` |
| `access_token` lifetime | 1 hour | `DOC` |
| `refresh_token` lifetime | 3 months | `DOC` |
| `refresh_token` reuse | **single-use** — every successful refresh returns a new one and invalidates the old one server-side | `DOC` |
| Refresh threshold used in code | refresh when `expires_at - now < 5 minutes` | ours — see `zalo_token_service.REFRESH_SKEW` |

The single-use property is the whole reason `zalo_token_service` looks
the way it does. See [Token refresh protocol](#token-refresh-protocol).

### Message sending

| Fact | Value | Provenance |
|---|---|---|
| CS message endpoint | `POST https://openapi.zalo.me/v3.0/oa/message/cs` | `DOC` |
| Quota endpoint | `GET https://openapi.zalo.me/v3.0/oa/quota/message` → `data.remain` / `data.total` | `ASSUMED` — needs staging |
| Auth | header `access_token: <token>` | `DOC` |
| Error signalling | HTTP `200` **plus** a non-zero `error` field in the body | `DOC` |
| Token-expired error codes | `-216`, `-201` | `ASSUMED` — needs staging |
| Retryable transient codes | `-32`, `-239` | `DOC` (4B) |
| Rate limit | ~10 requests/second per OA | `DOC` |
| Reply window | 48 hours from the user's last inbound message | `DOC` |
| Free messages per window | 8 consulting messages | `DOC` |
| Display length | ~300 characters | `DOC` (4B) |
| Markdown | not supported — plain text only | `DOC` (4B) |
| Images | require a public URL; raw bytes are not accepted | `DOC` (4B) |
| Inline keyboards | not used in 5.0 | product decision |

Because app-level errors arrive as HTTP 200, `ZaloOAClient._post` must
inspect the body on every response. A bare `resp.raise_for_status()` is
a bug in this adapter.

---

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `ZALO_CHANNEL_ENABLED` | `false` | Master switch. Off ⇒ webhook route is not mounted and the resolver never returns a Zalo target. Off is byte-identical to pre-5.0 behaviour. |
| `ZALO_APP_ID` | `""` | Zalo application id. Part of the MAC input. |
| `ZALO_APP_SECRET` | `""` | Application secret. Sent as `secret_key` on token refresh. |
| `ZALO_OA_SECRET_KEY` | `""` | OA secret key. Trailing component of the MAC input. |
| `ZALO_SIGNATURE_ENFORCE` | `true` | `false` puts signature verification in log-only mode for a soak. Never leave it false. |
| `ZALO_OA_ACCESS_TOKEN` | `""` | Legacy static token (Phase 4B). Only used as a fallback when no DB credential row exists. |

### Fail-closed startup invariant

If `ZALO_CHANNEL_ENABLED=true` and `ZALO_OA_SECRET_KEY` is empty, the
application **refuses to boot**. There is no "channel on, verification
off" state: that combination accepts unauthenticated writes to a
messaging channel from anyone who finds the URL.

The dev bypass (empty secret ⇒ skip verification) is legal only while
the channel is off, where the route isn't mounted anyway.

Implemented in `backend/main.py` lifespan via
`backend.utils.zalo_signature.assert_startup_invariant`.

### Signature soak rollout

The MAC formula row is `ASSUMED`. Rolling it straight to enforcing means
a wrong guess yields 403 on 100% of webhooks — the exact 4B failure.
Sequence instead:

1. Deploy with `ZALO_CHANNEL_ENABLED=true`, `ZALO_SIGNATURE_ENFORCE=false`.
2. Watch `zalo.signature` log records for ≥24h of real traffic.
   `valid=true` on every record ⇒ the formula is right; promote the
   MAC row above from `ASSUMED` to `STAGING`.
3. Set `ZALO_SIGNATURE_ENFORCE=true`.

Any `valid=false` during the soak stops the rollout — do not enforce
until it's explained.

---

## Token refresh protocol

`access_token` lives 1 hour; `refresh_token` lives 3 months but is
**single-use and rotates on every refresh**. Losing the current
`refresh_token` means a human has to re-authorise the OA by hand.

A plain "call Zalo, then commit the result" is unsafe: Zalo invalidates
the old refresh token the moment the HTTP call succeeds, so a crash
between the response and the commit loses the only usable token. A DB
transaction does not help — the damage is on Zalo's side, outside it.

So `zalo_token_service` uses a write-ahead protocol:

```
  1. pg_advisory_xact_lock(app_id)      -- only one refresher at a time
  2. re-read the row                     -- someone may have refreshed while we waited
  3. COMMIT refresh_pending = {token, attempted_at}
  4. POST /v4/oa/access_token
  5. COMMIT new access_token + new refresh_token, refresh_pending = NULL
```

If the process dies between 3 and 5, the row comes back with
`refresh_pending` set and we **cannot know** whether Zalo consumed the
token. Blind-retrying would burn a token that may still be the only
valid one. So on startup a pending row makes the service log `CRITICAL`
and raise, pointing here. Failing loudly beats failing silently and
un-diagnosably three months later.

### Runbook: `refresh_pending` found on startup

Symptom: `CRITICAL zalo.token.refresh_pending` and Zalo sends failing.

1. Try the pending `refresh_token` **once**, by hand:

   ```bash
   curl -X POST https://oauth.zaloapp.com/v4/oa/access_token \
     -H "secret_key: $ZALO_APP_SECRET" \
     -d "app_id=$ZALO_APP_ID" \
     -d "grant_type=refresh_token" \
     -d "refresh_token=<pending refresh_token from the DB row>"
   ```

2. Success ⇒ seed the returned pair and clear the pending column:

   ```bash
   python -m scripts.seed_zalo_credentials \
     --app-id "$ZALO_APP_ID" \
     --access-token "<new access_token>" \
     --refresh-token "<new refresh_token>" \
     --expires-in 3600
   ```

   (The seed script clears `refresh_pending` as part of the upsert.)

3. Failure (`error != 0`) ⇒ the token was consumed. Re-authorise the OA
   through Zalo's OAuth consent flow, then seed the fresh pair with the
   same command.

Do not automate step 1. It is a one-shot decision that has to be made by
a human looking at the response.

### Runbook: manual OA re-authorisation

1. Open the Zalo OA console → *Quản lý ứng dụng* → the Bé Tiền app.
2. Run the OAuth consent flow for the OA; capture `access_token` and
   `refresh_token` from the callback.
3. Seed them with `python -m scripts.seed_zalo_credentials` (above).
4. Confirm recovery: one CS message to a staff Zalo account inside an
   open 48h window.

---

## 48-hour window and the 8-message quota

Zalo permits consulting (CS) messages only within 48 hours of the user's
last inbound message, capped at 8 per window.

`zalo_message_window` tracks both, and the accounting rule is that
**quota is reserved before the send, not after**:

```
  reserve_send():  UPDATE ... SET free_msg_count = free_msg_count + 1
                   WHERE window_expires_at > now() AND free_msg_count < 8
                   RETURNING free_msg_count          -- committed immediately
  <send>
  release_send():  compensating decrement, only for non-quota failures
```

Checking then sending is a TOCTOU race: two jobs both reading
`free_msg_count == 7` both send, and 9 messages leave. Reserving first
makes the database the arbiter. `can_send()` exists but is
**observability only** — it must never gate a send.

`release_send()` deliberately does *not* fire when Zalo rejects for
quota or window reasons: in that case Zalo counted the attempt too, and
giving the slot back would let us over-send.

All window arithmetic is in UTC. `window_expires_at` is a stored
timestamp, never a recomputed local-time boundary, so nothing changes
across the Asia/Ho_Chi_Minh offset.

### Runbook: user reports "Bé Tiền stopped replying on Zalo"

1. Was their last inbound message >48h ago? Then the window is closed
   and this is correct behaviour — Zalo forbids the send. They reopen it
   by messaging the OA.
2. Window open but nothing arrives ⇒ check `zalo.send.blocked` logs for
   the reason. The vocabulary is closed — it is
   `zalo_window_service.BLOCK_REASONS`, and every counter in the snapshot
   endpoint is keyed on exactly these five strings:
   - `no_window` — we have never recorded an inbound message from this
     sender, so there is no window row at all. Usually an unlinked
     account, or a proactive send to someone who only ever used Telegram.
   - `window_closed` — as above: a window exists but expired.
   - `quota_exhausted` — 8 sends already used this window.
   - `not_configured` — no credential row and no static token; see the
     re-authorisation runbook.
   - `send_failed` — transport error; the `error` code is in the log.

   A reason outside this list means code and runbook have drifted apart;
   the snapshot endpoint raises `zalo_block_reason_unknown` for it.

Log lines carry the **masked** sender (`mask_zalo_id`) and never the
message body. The matching analytics events carry no identifier at all —
they are only ever read in aggregate.

Proactive messages (briefings, empathy nudges) are **expected** to be
dropped on Zalo outside the window. Zalo is a reactive-first channel by
decision (02/08/2026); proactive delivery lives on Telegram. Dropping is
the designed outcome, not an incident.

### Runbook: quota drift (internal count vs. Zalo's count)

Our ledger and Zalo's are two independent counters of the same thing. If
they disagree, one of them is wrong about how much allowance is left, and
the failure mode is silent: we keep sending against a budget that is
already spent, and Zalo starts rejecting.

Reconciliation compares **movement against movement**, never a single
reading — Zalo's `remain` is per-OA and ours is per-sender, so the
absolute numbers are not comparable and were never meant to be. Two
calls, both requiring `X-API-Key: $INTERNAL_API_KEY`:

```bash
# 1. Where is Zalo now? Save `remain` and `captured_at` verbatim.
curl -sS -H "X-API-Key: $INTERNAL_API_KEY" \
  https://<host>/api/v1/admin/zalo-quota/baseline

# 2. Later — an hour, a day — compare the two movements.
curl -sS -H "X-API-Key: $INTERNAL_API_KEY" \
  "https://<host>/api/v1/admin/zalo-quota/snapshot?baseline_remain=<remain>&baseline_at=<captured_at>"
```

`remain: null` from step 1 means the read failed. Save nothing and
retry: a baseline captured from an unknown is not a baseline.

Read `reconciliation.status` in the response:

| Status | Meaning | Action |
|---|---|---|
| `ok` | Both movements known. `drift` is the disagreement, in messages. | `drift > 1` ⇒ investigate (see below). `drift ≤ 1` is expected — it is the crash-between-reserve-and-send case the accounting deliberately allows. |
| `quota_unavailable` | Zalo's counter could not be read. **Not** a drift of zero. | Check the token (`zalo.quota.read_failed` in the logs). Internal counters in the same response are still correct and still worth reading. |
| `need_baseline` | No baseline was supplied. | Do step 1. |
| `baseline_stale` | Zalo's `remain` went **up** since the baseline — the quota period rolled over, so the interval spans a reset. | Re-baseline. Not an incident. |

Alert codes appear in `alerts[]` with Vietnamese operator-facing text:
`zalo_quota_drift`, `zalo_quota_unavailable`, `zalo_quota_baseline_stale`,
`zalo_quota_need_baseline`, `zalo_quota_exhausted_high`,
`zalo_not_configured`, `zalo_block_reason_unknown`. The drift threshold
is `zalo_quota_metrics.ALERT_QUOTA_DRIFT_TOLERANCE` (currently `1`).

When `drift > 1`, in order:

1. Did someone send to the OA from outside this application (Zalo
   console, another integration, a staging server pointed at the same
   OA)? Zalo counts those; we do not. This is the most common cause and
   it is not a bug.
2. Compare `delivered` against `window_ledger.slots_used_open`. Ours
   counting *higher* than Zalo's consumption means we spent slots on
   sends that never left — look for `send_failed` in
   `blocked_by_reason`, and for `zalo.window.release_failed` in the logs
   (a compensation that itself failed leaves the slot spent).
3. Ours counting *lower* means the ceiling is not holding. Set
   `ZALO_CHANNEL_ENABLED=false` and restart before diagnosing further —
   over-sending gets the OA rate-limited, and the flag is the fast stop.

Two notes on the endpoints themselves. `?read_quota=false` skips the
network call and returns the internal half instantly — use it while
refreshing repeatedly during an incident, since Zalo rate-limits us at
~10 req/s. And both routes stay mounted when `ZALO_CHANNEL_ENABLED=false`,
by design: they send nothing and touch no user surface, and unmounting
the instrument exactly when an incident starts would remove the only
view of what happened.

---

## The 5.0 thin slice — what Zalo actually serves

Zalo is not a second front door onto the whole product. Phase 5.0 ships a
**whitelist**, `zalo_inbound.ZALO_SUPPORTED_INTENTS`, and everything
outside it gets one reply pointing at Telegram (`content/zalo.yaml`,
`fallback.body`).

| Served on Zalo | Not served — falls back |
|---|---|
| Ghi thu/chi (`action_quick_transaction`) | Sửa/xoá giao dịch |
| Báo cáo chi tiêu, theo danh mục | Twin view, so sánh kịch bản |
| Tổng tài sản, danh sách tài sản | Onboarding, đặt mục tiêu |
| Chào hỏi, trợ giúp | Mọi advisory dài, ảnh/biểu đồ |

Three rules hold this together, and each is enforced in a different
place — worth knowing which, because the failure looks different:

- **Whitelist** — a non-whitelisted intent never reaches its service. If
  a user reports "Bé Tiền trả lời sai câu hỏi" on Zalo, check the intent
  against the frozenset before looking at the service.
- **Copy** — every Zalo-bound string lives in `content/zalo.yaml` and is
  held to plain text, ≤300 chars, ≤2 emoji by
  `tests/test_phase_5_0/test_zalo_copy_contract.py`. Copy that violates
  the channel fails the build; it does not get silently rewritten on the
  way out.
- **Rendering** — `ZaloContentRenderer` implements `render_briefing` and
  **raises** on Twin/comparison/milestone. In 5.0 those raises are
  unreachable by design: Twin intents are outside the whitelist and
  briefings are proactive, so nothing on the Zalo path calls them. The
  renderer is the port surface prepared for 5.1, and the raise is what
  stops 5.1 from wiring it up and silently shipping a Twin with nothing
  in it. If one ever *does* fire in 5.0, the whitelist leaked — start
  there, not in the renderer.

The fallback reply is a redirection, never an error message. "Không hỗ
trợ" is technically true and entirely wrong for this persona — the copy
test asserts against that wording specifically.

---

## Rollback

`ZALO_CHANNEL_ENABLED=false` + restart. That is the whole procedure, and
it is byte-identical to pre-5.0 behaviour:

- the webhook route is not mounted, so Zalo's deliveries get a 404 and
  Zalo retries into the void — no partial processing, no half-written rows;
- `notifier_resolver` stops returning a Zalo target, so every send goes
  back to Telegram alone;
- no migration is reverted. `zalo_updates`, `zalo_message_window` and
  `zalo_oa_credentials` are additive tables; leaving them populated costs
  nothing and keeps the evidence if the flag went off during an incident.

Two deliberate exceptions to "off means gone":

1. **The admin quota routes stay mounted.** They send nothing and touch
   no user surface. Unmounting the instrument at the exact moment an
   incident starts would remove the only view of what happened.
2. **The startup invariant still fires.** `ZALO_CHANNEL_ENABLED=true` with
   an empty `ZALO_OA_SECRET_KEY` refuses to boot — flipping the flag back
   on with a half-populated env fails loudly rather than serving an
   unauthenticated webhook.

Turning it back on is the same flag plus the [signature soak](#signature-soak-rollout)
if the credentials changed while it was off.

---

## Rollout checklist

- [ ] Every `ASSUMED` row above promoted to `DOC`/`STAGING`.
- [ ] OA verified in the Zalo console (needed for Mini App in 5.2; not a
      5.0 blocker).
- [ ] `scripts/seed_zalo_credentials.py` run against prod; row present in
      `zalo_oa_credentials` with a non-null `refresh_token`.
- [ ] `ZALO_CHANNEL_ENABLED=true`, `ZALO_SIGNATURE_ENFORCE=false` — soak.
- [ ] 24h of `zalo.signature valid=true` ⇒ `ZALO_SIGNATURE_ENFORCE=true`.
- [ ] Smoke: link an account, capture an expense, request a short report,
      all from Zalo.
- [ ] Confirm webhook p95 latency ≤100ms in the access log.
- [ ] `INTERNAL_API_KEY` set in prod, and
      `GET /api/v1/admin/zalo-quota/baseline` returns a non-null `remain`
      (this is also what promotes the quota-endpoint `ASSUMED` row above).
- [ ] Capture a baseline at cutover, then reconcile after 24h:
      `reconciliation.status == "ok"` and `drift ≤ 1`. See
      [Runbook: quota drift](#runbook-quota-drift-internal-count-vs-zalos-count).
