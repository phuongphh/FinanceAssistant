"""liquidation_advisor — "Rút từ đâu ít hại nhất?" (Phase 4.5, Epic E1, #1.2).

Given a lump sum the user has to raise, rank *their own* asset classes into a
least-harmful withdrawal order and build a concrete draw plan.

`legal-guardrail` — this module NEVER recommends buying or selling an external
product. Every option is a class the user already owns (read straight from
their portfolio snapshot); we only advise on the ordering of *their* money.
There is deliberately no code path that names a fund, ticker, bank product, or
counterparty. Keep it that way.

Ranking rationale (encoded in ``_DRAW_PRIORITY``): draw first from what is most
liquid and least costly to give up, keep the compounding growth engines and the
illiquid, lumpy home for last. Concretely:

    cash / bonds   → most liquid, lowest expected growth → draw first
    gold           → liquid store of value
    stocks (VN/global) → liquid but productive; selling forfeits compounding
    crypto         → liquid yet highest expected upside/volatility → costly to sell
    real estate    → illiquid + indivisible (can't sell "a corner") → last resort

This single ordering folds together the two signals the Epic calls for —
*trajectory impact* (higher-growth assets hurt more to liquidate) and
*liquidity* (illiquid assets are impractical to tap) — so the plan is honest
without pretending to a false precision.

Layer contract: pure service. No DB, no commit, no env, no Telegram. The caller
passes the ``allocation_amounts`` mapping from ``PortfolioSnapshot`` (a single
read it already owns).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Lower number → draw from this class earlier (least harmful first). Classes
# absent here (unexpected/future twin classes) sort last, after real estate,
# so we never silently prioritise an unknown asset.
_DRAW_PRIORITY: dict[str, int] = {
    "cash_savings": 1,
    "bonds_vn": 2,
    "gold": 3,
    "stocks_vn": 4,
    "stocks_global": 5,
    "crypto": 6,
    "real_estate_vn": 7,
}

_UNKNOWN_PRIORITY = 99


@dataclass(frozen=True, slots=True)
class LiquidationOption:
    """One asset class in the draw plan.

    ``take`` is how much the plan pulls from this class; ``remaining_after`` is
    what is left in it once ``take`` is withdrawn. Money is ``Decimal``.
    """

    asset_class: str
    available: Decimal
    take: Decimal
    remaining_after: Decimal
    draw_priority: int


@dataclass(frozen=True, slots=True)
class LiquidationPlan:
    """A ranked, least-harmful way to raise ``shock_amount`` from owned assets.

    ``options`` is ordered by draw priority and only includes classes the plan
    actually touches (``take > 0``). When the portfolio can't cover the amount,
    ``fully_covered`` is ``False`` and ``shortfall`` is the honest gap — we say
    "chưa đủ" rather than inventing liquidity.
    """

    shock_amount: Decimal
    total_liquidatable: Decimal
    options: tuple[LiquidationOption, ...]
    fully_covered: bool
    shortfall: Decimal

    @property
    def has_assets(self) -> bool:
        return self.total_liquidatable > 0


def _priority(asset_class: str) -> int:
    return _DRAW_PRIORITY.get(asset_class, _UNKNOWN_PRIORITY)


def rank_options(
    allocation_amounts: dict[str, Decimal],
    shock_amount: Decimal,
) -> LiquidationPlan:
    """Build a least-harmful withdrawal plan for ``shock_amount``.

    Greedy over the fixed draw priority: take as much as needed from the
    least-harmful class first, spilling to the next only when a class is
    exhausted. Deterministic and pure.

    Args:
        allocation_amounts: current VND value per twin asset class (from the
            portfolio snapshot). Zero/negative balances are ignored.
        shock_amount: the lump sum to raise, ``Decimal`` VND, > 0.

    Raises:
        ValueError: non-positive ``shock_amount``.
    """
    if shock_amount is None or shock_amount <= 0:
        raise ValueError("shock_amount must be a positive Decimal")

    owned = {
        cls: Decimal(amount)
        for cls, amount in allocation_amounts.items()
        if Decimal(amount) > 0
    }
    total = sum(owned.values(), Decimal(0))

    # Draw order: least-harmful first, with the asset class name as a stable
    # tiebreaker so equal-priority classes rank deterministically.
    ordered = sorted(owned.items(), key=lambda kv: (_priority(kv[0]), kv[0]))

    remaining = shock_amount
    options: list[LiquidationOption] = []
    for asset_class, available in ordered:
        if remaining <= 0:
            break
        take = min(available, remaining)
        if take <= 0:
            continue
        options.append(
            LiquidationOption(
                asset_class=asset_class,
                available=available,
                take=take,
                remaining_after=available - take,
                draw_priority=_priority(asset_class),
            )
        )
        remaining -= take

    covered = remaining <= 0
    return LiquidationPlan(
        shock_amount=shock_amount,
        total_liquidatable=total,
        options=tuple(options),
        fully_covered=covered,
        shortfall=Decimal(0) if covered else remaining,
    )


__all__ = [
    "LiquidationOption",
    "LiquidationPlan",
    "rank_options",
]
