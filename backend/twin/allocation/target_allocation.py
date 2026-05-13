"""Target allocations for Phase 4A Optimal Trajectory.

Targets are externalized in ``content/allocation_targets.yaml`` so PM/legal can
adjust risk posture without code changes. They are conservative rule-of-thumb
allocation bands by wealth tier, not personalized investment advice. The
localized disclaimer also lives in content and must be surfaced by callers.

The simulator ignores tax and transaction costs in Phase 4A MVP.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from backend.wealth.ladder import WealthLevel

_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "allocation_targets.yaml"
)
_ALLOWED_LEVELS = {level.value for level in WealthLevel}
_TOLERANCE = 0.001


@dataclass(frozen=True, slots=True)
class AllocationTarget:
    wealth_level: str
    name_vn: str
    targets: dict[str, float]
    disclaimer: str
    source_note: str


@dataclass(frozen=True, slots=True)
class RebalanceDelta:
    asset_class: str
    current_weight: Decimal
    target_weight: Decimal
    delta_weight: Decimal
    amount_delta: Decimal


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    _validate_config(config)
    return config


def get_target_allocation(wealth_level: WealthLevel | str) -> dict[str, float]:
    """Return target allocation weights for a wealth level.

    The returned weights sum to 1.0 ± 0.001 and are safe to pass directly to
    the Monte Carlo savings split.
    """
    target = get_target_metadata(wealth_level)
    return dict(target.targets)


def get_target_metadata(wealth_level: WealthLevel | str) -> AllocationTarget:
    level_key = _normalize_level(wealth_level)
    config = _load_config()
    raw = config["levels"][level_key]
    targets = {asset: float(weight) for asset, weight in raw["targets"].items()}
    return AllocationTarget(
        wealth_level=level_key,
        name_vn=str(raw["name_vn"]),
        targets=targets,
        disclaimer=str(config["disclaimer"]),
        source_note=str(config.get("source_note", "")),
    )


def get_allocation_disclaimer() -> str:
    return str(_load_config()["disclaimer"])


def top_rebalance_deltas(
    current_weights: Mapping[str, Decimal | int | float | str],
    target_weights: Mapping[str, Decimal | int | float | str],
    *,
    base_net_worth: Decimal | int | float | str,
    limit: int = 2,
    min_abs_delta: Decimal = Decimal("0.03"),
) -> list[RebalanceDelta]:
    """Return largest target-current gaps for actionable copy.

    Positive ``delta_weight`` means add toward the asset class; negative means
    trim. Deltas under 3 percentage points are skipped to avoid noisy advice.
    """
    base = Decimal(str(base_net_worth or 0))
    assets = set(current_weights) | set(target_weights)
    deltas: list[RebalanceDelta] = []
    for asset in assets:
        current = Decimal(str(current_weights.get(asset, 0)))
        target = Decimal(str(target_weights.get(asset, 0)))
        delta = target - current
        if abs(delta) < min_abs_delta:
            continue
        deltas.append(
            RebalanceDelta(
                asset_class=asset,
                current_weight=current,
                target_weight=target,
                delta_weight=delta,
                amount_delta=(base * delta).quantize(Decimal("1")),
            )
        )
    return sorted(deltas, key=lambda item: (-abs(item.delta_weight), item.asset_class))[
        :limit
    ]


def _normalize_level(wealth_level: WealthLevel | str) -> str:
    raw = (
        wealth_level.value
        if isinstance(wealth_level, WealthLevel)
        else str(wealth_level)
    )
    normalized = raw.strip()
    if normalized in _ALLOWED_LEVELS:
        return normalized

    levels = _load_config()["levels"]
    for level_key, level_config in levels.items():
        if normalized.casefold() == str(level_config.get("name_vn", "")).casefold():
            return level_key

    raise ValueError(
        f"Unsupported wealth level for Twin target allocation: {wealth_level}"
    )


def _validate_config(config: dict[str, Any]) -> None:
    levels = config.get("levels") or {}
    missing = _ALLOWED_LEVELS - set(levels)
    if missing:
        raise ValueError(
            f"Missing allocation targets for wealth levels: {sorted(missing)}"
        )
    if not config.get("disclaimer"):
        raise ValueError("allocation_targets.yaml must include a prominent disclaimer")
    for level_key in _ALLOWED_LEVELS:
        targets = levels[level_key].get("targets") or {}
        total = sum(float(value) for value in targets.values())
        if abs(total - 1.0) > _TOLERANCE:
            raise ValueError(
                f"Allocation targets for {level_key} must sum to 1.0 ± {_TOLERANCE}"
            )
