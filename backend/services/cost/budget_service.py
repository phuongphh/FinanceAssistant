"""Per-user LLM budget service (Phase 4.1, Story A.3).

Operations:
  - ``ensure_budget(user_id)`` — create a free-tier row on first call.
  - ``preflight(user_id)`` — raise :class:`BudgetExceededError` if 100%,
    return a flag if 80% (caller decides whether to warm-warn).
  - ``record_spend(user_id, vnd)`` — add to ``current_month_spend_vnd``;
    also writes one row to ``llm_cost_log``.
  - ``maybe_reset_month(budget)`` — if the calendar month rolled over
    since ``current_month_started_at``, zero the spend.

Transaction discipline: every mutator flushes only. The worker /
router that triggered the LLM call commits.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.cost_budget import (
    DEFAULT_BUDGET_VND,
    LLMCostLog,
    TIER_FREE,
    UserCostBudget,
)

logger = logging.getLogger(__name__)


# Pricing — VND per call/unit. Conservative for v1; refined post-launch.
# DeepSeek is OpenAI-compatible; tokens_in + tokens_out get the same
# rate to keep math simple (the diff is < 5% of the call cost).
USD_VND_RATE = Decimal(os.environ.get("USD_VND_RATE", "25000"))

# DeepSeek-chat: roughly $0.27 per 1M tokens (blended in+out for v1).
# Cache-hit prices not modeled — LLMCache returns cached responses
# without hitting the API (zero upstream cost).
_DEEPSEEK_USD_PER_TOKEN = Decimal("0.27") / Decimal("1_000_000")
# Claude Sonnet OCR — ~$0.03 per page using p50 token counts.
_CLAUDE_PER_PAGE_USD = Decimal("0.03")
# Whisper at $0.006 per minute → per-second.
_WHISPER_PER_SECOND_USD = Decimal("0.006") / Decimal("60")


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of a pre-LLM budget check."""

    allowed: bool
    crossed_warning: bool  # True iff current call would push past 80%
    warning_already_sent_this_month: bool
    spend_vnd: Decimal
    cap_vnd: Decimal


class BudgetExceededError(Exception):
    """Caller hit the monthly cap. Service layer translates to a user-
    facing message via content/cost/budget_messages.yaml.
    """

    def __init__(self, user_id: uuid.UUID, spend_vnd: Decimal, cap_vnd: Decimal):
        super().__init__(
            f"Budget exceeded for user={user_id}: {spend_vnd}/{cap_vnd} VND"
        )
        self.user_id = user_id
        self.spend_vnd = spend_vnd
        self.cap_vnd = cap_vnd


def estimate_call_cost_vnd(
    provider: str,
    *,
    tokens_in: int = 0,
    tokens_out: int = 0,
    page_count: int = 0,
    audio_seconds: float = 0,
) -> Decimal:
    """Best-effort VND cost estimate from raw call params.

    Operations:
      - DeepSeek: (tokens_in + tokens_out) at one rate; OK for budget.
      - Claude OCR: per-page rate × page_count.
      - Whisper: per-second × audio_seconds.

    Returns a non-negative Decimal. Unknown providers return 0 (no
    accidental over-billing).
    """
    p = provider.lower()
    if p == "deepseek":
        total_tokens = Decimal(tokens_in + tokens_out)
        cost_usd = total_tokens * _DEEPSEEK_USD_PER_TOKEN
        return (cost_usd * USD_VND_RATE).quantize(Decimal("0.0001"))
    if p == "claude":
        cost_usd = _CLAUDE_PER_PAGE_USD * Decimal(max(page_count, 1))
        return (cost_usd * USD_VND_RATE).quantize(Decimal("0.0001"))
    if p == "whisper":
        cost_usd = _WHISPER_PER_SECOND_USD * Decimal(str(audio_seconds))
        return (cost_usd * USD_VND_RATE).quantize(Decimal("0.0001"))
    return Decimal("0")


