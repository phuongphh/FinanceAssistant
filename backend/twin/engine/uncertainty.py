"""Uncertainty breakdown for Financial Twin — Phase 4B S5.

Computes which asset classes contribute most to P90−P10 cone width using
marginal-risk-contribution (MRC) decomposition of the portfolio covariance matrix.
This is a pure analytical computation over the stored allocation_snapshot, so it
never re-runs Monte Carlo and is safe in the GET path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.twin.engine.distributions import get_correlation, get_distribution


@dataclass(frozen=True, slots=True)
class UncertaintyContributor:
    """One asset class and its percentage share of portfolio variance."""

    asset_class: str
    contribution_pct: float  # 0–100, rounded to 1 decimal place


def compute_uncertainty_breakdown(
    allocation: dict[str, Any],
    *,
    top_n: int = 2,
) -> list[UncertaintyContributor]:
    """Return top ``top_n`` asset classes by marginal risk contribution (MRC).

    Formula: MRC_i = w_i * (Σw)_i / (w^T Σ w) where Σ is the covariance matrix
    built from each asset's historical σ and pairwise correlations.

    Allocation values may be fractional weights (summing to ~1) or VND amounts —
    only the relative proportions matter.
    """
    if not allocation:
        return []

    asset_classes = list(allocation.keys())
    raw_values = [float(allocation[a]) for a in asset_classes]
    total = sum(raw_values)
    if total <= 0:
        return []

    weights = np.array([v / total for v in raw_values], dtype=np.float64)

    try:
        sigmas = np.array(
            [get_distribution(a).sigma for a in asset_classes], dtype=np.float64
        )
    except ValueError:
        # Unknown asset class — skip gracefully
        return []

    # Covariance matrix: Cov[i,j] = σ_i * σ_j * corr(i, j)
    cov = np.outer(sigmas, sigmas)
    for i, a in enumerate(asset_classes):
        for j, b in enumerate(asset_classes):
            if i != j:
                cov[i, j] *= get_correlation(a, b)

    portfolio_var = float(weights @ cov @ weights)
    if portfolio_var <= 0:
        return []

    mrc = weights * (cov @ weights)
    mrc_pct = mrc / portfolio_var * 100.0

    contributors = [
        UncertaintyContributor(
            asset_class=asset_classes[i],
            contribution_pct=round(float(mrc_pct[i]), 1),
        )
        for i in range(len(asset_classes))
        if mrc_pct[i] > 0
    ]
    contributors.sort(key=lambda c: c.contribution_pct, reverse=True)
    return contributors[:top_n]
