-- Phase 4.3 Epic 4.3 — Twin Comprehension Signals source query.
SELECT
  event_type,
  screen_id,
  COUNT(*) AS events,
  COUNT(DISTINCT user_id) AS users
FROM twin_view_events
WHERE created_at >= :start_at
  AND created_at < :end_at
GROUP BY event_type, screen_id;
