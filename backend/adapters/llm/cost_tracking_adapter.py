"""Cost-tracking wrapper around LLM/OCR/Whisper calls (Phase 4.1, A.3).

Pattern (callsite):

    from backend.adapters.llm.cost_tracking_adapter import tracked_call

    async with tracked_call(
        db, user_id, provider="deepseek", operation="categorize"
    ) as recorder:
        result = await deepseek_client.chat.completions.create(...)
        recorder.tokens_in = result.usage.prompt_tokens
        recorder.tokens_out = result.usage.completion_tokens
        recorder.model_version = result.model

The context manager:

  1. Calls ``preflight()`` BEFORE entering the body — raises
     :class:`BudgetExceededError` if the cap is exhausted.
  2. Times the call.
  3. On exit (success or fail), calls ``record_spend()`` with the
     metadata the body filled in on the recorder object.
  4. Caller is responsible for NOT calling the upstream API if
     :class:`BudgetExceededError` was raised (it bubbles out).

Why a context manager rather than a decorator? Because token usage is
only known after the response lands, and the body needs to populate
``recorder.tokens_in`` etc. — a decorator would force the wrapped
function to take that signature, leaking the cost concern into every
LLM client.

The adapter NEVER calls Telegram directly. The 80%/100% notification
is the service's job (services/cost/budget_service or the calling
handler) — adapters stay transport-only per the layer contract.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.cost import budget_service
from backend.services.cost.budget_service import (
    BudgetExceededError,
    PreflightResult,
    estimate_call_cost_vnd,
)

logger = logging.getLogger(__name__)


@dataclass
class CallRecorder:
    """Mutable container the body fills with usage data."""

    provider: str
    operation: str
    tokens_in: int = 0
    tokens_out: int = 0
    page_count: int = 0
    audio_seconds: float = 0.0
    success: bool = True
    model_version: str | None = None
    # Override-only — for fixed-cost providers where the per-call
    # cost is known without token math (e.g. flat-rate APIs).
    explicit_cost_vnd: Decimal | None = None
    preflight: PreflightResult | None = field(default=None, repr=False)


@asynccontextmanager
async def tracked_call(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    *,
    provider: str,
    operation: str,
    projected_cost_vnd: Decimal | None = None,
) -> AsyncIterator[CallRecorder]:
    """Open a tracked LLM call scope.

    If ``user_id`` is None (background tasks with no user context, e.g.
    market poller LLM calls), the adapter skips the preflight + spend
    recording — those costs land in the global cost dashboard via the
    aggregate ``llm_cost_log`` only when associated with a user.

    Yields a :class:`CallRecorder` the body MUST populate with usage
    metadata before the context exits. On exit, the recorder is used
    to compute final cost + insert one row into ``llm_cost_log`` and
    bump the user's monthly spend.
    """
    recorder = CallRecorder(provider=provider, operation=operation)

    if user_id is not None:
        # Preflight raises BudgetExceededError if blocked. Let it bubble.
        recorder.preflight = await budget_service.preflight(
            db, user_id, projected_cost_vnd=projected_cost_vnd
        )

    start = time.monotonic()
    try:
        yield recorder
    except Exception:
        recorder.success = False
        raise
    finally:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if user_id is None:
            return

        cost = recorder.explicit_cost_vnd
        if cost is None:
            cost = estimate_call_cost_vnd(
                provider,
                tokens_in=recorder.tokens_in,
                tokens_out=recorder.tokens_out,
                page_count=recorder.page_count,
                audio_seconds=recorder.audio_seconds,
            )

        try:
            await budget_service.record_spend(
                db,
                user_id,
                provider=provider,
                operation=operation,
                cost_vnd=cost,
                tokens_in=recorder.tokens_in,
                tokens_out=recorder.tokens_out,
                latency_ms=elapsed_ms,
                success=recorder.success,
                model_version=recorder.model_version,
            )
        except Exception:
            # Don't let bookkeeping failure mask the upstream result.
            logger.exception(
                "cost_tracking_adapter: record_spend failed user=%s op=%s",
                user_id,
                operation,
            )


__all__ = [
    "BudgetExceededError",
    "CallRecorder",
    "tracked_call",
]
