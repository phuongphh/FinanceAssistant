"""Aggregations for the Phase 3.5 intent admin dashboard.

Aggregates events emitted by ``backend.bot.handlers.free_form_text``
into the shape the admin endpoint consumes:

  - daily totals (queries / rule-vs-llm split)
  - confidence histogram
  - top unclear queries (fallback signal for new patterns)
  - LLM cost trend (7d / 30d)
  - rate-of-rule-handling alerts

All reads go through SQL aggregations on ``events`` so a single page
load is one or two roundtrips even with 100k events.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.event import Event

logger = logging.getLogger(__name__)


EVENT_INTENT_CLASSIFIED = "intent_classified"
EVENT_INTENT_HANDLER_EXECUTED = "intent_handler_executed"
EVENT_INTENT_UNCLEAR = "intent_unclear"
EVENT_INTENT_CLARIFY_SENT = "intent_clarification_sent"
EVENT_INTENT_CLARIFY_RESOLVED = "intent_clarification_resolved"
EVENT_INTENT_CONFIRM_SENT = "intent_confirm_sent"
EVENT_INTENT_OOS_DECLINED = "intent_oos_declined"
EVENT_LLM_CLASSIFIER_CALL = "llm_classifier_call"


# Alert thresholds — see acceptance criteria of issue #124.
ALERT_LLM_COST_PER_DAY = 0.50
ALERT_RULE_RATE_FLOOR = 0.50      # rule classifier should handle ≥50%
ALERT_UNCLEAR_RATE_CEILING = 0.20  # unclear rate should stay ≤20%


async def daily_summary(
    db: AsyncSession, *, since: datetime | None = None
) -> dict:
    """Headline metrics for the admin dashboard.

    Returns counts + ratios + LLM cost. Bound to a window — default
    "last 24 hours" — so the endpoint can serve fast without scanning
    the full events table.
    """
    since = since or (datetime.now(timezone.utc) - timedelta(days=1))

    # One query for all classified-event totals split by classifier.
    stmt = (
        select(
            Event.properties["classifier"].astext.label("classifier"),
            func.count().label("total"),
        )
        .where(
            Event.event_type == EVENT_INTENT_CLASSIFIED,
            Event.timestamp >= since,
        )
        .group_by(Event.properties["classifier"].astext)
    )
    by_classifier: Counter[str] = Counter()
    for row in (await db.execute(stmt)).all():
        by_classifier[row.classifier or "unknown"] = int(row.total)
    total_classified = sum(by_classifier.values())

    # Unclear / OOS rates.
    unclear_stmt = (
        select(func.count())
        .select_from(Event)
        .where(
            Event.event_type.in_(
                [EVENT_INTENT_UNCLEAR, EVENT_INTENT_OOS_DECLINED]
            ),
            Event.timestamp >= since,
        )
    )
    unclear_total = int((await db.execute(unclear_stmt)).scalar() or 0)

    # Cumulative LLM cost — sum the cost_usd property.
    cost_stmt = (
        select(
            func.coalesce(
                func.sum(
                    func.cast(
                        Event.properties["cost_usd"].astext,
                        _Float(),
                    )
                ),
                0,
            )
        )
        .where(
            Event.event_type == EVENT_LLM_CLASSIFIER_CALL,
            Event.timestamp >= since,
        )
    )
    llm_cost_usd = float((await db.execute(cost_stmt)).scalar() or 0.0)

    # Latency p50 (rough) — the rule classifier dominates so a simple
    # average gives a useful read without window-percentile gymnastics.
    latency_stmt = (
        select(
            func.coalesce(
                func.avg(
                    func.cast(
                        Event.properties["latency_ms"].astext,
                        _Float(),
                    )
                ),
                0,
            )
        )
        .where(
            Event.event_type == EVENT_INTENT_CLASSIFIED,
            Event.timestamp >= since,
        )
    )
    avg_latency_ms = float((await db.execute(latency_stmt)).scalar() or 0.0)

    rule_rate = (
        (by_classifier["rule"] / total_classified)
        if total_classified
        else 0.0
    )
    unclear_rate = (
        (unclear_total / total_classified)
        if total_classified
        else 0.0
    )

    return {
        "since": since.isoformat(),
        "total_classified": total_classified,
        "by_classifier": {
            "rule": by_classifier["rule"],
            "llm": by_classifier["llm"],
            "none": by_classifier["none"],
        },
        "rule_rate": round(rule_rate, 4),
        "unclear_total": unclear_total,
        "unclear_rate": round(unclear_rate, 4),
        "llm_cost_usd": round(llm_cost_usd, 6),
        "avg_latency_ms": round(avg_latency_ms, 1),
    }


async def confidence_histogram(
    db: AsyncSession, *, since: datetime | None = None
) -> dict[str, int]:
    """Bucketed histogram of intent_classified confidence values.

    Buckets: 0.0–0.2, 0.2–0.4, …, 0.8–1.0. Useful for spotting clusters
    of medium-confidence misses that should be promoted to rules.
    """
    since = since or (datetime.now(timezone.utc) - timedelta(days=7))

    confidence_col = func.cast(
        Event.properties["confidence"].astext, _Float()
    )
    bucket = case(
        (confidence_col < 0.2, "0.0-0.2"),
        (confidence_col < 0.4, "0.2-0.4"),
        (confidence_col < 0.6, "0.4-0.6"),
        (confidence_col < 0.8, "0.6-0.8"),
        else_="0.8-1.0",
    )
    stmt = (
        select(bucket.label("bucket"), func.count().label("count"))
        .where(
            Event.event_type == EVENT_INTENT_CLASSIFIED,
            Event.timestamp >= since,
        )
        .group_by(bucket)
    )
    rows = (await db.execute(stmt)).all()
    out = {b: 0 for b in ("0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0")}
    for row in rows:
        out[row.bucket] = int(row.count)
    return out


async def top_unclear_intents(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    limit: int = 20,
) -> list[dict]:
    """Top N intents that fell to UNCLEAR — signal for new rule patterns.

    We can't surface raw_text because the analytics PII filter drops
    that key on write. The intent value (e.g. ``query_assets``) plus
    count is still actionable: lots of UNCLEAR for the same low-conf
    intent means the rule patterns there are too narrow.
    """
    since = since or (datetime.now(timezone.utc) - timedelta(days=7))

    stmt = (
        select(
            Event.properties["intent"].astext.label("intent"),
            func.count().label("count"),
        )
        .where(
            Event.event_type == EVENT_INTENT_UNCLEAR,
            Event.timestamp >= since,
        )
        .group_by(Event.properties["intent"].astext)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"intent": row.intent or "unknown", "count": int(row.count)}
        for row in rows
    ]


async def cost_trend(
    db: AsyncSession, *, days: int = 7
) -> list[dict]:
    """Per-day LLM cost for the last ``days`` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    day_col = func.date_trunc("day", Event.timestamp).label("day")
    cost_col = func.cast(Event.properties["cost_usd"].astext, _Float())
    stmt = (
        select(day_col, func.coalesce(func.sum(cost_col), 0).label("cost"))
        .where(
            Event.event_type == EVENT_LLM_CLASSIFIER_CALL,
            Event.timestamp >= cutoff,
        )
        .group_by(day_col)
        .order_by(day_col)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "day": row.day.date().isoformat(),
            "cost_usd": round(float(row.cost or 0.0), 6),
        }
        for row in rows
    ]


