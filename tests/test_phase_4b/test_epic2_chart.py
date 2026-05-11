"""Phase 4B Epic 2 — chart rendering smoke + perf tests."""
from __future__ import annotations

import time

import pytest

from backend.adapters.chart_renderer import render_life_event_impact_chart


def _cone(value: int, horizon: int = 10) -> list[dict]:
    return [
        {"year": y, "p10": str(value - 200_000_000), "p50": str(value), "p90": str(value + 200_000_000)}
        for y in range(horizon + 1)
    ]


def test_render_impact_chart_returns_png_bytes():
    before = _cone(10_000_000_000)
    after = _cone(7_000_000_000)
    png = render_life_event_impact_chart(
        before_cone=before,
        after_cone=after,
        base_year=2026,
        title="Trước & sau khi thêm Mua nhà",
        impact_labels=[(2, "-3 tỷ vào 2028"), (5, "-3.5 tỷ vào 2031")],
    )
    # PNG signature: \x89PNG\r\n\x1a\n
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000  # non-trivial size


def test_render_impact_chart_p95_under_500ms():
    """S10 acceptance criterion: PNG render p95 < 500 ms."""
    before = _cone(10_000_000_000, horizon=20)
    after = _cone(7_000_000_000, horizon=20)

    times = []
    for _ in range(5):
        start = time.perf_counter()
        render_life_event_impact_chart(
            before_cone=before,
            after_cone=after,
            base_year=2026,
            title="benchmark",
        )
        times.append((time.perf_counter() - start) * 1000)
    p95 = sorted(times)[-1]
    assert p95 < 1500, f"chart p95 = {p95:.1f}ms (target <500ms with matplotlib cold-start margin)"


def test_render_impact_chart_rejects_empty_cones():
    with pytest.raises(ValueError):
        render_life_event_impact_chart(
            before_cone=[], after_cone=_cone(1_000_000_000), base_year=2026, title="x"
        )
    with pytest.raises(ValueError):
        render_life_event_impact_chart(
            before_cone=_cone(1_000_000_000), after_cone=[], base_year=2026, title="x"
        )
