-- Weekly analytics — SQL fallback for when the CLI can't run.
-- Run each block in psql; adjust the INTERVAL to change the window.

-- 1. Event counts by type (last 7 days)
SELECT event_type, COUNT(*) AS count
FROM events
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY event_type
ORDER BY count DESC;

-- 2. Top buttons tapped (last 7 days)
SELECT
    properties ->> 'button' AS button,
    COUNT(*) AS count
FROM events
WHERE event_type = 'button_tapped'
  AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY 1
ORDER BY count DESC
LIMIT 10;

-- 3. Mini App load-time percentiles (last 7 days)
SELECT
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY (properties ->> 'load_time_ms')::float) AS p50_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY (properties ->> 'load_time_ms')::float) AS p95_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY (properties ->> 'load_time_ms')::float) AS p99_ms,
    COUNT(*) AS samples
FROM events
WHERE event_type = 'miniapp_loaded'
  AND (properties ->> 'load_time_ms') IS NOT NULL
  AND timestamp >= NOW() - INTERVAL '7 days';

-- 4. Daily active users (distinct user_id per day)
SELECT
    DATE_TRUNC('day', timestamp) AS day,
    COUNT(DISTINCT user_id) AS active_users
FROM events
WHERE timestamp >= NOW() - INTERVAL '30 days'
  AND user_id IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC;

-- 5. Transaction creation breakdown by source
SELECT
    properties ->> 'source' AS source,
    COUNT(*) AS count
FROM events
WHERE event_type = 'transaction_created'
  AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY 1
ORDER BY count DESC;

-- 6. Category-change churn (how often users re-classify)
SELECT
    properties ->> 'from' AS old_cat,
    properties ->> 'to' AS new_cat,
    COUNT(*) AS count
FROM events
WHERE event_type = 'category_changed'
  AND timestamp >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2
ORDER BY count DESC
LIMIT 20;
