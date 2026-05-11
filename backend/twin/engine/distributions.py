"""Return distributions for the Phase 4A Financial Twin engine.

Source notes are intentionally stored with each distribution and externalized in
``content/twin_distributions.yaml`` for future tuning without code changes.
Current Phase 4A assumptions use these historical proxies:
- VN-Index 2015-2025 for ``stocks_vn``.
- S&P 500 long-term benchmark for ``stocks_global``.
- BTC/ETH 2018-2025, capped, for ``crypto``.
- SJC/Vietnam gold 2015-2025 for ``gold``.
- Vietnam bank deposit-rate range for ``cash_savings``.
- Vietnam residential real-estate proxy for ``real_estate_vn``.
- Vietnam government-bond yield proxy for ``bonds_vn``.

Prominent disclaimer: historical ≠ future. These are scenario assumptions for
probability cones, not investment advice and not guaranteed forecasts.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ASSET_CLASSES = (
    "stocks_vn",
    "stocks_global",
    "crypto",
    "gold",
    "cash_savings",
    "real_estate_vn",
    "bonds_vn",
)

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_distributions.yaml"


@dataclass(frozen=True, slots=True)
class ReturnDistribution:
    """Annual return distribution parameters for one asset class."""

    asset_class: str
    mu: float
    sigma: float
    source_note: str


@lru_cache(maxsize=1)
def load_distribution_config() -> dict[str, Any]:
    """Load the externalized distribution/correlation configuration."""
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    _validate_config(config)
    return config


def get_distribution(asset_class: str) -> ReturnDistribution:
    """Return annual μ/σ assumptions for ``asset_class``.

    Raises:
        ValueError: if the asset class is unsupported or has invalid values.
    """
    config = load_distribution_config()
    raw = config["asset_classes"].get(asset_class)
    if raw is None:
        raise ValueError(f"Unsupported Twin asset class: {asset_class}")
    dist = ReturnDistribution(
        asset_class=asset_class,
        mu=float(raw["mu"]),
        sigma=float(raw["sigma"]),
        source_note=str(raw.get("source_note", "")),
    )
    if dist.mu == 0 or dist.sigma <= 0:
        raise ValueError(f"Invalid return distribution for {asset_class}")
    return dist


def get_correlation(asset_a: str, asset_b: str) -> float:
    """Return configured correlation between two asset classes."""
    if asset_a == asset_b:
        return 1.0
    config = load_distribution_config()
    pairs = config.get("correlations", {}).get("pairs", {})
    default = float(config.get("correlations", {}).get("default", 0.0))
    return float(
        pairs.get(asset_a, {}).get(asset_b, pairs.get(asset_b, {}).get(asset_a, default))
    )


def _validate_config(config: dict[str, Any]) -> None:
    classes = config.get("asset_classes", {})
    missing = set(ASSET_CLASSES) - set(classes)
    if missing:
        raise ValueError(f"Missing Twin asset classes in config: {sorted(missing)}")
    for asset_class in ASSET_CLASSES:
        raw = classes[asset_class]
        if float(raw["mu"]) == 0 or float(raw["sigma"]) <= 0:
            raise ValueError(f"Invalid Twin distribution for {asset_class}")
