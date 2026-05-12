#!/usr/bin/env python
"""Generate the 50-invite founding-member distribution package.

Phase 4.1, Stories C.1 + Task D.3.

The script:

  1. Generates N invite tokens (default 50, distributed evenly across the
     5 soft-launch sources) with high-entropy URL-safe tokens.
  2. Inserts the corresponding ``invite_codes`` rows in one transaction
     with ``grants_founding_status=TRUE``.
  3. Writes a CSV (default ``invite_links_<batch>.csv``) ready for the
     operator to hand-distribute.

Usage:
  python scripts/soft_launch_acquisition.py --batch soft-launch-2026-06
  python scripts/soft_launch_acquisition.py --count 50 --bot BeTienBot
  python scripts/soft_launch_acquisition.py --dry-run        # no DB write

Idempotency:
  - Re-running with the same --batch name appends new rows (we do NOT
    purge previous tokens). Token collisions are vanishingly unlikely
    (128-bit secrets) but the table's ``token`` unique constraint
    guards against silent overwrites.

Safety:
  - Tokens are generated with :mod:`secrets`; they are NOT predictable.
  - The CSV is written to the current working directory by default so
    the operator decides where it lives. Treat the CSV as sensitive —
    each row is a one-time founding-member ticket.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from backend.database import get_session_factory
from backend.models.invite_code import InviteCode

logger = logging.getLogger(__name__)


# 5 sources from Phase 4.1 spec (Story C.1). Order is significant: the
# distribution loop assigns sources round-robin from this list.
SOURCES: tuple[str, ...] = (
    "friends",
    "personal_fb",
    "vn_finance_community",
    "direct_msg",
    "tg_finance_groups",
)

DEFAULT_BOT_USERNAME = "BeTienBot"
DEFAULT_COUNT = 50
DEFAULT_BATCH = "soft-launch"


@dataclass(frozen=True)
class GeneratedInvite:
    token: str
    source: str
    invite_url: str


def _build_invite_url(bot_username: str, token: str) -> str:
    return f"https://t.me/{bot_username}?start=invite_{token}"


def _generate_tokens(count: int) -> list[str]:
    """Generate `count` distinct URL-safe tokens.

    Uses 16 bytes (~22 chars base64-url) — 128 bits of entropy, so the
    chance of collision in 50 tokens is ~10⁻³⁵.
    """
    seen: set[str] = set()
    tokens: list[str] = []
    while len(tokens) < count:
        candidate = secrets.token_urlsafe(16)
        if candidate in seen:
            continue
        seen.add(candidate)
        tokens.append(candidate)
    return tokens


def _distribute_sources(count: int) -> list[str]:
    """Round-robin assignment across the 5 sources. With count=50 each
    source gets exactly 10 invites; with other counts the remainder is
    spread to the earliest sources first.
    """
    return [SOURCES[i % len(SOURCES)] for i in range(count)]


async def _insert_rows(
    invites: list[GeneratedInvite],
    *,
    batch_name: str,
    grants_founding: bool,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        # Pre-check token collisions against existing rows (extremely
        # unlikely, but cheap and avoids a partial-insert state).
        tokens = [inv.token for inv in invites]
        existing = (
            await db.execute(
                select(InviteCode.token).where(InviteCode.token.in_(tokens))
            )
        ).scalars().all()
        if existing:
            raise RuntimeError(
                f"Token collision detected ({len(existing)} pre-existing). "
                "Re-run to regenerate."
            )

        rows = [
            InviteCode(
                token=inv.token,
                source=inv.source,
                batch_name=batch_name,
                grants_founding_status=grants_founding,
            )
            for inv in invites
        ]
        db.add_all(rows)
        await db.commit()
        logger.info(
            "Inserted %d invite_codes rows (batch=%s, grants_founding=%s)",
            len(rows),
            batch_name,
            grants_founding,
        )


def _write_csv(
    invites: list[GeneratedInvite],
    *,
    output_path: Path,
    batch_name: str,
    grants_founding: bool,
) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "sequence",
                "invite_url",
                "source",
                "batch_name",
                "grants_founding_status",
                "generated_at_utc",
            ]
        )
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for i, inv in enumerate(invites, start=1):
            writer.writerow(
                [
                    i,
                    inv.invite_url,
                    inv.source,
                    batch_name,
                    "TRUE" if grants_founding else "FALSE",
                    now,
                ]
            )


def _summary(invites: list[GeneratedInvite]) -> str:
    by_source: dict[str, int] = {}
    for inv in invites:
        by_source[inv.source] = by_source.get(inv.source, 0) + 1
    parts = [f"  {src}: {n}" for src, n in sorted(by_source.items())]
    return "\n".join(parts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Phase 4.1 founding-member invite links "
            "(50 by default, distributed across 5 acquisition sources)."
        )
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Number of invite links to generate (default: {DEFAULT_COUNT}).",
    )
    parser.add_argument(
        "--batch",
        type=str,
        default=DEFAULT_BATCH,
        help=f"Batch label stored on each row (default: {DEFAULT_BATCH}).",
    )
    parser.add_argument(
        "--bot",
        type=str,
        default=os.environ.get("TELEGRAM_BOT_USERNAME", DEFAULT_BOT_USERNAME),
        help=(
            "Telegram bot username (no @). Defaults to env "
            "TELEGRAM_BOT_USERNAME or 'BeTienBot'."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV path. Defaults to invite_links_<batch>.csv in CWD.",
    )
    parser.add_argument(
        "--no-founding",
        action="store_true",
        help="Generate invites WITHOUT founding-member grant (rare; for testing).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print to stdout / CSV without writing DB rows.",
    )
    return parser.parse_args()


async def _run() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()

    if args.count <= 0:
        logger.error("count must be > 0 (got %s)", args.count)
        return 2

    tokens = _generate_tokens(args.count)
    sources = _distribute_sources(args.count)
    invites = [
        GeneratedInvite(
            token=t, source=s, invite_url=_build_invite_url(args.bot, t)
        )
        for t, s in zip(tokens, sources)
    ]

    output_path = (
        Path(args.output)
        if args.output
        else Path.cwd() / f"invite_links_{args.batch}.csv"
    )

    grants_founding = not args.no_founding

    print(f"Generated {len(invites)} invite links for batch '{args.batch}':")
    print(_summary(invites))
    print(f"grants_founding_status: {grants_founding}")
    print(f"CSV: {output_path}")

    _write_csv(
        invites,
        output_path=output_path,
        batch_name=args.batch,
        grants_founding=grants_founding,
    )

    if args.dry_run:
        print("\n[dry-run] Skipping DB insert.")
        return 0

    await _insert_rows(
        invites, batch_name=args.batch, grants_founding=grants_founding
    )
    print(f"\n✅ Inserted {len(invites)} rows into invite_codes.")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
