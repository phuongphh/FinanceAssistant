"""clarity_service — Độ Nét Meter v1 (Phase 4.5, Epic E3).

Computes a deterministic 0–100 "clarity" score that answers a single
question: *how sharp is the picture we can paint of this user's finances?*
Every decision answer (shock simulation, feasibility Q&A) surfaces this
score so Bé Tiền can be humble when the data is thin and confident when it
is rich.

Design — pure core + thin I/O shell:
    ``gather_clarity_inputs(db, user_id)`` runs a handful of lightweight,
    indexed queries and packs the raw counts into :class:`ClarityInputs`.
    ``score_clarity(inputs)`` is a **pure, deterministic** function (no LLM,
    no I/O, no clock read beyond ``inputs.now``) that turns those counts
    into a :class:`ClarityResult`. Splitting the two keeps the scoring
    logic trivially unit-testable across profiles without a database and
    guarantees the "<100ms, no LLM" contract.

Layer contract: this is a service — it *flushes only* (in fact it never
writes at all, it is read-only) and never commits, never sends Telegram,
never reads env. The ``CLARITY_METER_ENABLED`` flag is read by the
handler/router edge (see Issue #3.4), never here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.expense import Expense
from backend.models.goal import Goal
from backend.models.income_record import IncomeRecord
from backend.wealth.models.asset import Asset

# ---------------------------------------------------------------------------
# Configuration — all tunables live here so scoring stays declarative.
# ---------------------------------------------------------------------------

# Component weights (must sum to 100). Order matters only for deterministic
# tie-breaking when two components share a weight.
COMPONENT_WEIGHTS: dict[str, int] = {
    "assets": 30,
    "asset_freshness": 15,
    "income": 20,
    "expenses": 20,
    "goals": 15,
}

# Below this score the answer surfaces in "humble mode" (Issue #3.3).
# Config-driven so product can retune without touching scoring logic.
CLARITY_MIN_THRESHOLD: int = 30

# Freshness buckets (days since the most recently valued asset).
_FRESHNESS_BUCKETS: tuple[tuple[int, str], ...] = (
    (30, "1.0"),
    (90, "0.6"),
    (180, "0.4"),
)
_FRESHNESS_STALE_FACTOR = Decimal("0.25")

# Income is scored on how many active months of expense history back it up.
# Distinct sources give confidence the picture isn't a one-off.
_INCOME_WINDOW_DAYS = 120

assert sum(COMPONENT_WEIGHTS.values()) == 100, "clarity weights must sum to 100"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClarityInputs:
    """Raw completeness signals gathered from the DB (or fabricated in tests)."""

    active_asset_count: int
    distinct_asset_types: int
    latest_asset_valued_at: datetime | None
    income_source_count: int
    expense_month_count: int
    active_goal_count: int
    now: datetime


@dataclass(frozen=True, slots=True)
class ClarityComponent:
    """One scored dimension of the clarity picture."""

    key: str
    weight: int
    earned: Decimal  # 0 .. weight

    @property
    def is_complete(self) -> bool:
        return self.earned >= self.weight

    @property
    def is_missing(self) -> bool:
        return self.earned <= 0


@dataclass(frozen=True, slots=True)
class ClarityResult:
    """Outcome of scoring — a 0–100 score plus the component breakdown."""

    score: int  # 0..100
    components: tuple[ClarityComponent, ...]

    @property
    def is_below_threshold(self) -> bool:
        return self.score < CLARITY_MIN_THRESHOLD

    def top_missing(self) -> ClarityComponent | None:
        """Highest-weight component the user has *no* data for.

        Drives humble mode's "cần nhập gì" prompt (Issue #3.3).
        """
        missing = [c for c in self.components if c.is_missing]
        if not missing:
            return None
        return max(missing, key=lambda c: (c.weight, -_order_index(c.key)))

    def top_sharpen(self) -> ClarityComponent | None:
        """Highest-weight component not yet complete — the single best
        suggestion for making the picture sharper (Issue #3.3)."""
        incomplete = [c for c in self.components if not c.is_complete]
        if not incomplete:
            return None
        return max(incomplete, key=lambda c: (c.weight, -_order_index(c.key)))


def _order_index(key: str) -> int:
    """Stable position of a component key for deterministic tie-breaking."""
    return list(COMPONENT_WEIGHTS).index(key)


# ---------------------------------------------------------------------------
# Pure scoring core — deterministic, no I/O, no LLM.
# ---------------------------------------------------------------------------


def _factor_assets(inputs: ClarityInputs) -> Decimal:
    if inputs.active_asset_count <= 0:
        return Decimal("0")
    # Base credit for having *any* asset, plus a diversity bonus that
    # saturates at three distinct asset types.
    diversity = min(inputs.distinct_asset_types, 3)
    return Decimal("0.5") + Decimal("0.5") * (Decimal(diversity) / Decimal(3))


def _factor_asset_freshness(inputs: ClarityInputs) -> Decimal:
    latest = inputs.latest_asset_valued_at
    if latest is None:
        return Decimal("0")
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    now = inputs.now if inputs.now.tzinfo else inputs.now.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - latest).days)
    for max_days, factor in _FRESHNESS_BUCKETS:
        if age_days <= max_days:
            return Decimal(factor)
    return _FRESHNESS_STALE_FACTOR


def _factor_income(inputs: ClarityInputs) -> Decimal:
    if inputs.income_source_count <= 0:
        return Decimal("0")
    if inputs.income_source_count == 1:
        return Decimal("0.7")
    return Decimal("1.0")


