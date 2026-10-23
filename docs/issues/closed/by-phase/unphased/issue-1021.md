# Issue #1021

Bug: VNINDEX stock quote live cache is missing while providers fail

Observed cause from dev logs on 2026-08-08 22:37 ICT:

- Telegram callback `menu:market:vnindex` was received and marked `done` with no `telegram_updates.error_message`.
- Backend handled the VNINDEX screen by querying `market_snapshots` for `VNINDEX` and VN30 symbols.
- DB has a latest `VNINDEX` snapshot for `2026-08-08` with price `1768.0600`, created at `2026-08-07 18:00:17 UTC`.
- Redis does not have `market_data:stock:VNINDEX` or `market_data:stock:VNINDEX:last_known`.
- Scheduler/backend error logs show stock quote provider failures around the market data path: VNDIRECT circuit open / provider returned empty data, SSI client errors, and fallback to Stooq producing symbol-not-found for VN symbols.

No code or config changes were made during this inspection.
