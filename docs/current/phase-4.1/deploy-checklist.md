# Phase 4.1 — Deploy Checklist (Soft Launch)

> **Task:** P4.1-D1 (Issue #514) — also reused as the master operator
> pre-launch checklist (D.1, D.2, D.3 + final dogfood).
> **Audience:** Operator + on-call dev.
> **When:** Two passes — T-3 (three days before launch) and T-0
> (morning of launch). Every item is a checkbox **and** a "who".

If you cannot answer "who has eyes on this right now?" the item isn't
done. Don't tick boxes by inference — verify and link the artifact.

---

## §1 Channel discipline — Zalo MUST stay disabled (D.1)

The whole reason Phase 4.1 is Telegram-only is to learn one channel
cleanly. A leaked-on Zalo bot in soft launch poisons every cost and
retention metric.

### T-3 verification

- [ ] **Code-side gate present.** Confirm `backend/main.py` includes
      the `if settings.zalo_channel_enabled:` gate around
      `app.include_router(zalo_router.router, ...)`.
      → `grep -n "zalo_channel_enabled" backend/main.py`
- [ ] **Default value is `False`.** Confirm
      `backend/config/__init__.py` has `zalo_channel_enabled: bool = False`.
      → `grep -n "zalo_channel_enabled" backend/config/__init__.py`
- [ ] **`.env.example` documents the flag** with the soft-launch note
      so a new operator doesn't accidentally flip it.
- [ ] **Grep the codebase for accidental imports** — anything that
      bypasses the gate (direct `from backend.routers.zalo import …`
      outside `main.py` is suspicious).
      → `grep -rn "from backend.routers.zalo\b\|backend\.routers\.zalo" backend/ --exclude-dir=__pycache__`

### T-0 verification

- [ ] **Production .env: `ZALO_CHANNEL_ENABLED=false`.** Print the file
      and grep the value with a second operator watching.
      → `grep ^ZALO_CHANNEL_ENABLED .env`
- [ ] **Webhook returns 404.** Hit the production URL and verify the
      response. (We expect Zalo's webhook to NOT be mounted.)
      → `curl -sI https://<prod>/api/v1/zalo/webhook | head -1`
      Expected: `HTTP/2 404` (or `405 Method Not Allowed`, both
      acceptable — both mean the route is not handling Zalo).
- [ ] **Startup log line confirms.** Look for
      `"Zalo channel disabled (ZALO_CHANNEL_ENABLED=false) — webhook not mounted"`
      in the boot log.
- [ ] **Zalo OA console disabled.** Verify in the Zalo OA admin that
      the webhook URL is either unset OR pointing to a non-prod test
      endpoint. (Belt + braces — the code gate is the primary
      guarantee, this is the secondary.)

---

## §2 Database migrations applied

- [ ] `alembic upgrade head` ran cleanly on staging.
- [ ] `alembic upgrade head` ran cleanly on production.
- [ ] **Verify the four Phase 4.1 migrations are present**:
      ```
      r7l8m9n0p1q2_phase41_user_cost_budgets
      s8m9n0p1q2r3_phase41_feedback_sla
      t9n0p1q2r3s4_phase41_twin_calibration
      u0p1q2r3s4t5_phase41_founding_member
      ```
      → `alembic current` should print `u0p1q2r3s4t5 (head)`.
- [ ] Spot-check key tables exist:
      `\d invite_codes`, `\d onboarding_sessions`, `\d user_cost_budgets`,
      `\d twin_calibration_snapshots`.

---

## §3 Environment variables

| Var | Value (prod) | Verified |
|---|---|:---:|
| `ENVIRONMENT` | `production` | [ ] |
| `DATABASE_URL` | (asyncpg URL) | [ ] |
| `INTERNAL_API_KEY` | 32 hex bytes | [ ] |
| `TELEGRAM_BOT_TOKEN` | from BotFather | [ ] |
| `TELEGRAM_WEBHOOK_SECRET` | 32 hex bytes | [ ] |
| `TELEGRAM_BOT_USERNAME` | `BeTienBot` (or actual) | [ ] |
| `OPERATOR_TELEGRAM_ID` | numeric id of founder | [ ] |
| `DEEPSEEK_API_KEY` | populated | [ ] |
| `ANTHROPIC_API_KEY` | populated (OCR) | [ ] |
| `OPENAI_API_KEY` | populated (Whisper) | [ ] |
| `SENTRY_DSN` | populated | [ ] |
| `ZALO_CHANNEL_ENABLED` | **`false`** | [ ] |
| `ONBOARDING_V2_ENABLED` | `true` (default) | [ ] |

Anything blank that the code expects → boot fails fast, fix before
launch.

---

## §4 Observability (Story A.5)

- [ ] Sentry: send a test exception in production, verify it appears
      in the project with the user_id hash + intent_type context.
- [ ] Sentry: verify the `beforeSend` PII-scrub hook is active — try
      an exception with a fake `0987654321` phone and `Decimal("12345678")`
      in the breadcrumb; both must be redacted in Sentry UI.
- [ ] Operator receives the morning KPI digest at 08:00 ICT on the
      staging cron run for 3 consecutive days.

---

## §5 Founding-member scaffolding

- [ ] `scripts/soft_launch_acquisition.py --dry-run --count 5` runs
      cleanly and prints a 5-row preview.
- [ ] `scripts/soft_launch_acquisition.py --batch soft-launch-test --count 5`
      inserts 5 rows; verify via
      `SELECT token, source, grants_founding_status FROM invite_codes WHERE batch_name = 'soft-launch-test';`.
- [ ] Test redemption: hit `/start invite_<token>` with a clean
      Telegram account → user sees the founding banner with
      `sequence = 1`, the invite_codes row gets `redeemed_by_user_id`
      and `redeemed_at` set.
- [ ] Race test: redeem 5 invites in parallel (5 telegram accounts,
      5 different tokens) → all 5 get distinct sequences 1..5, no
      duplicates. Drop the test rows after via SQL.
- [ ] `/whoami` returns the founding sequence and segment.
- [ ] `/founding_status` returns the sorted list (operator only;
      non-operator gets the "chỉ dành cho operator" message).
- [ ] `/cohort_stats` returns the source breakdown.
- [ ] Drop the test rows: `DELETE FROM invite_codes WHERE batch_name = 'soft-launch-test';`
      and reset the test user's founding flags via SQL before launch.

---

## §6 Final 50-invite generation (D.3)

- [ ] Run for real: `python scripts/soft_launch_acquisition.py --batch soft-launch-2026-06`.
- [ ] Verify exactly 50 rows: `SELECT COUNT(*), source FROM invite_codes WHERE batch_name = 'soft-launch-2026-06' GROUP BY source;`
      → 10 per source × 5 sources.
- [ ] All 50 have `grants_founding_status = TRUE`.
- [ ] CSV `invite_links_soft-launch-2026-06.csv` exists at the path the
      operator expects. Move to a private folder (not in git).
- [ ] Operator reviews the CSV — sanity-check at least 3 random rows
      by clicking the URL in an incognito browser; the link should open
      Telegram with the bot + `/start invite_<token>` payload.

---

## §7 Operator dogfood (D.2)

- [ ] Operator self-onboards from `invite_<token>` with `source=friends`.
      End-to-end: `/start` → goal question → first asset → narrative →
      cone chart → 😍 button → completion.
- [ ] Same with `source=vn_finance_community` (verify the more
      professional tone copy appears).
- [ ] Same with `source=direct_msg` (verify the personal tone).
- [ ] Operator verifies the **first-morning briefing** the next day
      includes the A.8 explainer + "💡 Bé Tiền đang nói gì?" button.
- [ ] Operator sends a `/feedback` with text, then verifies
      `/feedback_inbox` shows the row with the founding-member 🌱 flag.
- [ ] Operator replies via `/feedback_reply <id> thanks_logged` — user
      receives the templated message.
- [ ] Operator waits >24h on a different test feedback; the
      `feedback_sla_worker` alert fires once and only once.

---

## §8 Deploy-day rollout

- [ ] Tag the deploy commit: `git tag v4.1.0-soft-launch && git push --tags`.
- [ ] Post the launch announcement (see `phase-4.1-deploy-announcements.md`).
- [ ] Distribute invite links — **NOT all 50 at once**. Plan:
      - Day 1 morning: 15 (friends + personal_fb).
      - Day 1 afternoon: 15 (vn_finance_community).
      - Day 2 morning: 10 (tg_finance_groups).
      - Day 2 afternoon: 10 (direct_msg).
      - Justification: operator can SLA 24h on feedback with this
        cadence; 50 invites at once likely overflows the queue.
- [ ] Subscribe operator phone to Sentry alerts for the launch week.
- [ ] Block 1 hour daily for the next 7 days for feedback triage
      (calendar event, recurring). Soft launch fails if the operator
      doesn't show up; this is the single most important checkbox here.

---

## Rollback plan

If any criterion in [kill-criteria.md](kill-criteria.md) fires within
the first 7 days **before invite distribution completes**:

1. Stop distributing remaining invites (`scripts/soft_launch_acquisition.py`
   already-issued tokens stay valid — that's fine, those users are in).
2. Operator DMs each undistributed-invite holder: "Bé Tiền đang
   chỉnh sửa — sẽ quay lại sau X ngày."
3. Investigate using the action plan from the tripped criterion.

If the kill criterion fires **after** all 50 are distributed:

1. Operator messages the cohort: "Tuần tới Bé Tiền tạm dừng để cải
   thiện X. Tài sản và lịch sử của bạn được giữ nguyên."
2. Feature-flag-off the affected surface (e.g., `FIRST_BRIEFING_FORMAT_ENABLED=false`).
3. Honor the founding promise regardless: those 50 users keep their
   sequence + 50% lifetime discount even if the cohort is paused. See
   [founding-promise.md](../founding-promise.md).

---

*Last updated: Phase 4.1 implementation — 12/05/2026.*
