# Issue #861

[Bug] Twin dashboard status pill shows "Story 3.2" placeholder instead of causality explanation

## Bug

On the Twin dashboard Mini App (`twin_dashboard`), tapping the status/delta pill (e.g. when it reads "Ổn định") pops up a leftover developer placeholder:

> Bé Tiền sẽ giải thích nguyên nhân thay đổi ở Story 3.2.

The causality engine itself (`causality_service.attribute_delta`, Story 3.2 / #680) shipped and is already wired into the Telegram bot (`twin:causality` callback), push notifications, and the narrative flow — but the **Mini App delta pill** was never connected to it. Story 1.3 (#676) specified "Tap vào delta → trigger causality breakdown (Story 3.2)" for the viewer, and the web dashboard port still has the stub.

## Expected

Tapping the status pill explains *why* the Twin changed (or stayed stable), using the existing causality breakdown — never a "Story 3.2" placeholder.

## Fix

- Add a lazy, read-only `GET /api/twin/causality` endpoint returning the existing breakdown (`text`, `direction`, `show_breakdown`). Keeps the main `GET /api/twin` payload lean; only computes for users who actually tap.
- Replace `showCausalityPlaceholder` in `twin_dashboard.js` with a real fetch + `tg.showAlert` display, with an in-flight guard (no double-tap spam), a friendly fallback on failure, a client-side cache, and `screen_viewed`/`causality` funnel analytics.

## Acceptance Criteria

- [ ] Tapping the status pill shows the real causality explanation
- [ ] No "Story 3.2" placeholder remains
- [ ] Endpoint is auth-guarded (401 on invalid init data) and degrades gracefully on service failure
- [ ] Unit tests cover success, auth, and failure paths