async def ensure_budget(db: AsyncSession, user_id: uuid.UUID) -> UserCostBudget:
    """Get-or-create the budget row. New users land on the free tier."""
    existing = await db.get(UserCostBudget, user_id)
    if existing is not None:
        await maybe_reset_month(existing)
        return existing
    budget = UserCostBudget(
        user_id=user_id,
        tier=TIER_FREE,
        monthly_cap_vnd=DEFAULT_BUDGET_VND[TIER_FREE],
        current_month_spend_vnd=Decimal("0"),
        current_month_started_at=date.today().replace(day=1),
    )
    db.add(budget)
    await db.flush()
    return budget


async def maybe_reset_month(budget: UserCostBudget) -> bool:
    """If we've crossed into a new calendar month, reset spend to 0.

    Mutates the row in place; flush is up to the caller chain.
    Returns True if a reset happened.
    """
    today = date.today()
    started = budget.current_month_started_at
    if (today.year, today.month) != (started.year, started.month):
        budget.current_month_spend_vnd = Decimal("0")
        budget.current_month_started_at = today.replace(day=1)
        budget.last_warning_sent_at = None
        return True
    return False


async def preflight(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    projected_cost_vnd: Decimal | None = None,
) -> PreflightResult:
    """Decide whether the upcoming LLM call is allowed.

    ``projected_cost_vnd`` is an OPTIONAL hint — if the caller knows
    the call's worst-case cost up front (e.g. OCR page count), pass it
    so we don't approve a call that would itself blow the cap. If
    omitted, we only block on the already-recorded spend.

    Raises :class:`BudgetExceededError` if the cap is exhausted; this
    keeps the call sites declarative (try/except) instead of
    branching on every result.
    """
    budget = await ensure_budget(db, user_id)
    projected = projected_cost_vnd or Decimal("0")
    projected_total = budget.current_month_spend_vnd + projected

    if projected_total > budget.monthly_cap_vnd:
        raise BudgetExceededError(
            user_id=user_id,
            spend_vnd=budget.current_month_spend_vnd,
            cap_vnd=budget.monthly_cap_vnd,
        )

    threshold = budget.monthly_cap_vnd * Decimal("0.8")
    crossed = (
        budget.current_month_spend_vnd < threshold and projected_total >= threshold
    )
    already_sent = budget.last_warning_sent_at is not None

    return PreflightResult(
        allowed=True,
        crossed_warning=crossed,
        warning_already_sent_this_month=already_sent,
        spend_vnd=budget.current_month_spend_vnd,
        cap_vnd=budget.monthly_cap_vnd,
    )


async def record_spend(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    provider: str,
    operation: str,
    cost_vnd: Decimal,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int,
    success: bool = True,
    model_version: str | None = None,
) -> None:
    """Add the call's cost to budget + insert a per-call log row.

    Idempotency is the caller's job — calling this twice for the same
    upstream invocation double-bills the user. Adapters call it
    exactly once, in the response branch.
    """
    budget = await ensure_budget(db, user_id)
    budget.current_month_spend_vnd = budget.current_month_spend_vnd + cost_vnd

    log = LLMCostLog(
        user_id=user_id,
        provider=provider,
        operation=operation,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_vnd=cost_vnd,
        latency_ms=latency_ms,
        success=success,
        model_version=model_version,
    )
    db.add(log)
    await db.flush()


async def mark_warning_sent(db: AsyncSession, user_id: uuid.UUID) -> None:
    budget = await db.get(UserCostBudget, user_id)
    if budget is None:
        return
    budget.last_warning_sent_at = datetime.now(timezone.utc)
    await db.flush()


async def override_cap(
    db: AsyncSession, user_id: uuid.UUID, new_cap_vnd: Decimal
) -> bool:
    """Operator escape hatch (/budget_set). Returns True if applied."""
    budget = await ensure_budget(db, user_id)
    budget.monthly_cap_vnd = new_cap_vnd
    await db.flush()
    return True
