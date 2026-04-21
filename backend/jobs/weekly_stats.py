"""Weekly analytics stats CLI.

Usage:
    python -m backend.jobs.weekly_stats            # last 7 days
    python -m backend.jobs.weekly_stats --days 30  # custom window

Prints a human-readable summary of event counts, top buttons, and Mini App
load-time percentiles. Safe to run anytime — read-only queries on `events`.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from backend import analytics
from backend.database import get_session_factory


async def _run(days: int) -> None:
    session_factory = get_session_factory()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with session_factory() as db:
        counts = await analytics.count_by_type(db, since=since)
        buttons = await analytics.button_tap_leaderboard(db, since=since, limit=10)
        load_p = await analytics.miniapp_load_time_percentiles(db, since=since)

    print(f"=== Weekly stats — last {days} days (since {since.isoformat()}) ===\n")

    print("Event counts")
    print("-" * 40)
    if not counts:
        print("  (no events)")
    else:
        for event_type, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  {event_type:28s} {count:>8}")

    print("\nButton taps (top 10)")
    print("-" * 40)
    if not buttons:
        print("  (no button taps)")
    else:
        for button, count in buttons:
            print(f"  {button:28s} {count:>8}")

    print("\nMini App load time (ms)")
    print("-" * 40)
    if not load_p or load_p.get("p50", 0) == 0:
        print("  (no miniapp_loaded events)")
    else:
        print(f"  p50: {load_p['p50']:.0f} ms")
        print(f"  p95: {load_p['p95']:.0f} ms")
        print(f"  p99: {load_p['p99']:.0f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly analytics stats")
    parser.add_argument(
        "--days", type=int, default=7, help="Lookback window in days (default: 7)"
    )
    args = parser.parse_args()
    asyncio.run(_run(args.days))


if __name__ == "__main__":
    main()
