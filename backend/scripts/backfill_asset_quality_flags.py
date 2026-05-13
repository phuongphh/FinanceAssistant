"""Backfill Phase 4.2 asset quality flags.

Dry run by default. Use --commit only after operator reviews the printed
candidate rows. Targets old 50tr onboarding demo placeholders and marks them
as placeholder/confirmed so they no longer inflate real net worth.
"""
from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal

from sqlalchemy import select

from backend.database import get_session_factory
from backend.wealth.models.asset import Asset

DEMO_VALUE = Decimal("50000000")


async def run(*, commit: bool, limit: int) -> int:
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = (
            select(Asset)
            .where(
                Asset.current_value == DEMO_VALUE,
                Asset.is_placeholder_asset.is_(False),
                Asset.name.in_(["Twin demo", "Tài sản ban đầu"]),
            )
            .order_by(Asset.created_at.asc())
            .limit(limit)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        print(f"Candidates: {len(rows)}")
        for asset in rows[:10]:
            print(f"- {asset.id} user={asset.user_id} name={asset.name!r} value={asset.current_value}")
        if commit:
            for asset in rows:
                asset.is_placeholder_asset = True
                asset.is_confirmed = True
                asset.data_quality_warning_type = "legacy_demo_placeholder"
            await db.commit()
            print("Committed.")
        else:
            await db.rollback()
            print("Dry-run only. Re-run with --commit after operator review.")
        return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(run(commit=args.commit, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
