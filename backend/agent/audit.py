"""Fire-and-forget audit log writer for agent invocations.

Writes happen on a background task so the user-facing latency of a
``Orchestrator.route()`` call is not coupled to the audit DB write.
This mirrors ``backend.analytics.track`` — same pattern, same
trade-off (best-effort persistence; debug-log on failure).

Intentionally NOT importing the Orchestrator here to keep the
dependency graph one-way:

    orchestrator → audit.log_route()
       (never the other direction)

The ``RouteAudit`` dataclass is the parameter object — Orchestrator
fills it in piecewise as the route executes, then hands it to
``log_route`` once. Tests can construct one directly + check the
DB write without touching the orchestrator.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.database import get_session_factory
from backend.models.agent_audit_log import AgentAuditLog

logger = logging.getLogger(__name__)


@dataclass
class RouteAudit:
    """Snapshot of one ``Orchestrator.route()`` call.

    Constructed by the orchestrator and handed to ``log_route``.
    Defaults match "nothing happened yet" so partial fills are
    cheap; the orchestrator overwrites whatever it learned."""

    user_id: uuid.UUID | None
    query_text: str
    tier_used: str
    routing_reason: str | None = None
    tools_called: list[dict[str, Any]] = field(default_factory=list)
    tool_call_count: int = 0
    llm_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    success: bool = False
    response_preview: str | None = None
    error: str | None = None
    total_latency_ms: int | None = None


# Same pattern as ``analytics.track`` — keep tasks alive for GC.
_pending: set[asyncio.Task] = set()


def log_route(audit: RouteAudit) -> None:
    """Schedule a background write of one audit row.

    Returns immediately; the actual INSERT runs on the loop's
    background. Failures are swallowed (logged at debug) — the
    audit log going down should NEVER take user requests with it."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop running — sync best-effort write. Same fallback
        # ``analytics.track`` uses for sync CLI / migration contexts.
        try:
            asyncio.run(_persist(audit))
        except Exception:
            logger.debug("audit log_route sync-write failed", exc_info=True)
        return

    task = loop.create_task(_persist(audit))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def alog_route(audit: RouteAudit) -> None:
    """Async variant — await for ordering guarantees (mostly tests)."""
    await _persist(audit)


async def _persist(audit: RouteAudit) -> None:
    try:
        session_factory = get_session_factory()
    except Exception:
        logger.debug("audit: no session factory available", exc_info=True)
        return

    try:
        async with session_factory() as session:
            session.add(_to_row(audit))
            await session.commit()
    except Exception:
        logger.debug("audit log_route persist failed", exc_info=True)


def _to_row(audit: RouteAudit) -> AgentAuditLog:
    """Map dataclass → ORM row.

    Truncate the user-facing strings defensively — schema enforces
    the same bound, but raising on overflow inside a fire-and-forget
    write would just churn logs. Better to log the truncation later
    than crash."""
    query_text = (audit.query_text or "")[:2000]
    response_preview = (
        audit.response_preview[:500] if audit.response_preview else None
    )
    error = (audit.error[:500] if audit.error else None)

    return AgentAuditLog(
        user_id=audit.user_id,
        query_text=query_text,
        tier_used=audit.tier_used,
        routing_reason=audit.routing_reason,
        tools_called=audit.tools_called or None,
        tool_call_count=audit.tool_call_count,
        llm_model=audit.llm_model,
        input_tokens=audit.input_tokens,
        output_tokens=audit.output_tokens,
        cost_usd=audit.cost_usd,
        success=audit.success,
        response_preview=response_preview,
        error=error,
        total_latency_ms=audit.total_latency_ms,
    )


def to_dict(audit: RouteAudit) -> dict[str, Any]:
    """JSON-friendly snapshot — for tests / debug logging."""
    return asdict(audit)
