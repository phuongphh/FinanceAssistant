# Issue #623

perf: repeated user lookups cause slow menu navigation callbacks

## Observation
Clicking "Quay về menu" (menu:main) takes ~1.45s, noticeably slower than before.

## Log analysis (19:52:31)
```
19:52:31,219 → webhook (menu:main)
19:52:31,224 → HTTP 200 OK
19:52:31,229 → user lookup #1 (cached, 30+ cols)
19:52:31,236 → user lookup #2 (cached, 30+ cols)
19:52:31,238 → user lookup #3 (cached, 30+ cols)
19:52:32,646 → user lookup #4 (cached, 30+ cols)
19:52:32,660 → DONE
```

## Root cause
- Phase #621 added columns (`tenant_id`, `manual_status`) making user queries heavier
- `telegram_worker.py` does **3-4 SELECT users queries** per callback — caching hides repeat hits but the first is slow
- Time: webhook→done = ~1.45s, mostly spent on redundant user lookups

## File
`backend/workers/telegram_worker.py`
