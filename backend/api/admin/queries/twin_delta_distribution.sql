-- Phase 4.3 Epic 4.4 — Twin Delta Distribution source query.
SELECT
  delta_pct,
  COUNT(*) AS recomputes,
  AVG(delta_absolute_vnd) AS avg_delta_vnd
FROM twin_recompute_log
WHERE created_at >= :start_at
  AND created_at < :end_at
GROUP BY delta_pct
ORDER BY delta_pct;
