# Issue #991

4.6/E4 follow-up: tenant-scope the decision-adoption chart + average độ nét per active user

Post-merge review of #990 (E4 / #4.2, decision-adoption admin chart) surfaced two defects worth fixing now. Both are contained corrections that keep the chart's response shape identical.

## 1. Cross-tenant leak (security)

`GET /charts/decision-adoption` filtered `decision_query_logs` with `_tenant_filter(DecisionQueryLog, tenant_id)`. That table has **no `tenant_id` column**, so the helper falls back to `true()` for the default tenant — i.e. a non-default tenant would either see nothing or (for the default tenant) every tenant's rows, with no user-scoped isolation. Every other user-facing admin chart joins `users` and scopes on `users.tenant_id`.

**Fix:** join `User` on `DecisionQueryLog.user_id` and filter `User.deleted_at.is_(None)` + `_tenant_filter(User, tenant_id)`, matching `user_tiers` / `cohort_retention`.

## 2. độ nét averaged per interaction instead of per active user (correctness)

Gate G2 (`strategy.md`) defines độ nét as the **average over active users**, but the chart computed `AVG(clarity_score)` over raw interaction rows — a chatty user skews the cohort mean.

**Fix:** roll up per `(week, cohort, user_id)` in an inner subquery (per-user mean clarity + per-user interaction count), then average those per-user means and `COUNT()` distinct users in the outer per-cohort aggregate. Response columns (`week, cohort, interactions, active_users, avg_clarity`) are unchanged, so the downstream dense-backfill and labeling logic is untouched.

## Out of scope (tracked separately)

Two further review points are larger, dimension-adding changes and are **not** in this issue — they need product scoping first:
- Adoption **denominator** = product-active / first-week users (G1), not just users who already logged a decision.
- **D28-by-cohort** retention series feeding G2.

## Tests
- Rewrote the two tenant-scoping tests for the `users.tenant_id` join reality.
- Added a test asserting độ nét rolls up by `user_id` before the per-cohort average.
- Full suite green; `ruff check` clean on both changed files.
