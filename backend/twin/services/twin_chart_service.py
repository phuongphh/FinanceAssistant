"""Financial Twin chart service."""
from __future__ import annotations

from typing import Any

from backend.adapters.chart_renderer import render_cone_chart


def render_projection_chart(
    cone: list[dict[str, Any]],
    optimal: list[dict[str, Any]] | None = None,
    *,
    width: int = 800,
    height: int = 600,
) -> bytes:
    return render_cone_chart(cone, optimal=optimal, width=width, height=height)