def evaluate_alerts(summary: dict) -> list[dict]:
    """Translate a daily summary into actionable alert rows."""
    alerts: list[dict] = []
    if summary["llm_cost_usd"] > ALERT_LLM_COST_PER_DAY:
        alerts.append({
            "code": "llm_cost_high",
            "message": (
                f"LLM cost yesterday {summary['llm_cost_usd']:.4f} USD "
                f"exceeded {ALERT_LLM_COST_PER_DAY:.2f} USD threshold"
            ),
        })
    if (
        summary["total_classified"] > 100
        and summary["rule_rate"] < ALERT_RULE_RATE_FLOOR
    ):
        alerts.append({
            "code": "rule_rate_low",
            "message": (
                f"Rule classifier handled only "
                f"{summary['rule_rate'] * 100:.1f}% of queries — "
                "consider adding patterns"
            ),
        })
    if (
        summary["total_classified"] > 100
        and summary["unclear_rate"] > ALERT_UNCLEAR_RATE_CEILING
    ):
        alerts.append({
            "code": "unclear_rate_high",
            "message": (
                f"Unclear rate {summary['unclear_rate'] * 100:.1f}% "
                "exceeded ceiling — review top unclear intents"
            ),
        })
    return alerts


# SQLAlchemy float type — wrapped in a function so callers don't have
# to import the types module just to get this aggregation right.
def _Float():
    from sqlalchemy import Float
    return Float


__all__ = [
    "ALERT_LLM_COST_PER_DAY",
    "ALERT_RULE_RATE_FLOOR",
    "ALERT_UNCLEAR_RATE_CEILING",
    "EVENT_INTENT_CLARIFY_RESOLVED",
    "EVENT_INTENT_CLARIFY_SENT",
    "EVENT_INTENT_CLASSIFIED",
    "EVENT_INTENT_CONFIRM_SENT",
    "EVENT_INTENT_HANDLER_EXECUTED",
    "EVENT_INTENT_OOS_DECLINED",
    "EVENT_INTENT_UNCLEAR",
    "EVENT_LLM_CLASSIFIER_CALL",
    "confidence_histogram",
    "cost_trend",
    "daily_summary",
    "evaluate_alerts",
    "top_unclear_intents",
]
