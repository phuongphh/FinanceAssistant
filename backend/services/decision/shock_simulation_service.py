"""shock_simulation_service — "Nếu phải chi X thì sao?" (Phase 4.5, Epic E1).

Answers a *hypothetical* out loud: the user has to pull a lump sum out of
their portfolio today — how much does that bend the long-run trajectory?

Design — pure core over the Phase 4A/4B Monte Carlo engine:
    ``simulate_shock(snapshot, shock_amount, ...)`` runs the user's real
    portfolio once (``simulate_portfolio``), copies the resulting paths
    **in memory**, injects a single hypothetical one-time outflow via
    ``apply_life_events`` (the exact same machinery Life Events use, so the
    floor-at-zero clamp and per-path accounting stay honest), aggregates
    both cones, and reports the delta at the horizon.

    Nothing is persisted: no ``LifeEvent`` row, no ``TwinProjection`` write,
    no mutation of the stored baseline. The caller (handler) loads the
    snapshot once and hands it in — mirroring ``clarity_service``'s
    pure-core / thin-shell split so scoring is trivially unit-testable
    without a database.

Layer contract: this is a service. It never commits, never sends Telegram,
never reads env. The ``SHOCK_SIMULATION_ENABLED`` flag is decided at the
handler edge (Issue #1.3), never here. Money crosses the boundary as
``Decimal``; ``float`` is used only inside the NumPy engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from backend.twin.engine.cone_aggregator import ConePoint, aggregate_cone
from backend.twin.engine.life_events import LifeEventInjection, apply_life_events
from backend.twin.engine.monte_carlo import simulate_portfolio
from backend.twin.services.twin_projection_service import (
    DEFAULT_HORIZON_YEARS,
    DEFAULT_SIM_PATHS,
    PortfolioSnapshot,
)

# A hypothetical shock is a one-time outflow *today* (year 0). We tag the
# synthetic injection with a stable id so it can never collide with a real
# persisted life event — it is discarded the moment this function returns.
_SHOCK_EVENT_ID = "__hypothetical_shock__"


class ShockSeverity(str, Enum):
    """How hard the shock hits, as a fraction of current net worth.

    Deterministic bucketing lives here (not the formatter) so it is unit
    testable and the formatter only has to map a severity → weather copy.
    """

    LIGHT = "light"  # a passing shower
    MODERATE = "moderate"
    HEAVY = "heavy"
    SEVERE = "severe"  # a real storm


# Thresholds on ``shock_amount / base_net_worth``. Config-driven so product
# can retune the weather metaphor without touching engine logic.
_SEVERITY_BUCKETS: tuple[tuple[Decimal, ShockSeverity], ...] = (
    (Decimal("0.15"), ShockSeverity.LIGHT),
    (Decimal("0.35"), ShockSeverity.MODERATE),
    (Decimal("0.60"), ShockSeverity.HEAVY),
)


@dataclass(frozen=True, slots=True)
class ShockResult:
    """Outcome of a hypothetical shock — baseline vs shocked horizon cone.

    All money is ``Decimal``. Deltas are ``shocked − baseline`` so they read
    as non-positive (a withdrawal can only lower or hold the trajectory).
    """

    shock_amount: Decimal
    horizon_years: int
    base_net_worth: Decimal
    baseline_final: ConePoint
    shocked_final: ConePoint
    delta_p10: Decimal
    delta_p50: Decimal
    delta_p90: Decimal
    severity: ShockSeverity
    recovers: bool  # does the median path still end above today's net worth?

    @property
    def impact_ratio(self) -> Decimal:
        """Shock as a fraction of current net worth (0 when net worth is 0)."""
        if self.base_net_worth <= 0:
            return Decimal("0")
        return self.shock_amount / self.base_net_worth


def classify_severity(shock_amount: Decimal, base_net_worth: Decimal) -> ShockSeverity:
    """Bucket a shock into a weather-metaphor severity. Pure + deterministic."""
    if base_net_worth <= 0:
        return ShockSeverity.SEVERE
    ratio = shock_amount / base_net_worth
    for threshold, severity in _SEVERITY_BUCKETS:
        if ratio < threshold:
            return severity
    return ShockSeverity.SEVERE


def simulate_shock(
    snapshot: PortfolioSnapshot,
    shock_amount: Decimal,
    *,
    horizon: int = DEFAULT_HORIZON_YEARS,
    paths: int = DEFAULT_SIM_PATHS,
    seed: int | None = None,
    base_year: int | None = None,
) -> ShockResult:
    """Project the portfolio, then re-project it minus a one-time shock.

    The two cones share the same RNG draw (a *paired* comparison): the only
    difference between baseline and shocked paths is the injected outflow,
    so the reported delta isolates the shock's effect rather than sampling
    noise.

    Args:
        snapshot: the user's normalized portfolio (from
            ``load_portfolio_snapshot`` — a single DB read owned by the caller).
        shock_amount: hypothetical one-time outflow, ``Decimal`` VND, > 0.
        horizon / paths / seed: simulation controls (defaults match Twin).
        base_year: calendar year of column 0; defaults to the current UTC year.

    Raises:
        ValueError: empty/zero portfolio (nothing to simulate) or a
            non-positive shock amount.
    """
    if shock_amount is None or shock_amount <= 0:
        raise ValueError("shock_amount must be a positive Decimal")
    if not snapshot.allocation_amounts or snapshot.base_net_worth <= 0:
        raise ValueError("cannot simulate a shock on an empty portfolio")

    year0 = base_year if base_year is not None else datetime.now(timezone.utc).year

    baseline = simulate_portfolio(
        snapshot.allocation_amounts,
        snapshot.monthly_savings,
        savings_split=snapshot.allocation_weights or None,
        horizon=horizon,
        paths=paths,
        seed=seed,
    )
    baseline_cone = aggregate_cone(baseline)

    # Copy so the baseline paths stay pristine; inject the hypothetical
    # outflow at year 0 (planned_year == base_year → offset 0), flooring at
    # zero so a shock larger than net worth simply zeroes those paths rather
    # than driving net worth negative (or crashing).
    shocked = baseline.copy()
    injection = LifeEventInjection(
        event_id=_SHOCK_EVENT_ID,
        planned_year=year0,
        one_time_cost=float(shock_amount),
        recurring_monthly_delta=0.0,
        recurring_duration_months=0,
    )
    apply_life_events(shocked, [injection], base_year=year0, floor_at_zero=True)
    shocked_cone = aggregate_cone(shocked)

    baseline_final = baseline_cone[-1]
    shocked_final = shocked_cone[-1]

    return ShockResult(
        shock_amount=shock_amount,
        horizon_years=horizon,
        base_net_worth=snapshot.base_net_worth,
        baseline_final=baseline_final,
        shocked_final=shocked_final,
        delta_p10=shocked_final.p10 - baseline_final.p10,
        delta_p50=shocked_final.p50 - baseline_final.p50,
        delta_p90=shocked_final.p90 - baseline_final.p90,
        severity=classify_severity(shock_amount, snapshot.base_net_worth),
        recovers=shocked_final.p50 >= snapshot.base_net_worth,
    )


__all__ = [
    "ShockResult",
    "ShockSeverity",
    "classify_severity",
    "simulate_shock",
]
