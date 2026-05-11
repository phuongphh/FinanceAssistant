"""Pure Monte Carlo simulators for Phase 4A Financial Twin.

The engine keeps Decimal at API boundaries and uses numpy float64 internally for
speed. Outputs include year 0 as the deterministic current value, followed by
one column per projected year, so a 10-year horizon returns 11 columns.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from backend.twin.engine.distributions import ReturnDistribution, get_correlation, get_distribution


Array2D = NDArray[np.float64]


def simulate_single_asset(
    initial: Decimal,
    monthly_contrib: Decimal,
    dist: ReturnDistribution,
    years: int,
    paths: int = 1000,
    seed: int | None = None,
) -> Array2D:
    """Simulate one asset class with annual lognormal returns.

    Returns an array shaped ``(paths, years + 1)``. Column 0 is deterministic
    year 0, which lets downstream cone aggregation prove today's net worth.
    """
    _validate_sim_args(years, paths)
    initial_f = _non_negative_float(initial, "initial")
    contrib_f = _non_negative_float(monthly_contrib, "monthly_contrib") * 12.0

    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((paths, years), dtype=np.float64)
    return _simulate_from_standard_normals(initial_f, contrib_f, dist, shocks)


def simulate_portfolio(
    allocation: Mapping[str, Decimal | int | float],
    monthly_savings: Decimal,
    savings_split: Mapping[str, Decimal | int | float] | None,
    horizon: int,
    paths: int = 1000,
    seed: int | None = None,
    base_net_worth: Decimal | int | float | None = None,
) -> Array2D:
    """Simulate a correlated multi-asset portfolio.

    ``allocation`` can be either current VND amounts or weights. If values sum
    to 1.0, ``base_net_worth`` is required and weights are converted to current
    VND amounts. ``savings_split`` controls how monthly savings are allocated;
    if omitted, current allocation weights are reused.
    """
    _validate_sim_args(horizon, paths)
    if not allocation:
        raise ValueError("allocation must contain at least one asset class")

    asset_classes = list(allocation.keys())
    amounts = _resolve_allocation_amounts(allocation, base_net_worth)
    total_amount = sum(amounts.values())
    if total_amount <= 0:
        raise ValueError("portfolio allocation must be positive")

    split = _resolve_savings_split(savings_split, amounts, total_amount)
    monthly_savings_f = _non_negative_float(monthly_savings, "monthly_savings")

    corr = _build_correlation_matrix(asset_classes)
    rng = np.random.default_rng(seed)
    shocks = rng.multivariate_normal(
        mean=np.zeros(len(asset_classes), dtype=np.float64),
        cov=corr,
        size=(paths, horizon),
        method="svd",
    )

    result = np.zeros((paths, horizon + 1), dtype=np.float64)
    for idx, asset_class in enumerate(asset_classes):
        dist = get_distribution(asset_class)
        asset_paths = _simulate_from_standard_normals(
            initial=amounts[asset_class],
            annual_contrib=monthly_savings_f * 12.0 * split[asset_class],
            dist=dist,
            shocks=shocks[:, :, idx],
        )
        result += asset_paths

    _assert_finite(result)
    return result


def _simulate_from_standard_normals(
    initial: float,
    annual_contrib: float,
    dist: ReturnDistribution,
    shocks: Array2D,
) -> Array2D:
    paths, years = shocks.shape
    result = np.empty((paths, years + 1), dtype=np.float64)
    result[:, 0] = initial

    # Lognormal growth factor with median anchored to 1 + μ so the
    # P50 path stays intuitive for users and acceptance tests.
    drift = np.log1p(dist.mu)
    growth_factors = np.exp(drift + dist.sigma * shocks)
    for year_idx in range(years):
        result[:, year_idx + 1] = result[:, year_idx] * growth_factors[:, year_idx] + annual_contrib

    _assert_finite(result)
    return result


def _resolve_allocation_amounts(
    allocation: Mapping[str, Decimal | int | float],
    base_net_worth: Decimal | int | float | None,
) -> dict[str, float]:
    values = {asset: _non_negative_float(value, f"allocation[{asset}]") for asset, value in allocation.items()}
    total = sum(values.values())
    if abs(total - 1.0) <= 0.001:
        if base_net_worth is None:
            raise ValueError("base_net_worth is required when allocation values are weights")
        base = _non_negative_float(base_net_worth, "base_net_worth")
        if base <= 0:
            raise ValueError("base_net_worth must be positive")
        return {asset: weight * base for asset, weight in values.items()}
    return values


def _resolve_savings_split(
    savings_split: Mapping[str, Decimal | int | float] | None,
    amounts: Mapping[str, float],
    total_amount: float,
) -> dict[str, float]:
    if savings_split is None:
        return {asset: amount / total_amount for asset, amount in amounts.items()}

    split = {asset: _non_negative_float(savings_split.get(asset, 0), f"savings_split[{asset}]") for asset in amounts}
    split_total = sum(split.values())
    if abs(split_total - 1.0) > 0.001:
        raise ValueError("savings_split must sum to 1.0 ± 0.001")
    return split


def _build_correlation_matrix(asset_classes: list[str]) -> NDArray[np.float64]:
    matrix = np.eye(len(asset_classes), dtype=np.float64)
    for i, asset_a in enumerate(asset_classes):
        for j, asset_b in enumerate(asset_classes):
            if i != j:
                matrix[i, j] = get_correlation(asset_a, asset_b)
    # Numerical guard: tiny diagonal jitter helps if future YAML tuning creates
    # a near-singular matrix while preserving configured correlations.
    matrix += np.eye(len(asset_classes), dtype=np.float64) * 1e-12
    return matrix


def _validate_sim_args(years: int, paths: int) -> None:
    if years <= 0:
        raise ValueError("years/horizon must be positive")
    if paths <= 0:
        raise ValueError("paths must be positive")


def _non_negative_float(value: Decimal | int | float, name: str) -> float:
    converted = float(value)
    if converted < 0:
        raise ValueError(f"{name} must be non-negative")
    return converted


def _assert_finite(result: Array2D) -> None:
    if not np.isfinite(result).all():
        raise ValueError("simulation produced NaN or Inf")
