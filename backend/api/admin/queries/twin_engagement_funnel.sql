-- Phase 4.3 Epic 4.1 — Twin Engagement Funnel source query.
-- Runtime implementation lives in backend/api/admin/twin_metrics.py so tenant,
-- cohort, and segment filters can share SQLAlchemy helpers safely.
SELECT
  user_id,
  COUNT(*) AS twin_views,
  MAX(created_at) AS last_view_at
FROM twin_view_events
WHERE event_type IN ('story_opened', 'screen_viewed', 'chart_opened')
  AND created_at >= :start_at
  AND created_at < :end_at
GROUP BY user_id;
