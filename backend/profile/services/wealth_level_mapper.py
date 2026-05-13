from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

WEALTH_LEVELS_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "wealth_levels.yaml"
)


@lru_cache(maxsize=1)
def _load_levels() -> list[dict[str, Any]]:
    data = yaml.safe_load(WEALTH_LEVELS_PATH.read_text(encoding="utf-8")) or {}
    levels = data.get("levels") or []
    if not levels:
        raise ValueError("wealth_levels.yaml must define at least one level")
    return levels


def _money(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or 0))


class WealthLevelMapper:
    """VN-native wealth tier mapper for the Phase 3.8.5 profile view."""

    def __init__(self, levels: list[dict[str, Any]] | None = None) -> None:
        self.levels = levels or _load_levels()

    def get_level(
        self, net_worth: Decimal | int | float | str | None
    ) -> dict[str, Any]:
        nw = _money(net_worth)
        for level in self.levels:
            lower = _money(level["net_worth_min"])
            upper = level.get("net_worth_max")
            if nw >= lower and (upper is None or nw < _money(upper)):
                return deepcopy(level)
        return deepcopy(self.levels[0])

    def get_next_level(
        self, net_worth: Decimal | int | float | str | None
    ) -> dict[str, Any] | None:
        current = self.get_level(net_worth)
        for idx, level in enumerate(self.levels):
            if level["id"] == current["id"]:
                if idx + 1 >= len(self.levels):
                    return None
                return deepcopy(self.levels[idx + 1])
        return None

    def get_progress_to_next(
        self, net_worth: Decimal | int | float | str | None
    ) -> dict[str, Any]:
        nw = _money(net_worth)
        current = self.get_level(nw)
        next_level = self.get_next_level(nw)
        if next_level is None:
            return {
                "at_top": True,
                "progress_pct": 100,
                "amount_to_next": Decimal("0"),
                "next_level_name": None,
            }

        lower = _money(current["net_worth_min"])
        upper = _money(next_level["net_worth_min"])
        span = upper - lower
        progress = (
            Decimal("0")
            if span <= 0
            else (nw - lower) / span * Decimal("100")
        )
        progress = max(Decimal("0"), min(Decimal("100"), progress))
        return {
            "at_top": False,
            "progress_pct": int(progress.quantize(Decimal("1"))),
            "amount_to_next": max(Decimal("0"), upper - nw),
            "next_level_name": next_level["name_vn"],
        }
