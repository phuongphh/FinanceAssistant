-- Phase 4.3 Epic 4.2 — Twin Loop Health source query.
SELECT
  event_type AS trigger_source,
  COUNT(*) AS triggers,
  COUNT(DISTINCT user_id) AS triggered_users
FROM twin_recompute_log
WHERE created_at >= :start_at
  AND created_at < :end_at
GROUP BY event_type;