def _factor_expenses(inputs: ClarityInputs) -> Decimal:
    months = inputs.expense_month_count
    if months <= 0:
        return Decimal("0")
    if months == 1:
        return Decimal("0.5")
    if months == 2:
        return Decimal("0.75")
    return Decimal("1.0")


def _factor_goals(inputs: ClarityInputs) -> Decimal:
    if inputs.active_goal_count <= 0:
        return Decimal("0")
    if inputs.active_goal_count == 1:
        return Decimal("0.7")
    return Decimal("1.0")


_FACTORS = {
    "assets": _factor_assets,
    "asset_freshness": _factor_asset_freshness,
    "income": _factor_income,
    "expenses": _factor_expenses,
    "goals": _factor_goals,
}


def score_clarity(inputs: ClarityInputs) -> ClarityResult:
    """Turn raw completeness signals into a 0–100 clarity score.

    Pure and deterministic: the same :class:`ClarityInputs` always yields
    the same :class:`ClarityResult`. Each component's factor is monotonic
    in "more data", so adding any signal can only raise the score — the
    property the Epic requires ("nhập thêm data → độ nét tăng ngay").
    """
    components: list[ClarityComponent] = []
    for key, weight in COMPONENT_WEIGHTS.items():
        factor = _FACTORS[key](inputs)
        earned = (Decimal(weight) * factor).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        components.append(ClarityComponent(key=key, weight=weight, earned=earned))

    total = sum((c.earned for c in components), Decimal("0"))
    score = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    score = max(0, min(100, score))
    return ClarityResult(score=score, components=tuple(components))


# ---------------------------------------------------------------------------
# I/O shell — gather inputs then delegate to the pure core.
# ---------------------------------------------------------------------------


async def gather_clarity_inputs(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None
) -> ClarityInputs:
    """Read the four completeness signals with lightweight indexed queries.

    Read-only: no writes, no flush, no commit.
    """
    now = now or datetime.now(timezone.utc)

    # Assets — count, distinct types, freshest valuation. Excludes sold,
    # placeholder and unconfirmed rows (mirrors ``get_user_assets`` defaults)
    # so demo data never inflates clarity.
    asset_row = (
        await db.execute(
            select(
                func.count(Asset.id),
                func.count(func.distinct(Asset.asset_type)),
                func.max(Asset.last_valued_at),
            ).where(
                Asset.user_id == user_id,
                Asset.is_active.is_(True),
                Asset.is_placeholder_asset.is_(False),
                Asset.is_confirmed.is_(True),
            )
        )
    ).one()
    active_asset_count = int(asset_row[0] or 0)
    distinct_asset_types = int(asset_row[1] or 0)
    latest_asset_valued_at = asset_row[2]

    # Income — distinct sources with a record inside the trailing window.
    income_cutoff = (now - timedelta(days=_INCOME_WINDOW_DAYS)).date()
    income_source_count = int(
        (
            await db.execute(
                select(func.count(func.distinct(IncomeRecord.source))).where(
                    IncomeRecord.user_id == user_id,
                    IncomeRecord.deleted_at.is_(None),
                    IncomeRecord.period >= income_cutoff,
                )
            )
        ).scalar()
        or 0
    )

    # Expenses — distinct calendar months with at least one transaction.
    expense_month_count = int(
        (
            await db.execute(
                select(func.count(func.distinct(Expense.month_key))).where(
                    Expense.user_id == user_id,
                    Expense.deleted_at.is_(None),
                )
            )
        ).scalar()
        or 0
    )

    # Goals — active, non-deleted targets.
    active_goal_count = int(
        (
            await db.execute(
                select(func.count(Goal.id)).where(
                    Goal.user_id == user_id,
                    Goal.status == "active",
                    Goal.deleted_at.is_(None),
                )
            )
        ).scalar()
        or 0
    )

    return ClarityInputs(
        active_asset_count=active_asset_count,
        distinct_asset_types=distinct_asset_types,
        latest_asset_valued_at=latest_asset_valued_at,
        income_source_count=income_source_count,
        expense_month_count=expense_month_count,
        active_goal_count=active_goal_count,
        now=now,
    )


async def compute_clarity(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None
) -> ClarityResult:
    """Compute the clarity score for ``user_id``.

    Thin orchestration over :func:`gather_clarity_inputs` +
    :func:`score_clarity`. Deterministic, read-only, no LLM.
    """
    inputs = await gather_clarity_inputs(db, user_id, now=now)
    return score_clarity(inputs)


def to_payload(result: ClarityResult) -> dict:
    """Serialize a :class:`ClarityResult` into the stable JSON shape used by
    the Twin Mini App / API payload (Issue #3.2).

    Money is not involved here, but ``earned`` is emitted as a float so the
    front-end can render partial component bars without parsing Decimals.
    """
    top_missing = result.top_missing()
    top_sharpen = result.top_sharpen()
    return {
        "score": result.score,
        "threshold": CLARITY_MIN_THRESHOLD,
        "below_threshold": result.is_below_threshold,
        "components": [
            {
                "key": c.key,
                "weight": c.weight,
                "earned": float(c.earned),
                "complete": c.is_complete,
            }
            for c in result.components
        ],
        "top_missing": top_missing.key if top_missing else None,
        "top_sharpen": top_sharpen.key if top_sharpen else None,
    }
