#!/usr/bin/env python3
"""One-time re-engagement broadcast — Phase 4.5 / E5 #5.2.

Nudges the *dormant* cohort — users who joined a while ago but have gone
quiet — that Bé Tiền can now answer the Decision-Engine "nếu... thì sao"
questions. It fires **once per user**: the send stamps
``users.reengagement_broadcast_at`` so a second run never double-messages.

┌─────────────────────────────────────────────────────────────────────────┐
│ ⚠️  RUNBOOK — ĐỌC TRƯỚC KHI CHẠY THẬT                                      │
│                                                                           │
│  CHỈ chạy thật (``--confirm``) SAU KHI E1–E3 đã live trên production:     │
│    • E1 Shock simulation      (SHOCK_SIMULATION_ENABLED)                  │
│    • E2 Feasibility Q&A        (PLAN_FEASIBILITY_QA_ENABLED)              │
│    • E3 Độ nét / clarity meter (CLARITY_METER_ENABLED)                    │
│  Nếu gửi khi các surface còn dark, user bấm vào sẽ rơi vào advisory       │
│  fallback — lời hứa trong tin nhắn không khớp trải nghiệm → phản tác dụng.│
│                                                                           │
│  Quy trình an toàn:                                                       │
│    1. python scripts/send_reengagement_broadcast.py --dry-run            │
│       → in số đếm cohort, KHÔNG gửi, KHÔNG ghi DB.                        │
│    2. ... --only <telegram_id> --confirm  (thử trên chính mình)          │
│    3. ... --confirm                        (gửi thật cho cả cohort)       │
│  Chạy lại lần 2 là no-op: ai đã nhận thì reengagement_broadcast_at != NULL.│
└─────────────────────────────────────────────────────────────────────────┘

Run from repo root. Requires ``DATABASE_URL``, ``TELEGRAM_BOT_TOKEN`` and
``OWNER_TELEGRAM_ID`` in env (or .env).

Usage::

    # Count the cohort, send nothing (safe, no DB write)
    python scripts/send_reengagement_broadcast.py --dry-run

    # Test the copy on one telegram_id (does not require dormant status)
    python scripts/send_reengagement_broadcast.py --only 123456789 --confirm

    # Real one-time broadcast to the whole dormant cohort
    python scripts/send_reengagement_broadcast.py --confirm
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

# Ensure repo root on sys.path so `import backend...` works when invoked
# directly via `python scripts/send_reengagement_broadcast.py`.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402
from sqlalchemy import func, select, update  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.database import get_session_factory  # noqa: E402
from backend.models.conversation_context import ROLE_USER, ConversationContext  # noqa: E402
from backend.models.user import User  # noqa: E402
from backend.ports.notifier import get_notifier  # noqa: E402
from backend.services.user_status_service import STATUS_DORMANT, classify_status  # noqa: E402

_COPY_PATH = REPO_ROOT / "content" / "decision_copy.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reengage")


@dataclass(frozen=True)
class Recipient:
    user_id: object  # uuid.UUID at runtime; kept loose so tests can use fakes
    telegram_id: int


@lru_cache(maxsize=1)
def load_copy() -> str:
    """The re-engagement body from ``content/decision_copy.yaml``.

    Vietnamese copy lives in YAML (never hardcoded) so it passes the
    vi-localization-checker and can be tuned without a code change.
    """
    data = yaml.safe_load(_COPY_PATH.read_text(encoding="utf-8")) or {}
    body = ((data.get("reengagement") or {}).get("body") or "").strip()
    if not body:
        raise RuntimeError(
            "reengagement.body missing from content/decision_copy.yaml"
        )
    return body


def _eligible_dormant(row, now: datetime) -> bool:
    """A candidate is in the cohort iff it has never been broadcast to and
    classifies as ``dormant`` right now."""
    if row.reengagement_broadcast_at is not None:
        return False
    return (
        classify_status(
            row.created_at, row.last_active_at, row.manual_status, now=now
        )
        == STATUS_DORMANT
    )


def select_dormant(rows, *, now: datetime) -> list[Recipient]:
    """Pure cohort filter: never-broadcast dormant users. Testable without a DB."""
    return [
        Recipient(user_id=r.id, telegram_id=int(r.telegram_id))
        for r in rows
        if _eligible_dormant(r, now)
    ]


def _cohort_stmt():
    """Active, non-deleted users joined to their last activity timestamp
    (max user-role conversation turn) — the same signal the admin console
    uses to classify status."""
    last_active_sq = (
        select(
            ConversationContext.user_id.label("user_id"),
            func.max(ConversationContext.created_at).label("last_active_at"),
        )
        .where(ConversationContext.role == ROLE_USER)
        .group_by(ConversationContext.user_id)
        .subquery()
    )
    return (
        select(
            User.id,
            User.telegram_id,
            User.created_at,
            User.manual_status,
            User.reengagement_broadcast_at,
            last_active_sq.c.last_active_at,
        )
        .outerjoin(last_active_sq, last_active_sq.c.user_id == User.id)
        .where(User.is_active.is_(True), User.deleted_at.is_(None))
    )


async def collect_recipients(db, *, only: int | None, now: datetime) -> list[Recipient]:
    """Load the broadcast cohort from the DB.

    ``--only`` targets a single ``telegram_id`` for a test send — it bypasses
    the dormant requirement (so you can try the copy on your own active
    account) but still honours idempotency: an already-broadcast user is
    skipped.
    """
    rows = (await db.execute(_cohort_stmt())).all()
    if only is not None:
        return [
            Recipient(user_id=r.id, telegram_id=int(r.telegram_id))
            for r in rows
            if int(r.telegram_id) == only and r.reengagement_broadcast_at is None
        ]
    return select_dormant(rows, now=now)


async def broadcast(
    recipients: list[Recipient],
    body: str,
    *,
    notifier,
    on_sent,
    throttle_ms: int = 50,
) -> tuple[int, int]:
    """Send ``body`` to each recipient; call ``on_sent(user_id)`` after every
    successful delivery so the caller can stamp idempotency **incrementally**
    (crash-safe — a mid-run abort never re-messages the ones already sent).

    Returns ``(sent, failed)``. Individual send failures never abort the run.
    """
    sent = failed = 0
    delay = throttle_ms / 1000.0
    total = len(recipients)
    for idx, r in enumerate(recipients, start=1):
        try:
            result = await notifier.send_message(
                r.telegram_id, body, parse_mode="Markdown"
            )
        except Exception as exc:  # noqa: BLE001 — one bad chat must not stop the run
            failed += 1
            log.error("[%d/%d] error -> %s: %s", idx, total, r.telegram_id, exc)
            result = None
        else:
            if result is None:
                failed += 1
                log.warning("[%d/%d] failed -> %s", idx, total, r.telegram_id)
            else:
                await on_sent(r.user_id)
                sent += 1
                log.info("[%d/%d] sent -> %s", idx, total, r.telegram_id)
        if delay and idx < total:
            await asyncio.sleep(delay)
    return sent, failed


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Count the cohort and preview the copy; send nothing, write nothing",
    )
    p.add_argument(
        "--confirm",
        action="store_true",
        help="Required to actually send (guards against an accidental real run)",
    )
    p.add_argument(
        "--only",
        type=int,
        help="Send only to this telegram_id (test send; ignores dormant status)",
    )
    p.add_argument(
        "--throttle-ms", type=int, default=50, help="Sleep between sends (ms)"
    )
    return p.parse_args(argv)


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    # Safety: refuse to run against an env that has no bot / owner configured,
    # the same guard the announcement broadcaster uses.
    if not settings.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN not configured")
        return 2
    if not settings.owner_telegram_id:
        log.error(
            "OWNER_TELEGRAM_ID not configured — refusing to broadcast "
            "(safety check against running with the wrong env)"
        )
        return 2

    body = load_copy()
    now = datetime.now(timezone.utc)

    factory = get_session_factory()
    async with factory() as db:
        recipients = await collect_recipients(db, only=args.only, now=now)

        print()
        print("=== Re-engagement broadcast preview ===")
        print(f"Cohort:     dormant, never broadcast{' (--only override)' if args.only else ''}")
        print(f"Recipients: {len(recipients)}")
        print("--- Body ---")
        print(body)
        print("--- end preview ---")
        print()

        if args.dry_run:
            log.info("dry-run: %d recipient(s), nothing sent, DB untouched", len(recipients))
            return 0

        if not args.confirm:
            log.error("Refusing to send without --confirm (use --dry-run to preview)")
            return 1

        if not recipients:
            log.info("No eligible recipients — nothing to do")
            return 0

        notifier = get_notifier()

        async def on_sent(user_id) -> None:
            # Stamp + commit per recipient so the one-time guarantee survives a
            # crash mid-run. This is a script, not the service layer, so owning
            # the transaction boundary here is correct.
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(reengagement_broadcast_at=now)
            )
            await db.commit()

        sent, failed = await broadcast(
            recipients, body, notifier=notifier, on_sent=on_sent, throttle_ms=args.throttle_ms
        )

    print()
    log.info("Done. sent=%d failed=%d total=%d", sent, failed, len(recipients))
    return 0 if failed == 0 else 1


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print()
        log.warning("Interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
