# Issue #987

Phase 4.6 E3 — decision-moment review follow-ups (already-reached copy, savepoint isolation, demo gate, one-number building)

Follow-up to #985 / PR #986 (merged). Four P2 items raised in review on the merged decision-moment change, all confirmed real:

1. **Already-reached goals show a phantom countdown.** When `PlanFeasibility.already_reached` is true, `months` is the horizon fallback (the finished projection has no `months_remaining`), so the `on_track` copy rendered "khoảng 24 tháng nữa" to a user who is already at/above the milestone. Needs a dedicated already-reached copy line with no countdown.

2. **Best-effort DB failure poisons the outer transaction.** A read or the `log_query` flush inside `_send_decision_moment` erroring leaves the `AsyncSession` needing rollback; the `except` only logs, so the worker's boundary `db.commit()` then fails and can silently undo `mark_twin_shown` and the whole reveal. Isolate the DB work in a SAVEPOINT.

3. **Demo Twin runs a real decision moment.** The reveal calls `_send_decision_moment` unconditionally, so demo mode answers a decision on the giả-định 50tr portfolio and logs it as a real feasibility interaction — blurring the demo framing. Gate on `not demo`.

4. **Building answer breaks the one-number promise.** The `building` copy rendered three numbers (reachable + horizon + original target), turning the moment into a mini feasibility report. Keep it to the single reachable amount.

All four are copy/formatter/handler-local; no engine or schema change.
