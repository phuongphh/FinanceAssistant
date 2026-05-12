#!/usr/bin/env python
"""Standalone runner for the daily KPI digest (Phase 4.1, A.6).

Usage:
  python scripts/kpi_digest.py                  # send yesterday's digest
  python scripts/kpi_digest.py --date 2026-05-12 --print
  python scripts/kpi_digest.py --print          # render to stdout only

Reads ``OPERATOR_TELEGRAM_ID`` from the env unless ``--print`` is set.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date

from backend.database import get_session_factory
from backend.jobs.daily_kpi_digest_job import compose_digest, run_daily_kpi_digest_job


async def _print_only(day: date | None) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        text = await compose_digest(db, day=day)
        print(text)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send / preview the daily KPI digest.")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="ISO date (YYYY-MM-DD). Defaults to yesterday UTC.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print to stdout without sending. Skips OPERATOR_TELEGRAM_ID requirement.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    day = date.fromisoformat(args.date) if args.date else None

    if args.print:
        asyncio.run(_print_only(day))
        return 0

    sent = asyncio.run(run_daily_kpi_digest_job())
    return 0 if sent else 1


if __name__ == "__main__":
    raise SystemExit(main())
