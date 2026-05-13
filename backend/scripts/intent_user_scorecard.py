"""User-testing scorecard generator (Story #133).

CLI helper that reads the ``events`` table for a single user over a
window and prints the scoreboard row defined in
``docs/current/phase-3.5-user-testing.md`` § 4. Owner runs this once
per recruited user on Day 7.

Usage:

    python -m backend.scripts.intent_user_scorecard \\
        --user-id <uuid> \\
        --days 7

The script never modifies the DB. It does NOT depend on the FastAPI
app being up — opens its own session via the standard config. Falls
back gracefully when DATABASE_URL isn't set (prints a hint instead of
stack-tracing).

Why a CLI rather than a Mini App page: user testing is a one-shot
ops task, not a recurring product surface. A CLI is faster to write,
easier to grep through outputs, and doesn't add an admin UI that
would need its own auth story.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.models.event import Event

logger = logging.getLogger(__name__)


_INTENT_EVENTS = (
    "intent_classified",
    "intent_handler_executed",
    "intent_unclear",
    "intent_clarification_sent",
    "intent_clarification_resolved",
    "intent_confirm_sent",
    "intent_confirm_accepted",
    "intent_confirm_rejected",
    "intent_oos_declined",
    "intent_followup_tapped",
    "advisory_response_sent",
    "advisory_rate_limited",
    "voice_query_received",
    "voice_query_failed",
    "morning_briefing_sent",
    "morning_briefing_opened",
    "llm_classifier_call",
)


async def collect(user_id: uuid.UUID, days: int) -> dict:
    """Pull the events that go into the per-user scorecard.

    Returns a dict shaped like the markdown table — one key per
    metric — so ``print_scorecard`` doesn't reach back into the DB.
    """
    from backend.database import get_session_factory

    session_factory = get_session_factory()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with session_factory() as db:
        # Single grouped query gets all event-type counts in one trip.
        stmt = (
            select(Event.event_type, func.count())
            .where(
                Event.user_id == user_id,
                Event.timestamp >= cutoff,
                Event.event_type.in_(list(_INTENT_EVENTS)),
            )
            .group_by(Event.event_type)
        )
        rows = (await db.execute(stmt)).all()
        counts = {row[0]: int(row[1]) for row in rows}

        # Average latency over classified events.
        latency_stmt = (
            select(
                func.avg(
                    func.cast(
                        Event.properties["latency_ms"].astext,
                        _Float(),
                    )
                )
            )
            .where(
                Event.event_type == "intent_classified",
                Event.user_id == user_id,
                Event.timestamp >= cutoff,
            )
        )
        avg_latency = float(
            (await db.execute(latency_stmt)).scalar() or 0.0
        )

        # Classifier split — rule vs llm vs none.
        classifier_stmt = (
            select(
                Event.properties["classifier"].astext,
                func.count(),
            )
            .where(
                Event.event_type == "intent_classified",
                Event.user_id == user_id,
                Event.timestamp >= cutoff,
            )
            .group_by(Event.properties["classifier"].astext)
        )
        by_classifier: dict[str, int] = {}
        for row in (await db.execute(classifier_stmt)).all():
            key = row[0] or "unknown"
            by_classifier[key] = int(row[1])

    total_classified = counts.get("intent_classified", 0)
    rule_count = by_classifier.get("rule", 0)
    return {
        "user_id": str(user_id),
        "window_days": days,
        "total_classified": total_classified,
        "by_classifier": by_classifier,
        "rule_rate": _safe_div(rule_count, total_classified),
        "unclear_rate": _safe_div(
            counts.get("intent_unclear", 0), total_classified
        ),
        "execution_rate": _safe_div(
            counts.get("intent_handler_executed", 0), total_classified
        ),
        "briefing_open_rate": _safe_div(
            counts.get("morning_briefing_opened", 0),
            counts.get("morning_briefing_sent", 0),
        ),
        "avg_latency_ms": round(avg_latency, 1),
        "advisory_count": counts.get("advisory_response_sent", 0),
        "advisory_rate_limited": counts.get("advisory_rate_limited", 0),
        "voice_count": counts.get("voice_query_received", 0),
        "voice_failed": counts.get("voice_query_failed", 0),
        "confirm_sent": counts.get("intent_confirm_sent", 0),
        "confirm_accepted": counts.get("intent_confirm_accepted", 0),
        "confirm_rejected": counts.get("intent_confirm_rejected", 0),
        "followup_tapped": counts.get("intent_followup_tapped", 0),
        "raw_counts": counts,
    }


def _safe_div(num: int, denom: int) -> float:
    return round(num / denom, 4) if denom > 0 else 0.0


def _Float():
    from sqlalchemy import Float
    return Float


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def print_scorecard(scorecard: dict) -> None:
    """Render the scoreboard row matching the markdown table.

    Output is plain ASCII so it pastes cleanly into Markdown / Sheets
    without unicode-escape issues.
    """
    sc = scorecard
    print()
    print("=" * 60)
    print(f"User {sc['user_id']} — last {sc['window_days']} days")
    print("=" * 60)

    rows = [
        ("Total queries", sc["total_classified"], "≥25"),
        ("Rule classifier rate", _format_pct(sc["rule_rate"]), "≥60%"),
        ("Unclear rate", _format_pct(sc["unclear_rate"]), "≤20%"),
        ("Handler executed rate", _format_pct(sc["execution_rate"]), "≥70%"),
        ("Briefing open rate", _format_pct(sc["briefing_open_rate"]), "≥4/7"),
        ("Avg response latency (ms)", sc["avg_latency_ms"], "≤2000"),
        ("Advisory responses", sc["advisory_count"], "informational"),
        ("Advisory rate-limited", sc["advisory_rate_limited"], "≤2"),
        ("Voice queries received", sc["voice_count"], "informational"),
        ("Voice queries failed", sc["voice_failed"], "≤1"),
        ("Confirms sent", sc["confirm_sent"], "informational"),
        ("Confirm accepted", sc["confirm_accepted"], ""),
        ("Confirm rejected", sc["confirm_rejected"], "<30% of sent"),
        ("Follow-up button taps", sc["followup_tapped"], "informational"),
    ]
    for label, value, target in rows:
        print(f"{label:<32} {str(value):<12} target: {target}")

    print("\nClassifier split:")
    for key, count in sc["by_classifier"].items():
        print(f"  {key:<8} {count}")
    print()


async def _amain(args: argparse.Namespace) -> int:
    try:
        user_uuid = uuid.UUID(args.user_id)
    except ValueError:
        print(f"Invalid UUID: {args.user_id}", file=sys.stderr)
        return 2

    try:
        scorecard = await collect(user_uuid, days=args.days)
    except Exception as exc:  # noqa: BLE001
        print(
            f"Failed to collect events: {exc}\n"
            "Hint: ensure DATABASE_URL is set in your .env file.",
            file=sys.stderr,
        )
        return 1

    if args.json:
        import json
        print(json.dumps(scorecard, indent=2))
    else:
        print_scorecard(scorecard)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the Phase 3.5 user-testing scorecard for one user. "
            "Reads from the events table; doesn't modify anything."
        )
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="Internal user UUID (NOT Telegram ID — query users table first)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Window size in days (default 7)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable text",
    )
    args = parser.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
