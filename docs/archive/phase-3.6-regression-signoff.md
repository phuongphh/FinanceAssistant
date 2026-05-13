# Phase 3.6 Regression Sign-Off — Existing Flows

> **Story:** [P3.6-S10 / #170](../issues/active/issue-170.md)
> **Epic:** [Epic 2 / #159](../issues/active/issue-159.md)
> **Branch:** `claude/implement-phase-3.6-epic-2`
> **Status:** Pending manual verification

## Why this document exists

Phase 3.6 replaces the V1 flat 8-button menu with a 3-level hierarchy
adapted to wealth tier, plus a 4-command Telegram bot menu button. The
contract with users is that **menu UX changes don't break existing
features** — wizards still launch, briefing still fires, NL queries
still resolve. This sign-off captures the evidence that contract is
intact before Epic 3 (migration / hard cutover) ships.

Append-only: if the file gets out of date, add a new section with the
date and a summary of what was re-verified — don't rewrite old entries.

---

## Automated test surface

Run before manual sign-off:

```bash
python -m pytest backend/tests/ --no-header -q
```

| Suite | Tests | Status |
|---|---|---|
| `test_menu_v2` (Epic 1 + 2) | 43 | ☐ |
| `test_telegram_worker` | 10 | ☐ |
| `test_telegram_service` | TBD | ☐ |
| `test_asset_entry_handler` (regression) | 30 | ☐ |
| `test_briefing_callback` (regression) | 9 | ☐ |
| `test_storytelling_handler` (regression) | 26 | ☐ |
| `test_intent` (regression) | TBD | ☐ |
| **Full backend suite** | ~1100 | ☐ |

Pre-existing failures unrelated to Phase 3.6 (carry over from the base
commit) should not block sign-off — note them but don't block on them.

---

## Manual regression checklist (2 personas × 8 flows)

Test each flow with **two personas**: one Starter (low net worth,
encouraging tone) and one Mass Affluent (mid-tier, professional tone).
This proves the wealth-level adapter doesn't break the underlying flow.

Set `users.wealth_level` directly in the DB or use seed scripts to
cover both bands. Estimate: ~3 hours for both personas.

### Asset wizards (Phase 3A)
- ☐ `/themtaisan` → cash flow → 2-question entry → asset persisted (Minh)
- ☐ `/themtaisan` → stock flow → 4-question entry → asset persisted (Phương)
- ☐ `/themtaisan` → real-estate flow → 4-question entry (Minh)
- ☐ `/themtaisan` → crypto flow (Phương)
- ☐ `/themtaisan` → gold flow (Minh)

### OCR (Phase 3A)
- ☐ Send a receipt photo → Claude Vision extracts → confirmation card
  shown → tap ✅ → expense saved (both personas)

### Storytelling (Phase 3A Epic 3)
- ☐ Tap ``💬 Kể chuyện`` from morning briefing → free-form text →
  multi-transaction extract → confirmation → save
- ☐ Voice variant: same flow but with a voice message

### Morning briefing (Phase 3A)
- ☐ 7 AM cron fires (or trigger manually via `/scheduler` admin) →
  briefing message lands → wealth-level-appropriate copy

### Onboarding (Phase 2)
- ☐ Brand-new user `/start` → name capture → wealth-tier flavour text →
  first-asset prompt → onboarding completes

### Free-form intent (Phase 3.5 — 11 canonical queries)
- ☐ "tài sản của tôi"
- ☐ "tổng tài sản tôi bao nhiêu"
- ☐ "portfolio chứng khoán"
- ☐ "chi tiêu tháng này"
- ☐ "thu nhập của tôi"
- ☐ "tỷ lệ tiết kiệm"
- ☐ "VNM giá bao nhiêu"
- ☐ "BTC hôm nay thế nào"
- ☐ "mục tiêu của tôi"
- ☐ "nên đầu tư gì"
- ☐ "tư vấn rebalance portfolio"

### Voice query (Phase 3.5)
- ☐ Send a voice message with a query → Whisper transcribe → intent
  resolves → answer lands

### Mini App dashboard (Phase 3A)
- ☐ Tap "Mở Dashboard" from morning briefing → Mini App opens in chat
- ☐ `/dashboard` command → Mini App opens (Phase 3.6 Epic 2 addition)

---

## Phase 3.6 — new behaviour to verify

These are the new code paths Phase 3.6 introduces. The automated tests
cover the unit boundary; this list is the behavioural smoke test on
real Telegram.

### Menu navigation (Epic 1)
- ☐ `/menu` → main menu with 5 categories
- ☐ Tap each category → sub-menu (4-5 actions + back button)
- ☐ Tap "◀️ Quay về" → main menu (same bubble, edit-in-place)
- ☐ Send 3 navigations in a row → only 1 menu bubble in chat history

### Wealth-adaptive intros (Epic 2 / S7)
- ☐ Starter persona `/menu` → "Trợ lý tài chính" + encouraging copy
- ☐ Mass Affluent persona `/menu` → "Trợ lý CFO cá nhân" + professional copy
- ☐ HNW persona `/menu` → "Personal CFO của anh/chị" + advisor copy
- ☐ Buttons identical across all 4 personas (smoke check 1 sub-menu)

### Bot menu button (Epic 2 / S8)
- ☐ Tap the Telegram bot menu button (corner of input) →
  see exactly 4 commands: /start, /menu, /help, /dashboard
- ☐ Tap each → expected handler fires

### Coexistence (Epic 2 / S9)
- ☐ Open `/menu`, then send a free-form query → query answered in
  new bubble; menu bubble still visible above
- ☐ Start `/themtaisan` wizard, mid-flow send `/menu` → menu opens;
  type the next wizard input → wizard resumes correctly
- ☐ Stale legacy callback (e.g. tap an old `menu:gmail_scan` bubble
  from before deploy) → bot doesn't crash; legacy handler responds

---

## Sign-off

| Item | Verified by | Date | Notes |
|---|---|---|---|
| Automated suite passes | TBD | TBD | |
| Asset wizards (5 flows × 2 personas) | TBD | TBD | |
| OCR + storytelling + voice | TBD | TBD | |
| Free-form intent (11 queries × 2 personas) | TBD | TBD | |
| Phase 3.6 new behaviour (menu + adaptive + commands + coexistence) | TBD | TBD | |
| Mini App dashboard | TBD | TBD | |

When all rows above are filled, Phase 3.6 Epic 2 is **clear to ship**
and Epic 3 (hard cutover migration) can start.

---

## Issues found

> Append rows here as regressions surface during testing. Empty list at
> the time of sign-off means no blockers.

| Issue | Severity | Owner | Resolution |
|---|---|---|---|
| _none yet_ | | | |
