# Phase 4A — Financial Twin Benchmark Results

Benchmarks are local/offline quality gates for Epic 6. They avoid production services and use deterministic fixture portfolios so results are repeatable in CI.

| Gate | Target | Current implementation |
|---|---:|---:|
| Monte Carlo single user, 5 assets, 1,000 paths, 10 years | p95 < 2s | Covered by `tests/test_phase_4a/test_perf_twin.py` |
| Weekly cron, 100 users | < 5 minutes | Covered with mocked DB/users/projection writes |
| Chart PNG render | p95 < 500ms | Covered after renderer warm-up |
| API cached payload/ETag path | p95 < 200ms | Covered without recompute |
| Mini App static bundle gzip size | < 200KB | Covered by gzipping static JS/CSS files |

## How to run

```bash
uv run pytest tests/test_phase_4a/test_perf_twin.py
```

## Design constraints

- GET `/api/twin` reads cached projections only; no Monte Carlo recompute happens in the request path.
- Weekly recompute is bounded by `CONCURRENCY_LIMIT` and isolates per-user failures.
- Chart renderer adds a probabilistic watermark on every cone image.
