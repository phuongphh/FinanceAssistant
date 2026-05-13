#!/usr/bin/env python3
"""One-click broadcast for Phase deploy announcements.

Reads message templates from a markdown file (default:
``docs/current/phase-3.8-deploy-announcements.md``), picks one by ID,
and sends it via Telegram to all eligible users.

Designed so the operator can run a single command per announcement
without copy-pasting Python into a REPL. Failures on individual sends
(blocked bot, deactivated chat) are logged but never abort the run.

Usage::

    # Preview before sending
    python scripts/broadcast_announcement.py --message teaser --dry-run

    # Send to all active users (asks for confirmation)
    python scripts/broadcast_announcement.py --message launch

    # Send to one telegram_id (testing)
    python scripts/broadcast_announcement.py --message launch --only 123456789

    # Skip users who already engaged with new features
    python scripts/broadcast_announcement.py --message followup \\
        --skip-engaged --launch-date 2026-05-07

    # Non-interactive (CI / scripted)
    python scripts/broadcast_announcement.py --message launch --yes

Run from repo root. Requires ``DATABASE_URL``, ``TELEGRAM_BOT_TOKEN``,
and ``OWNER_TELEGRAM_ID`` in env (or .env).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

# Ensure repo root on sys.path so `import backend...` works when invoked
# directly via `python scripts/broadcast_announcement.py`.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.database import get_session_factory  # noqa: E402
from backend.models.user import User  # noqa: E402
from backend.services.telegram_service import (  # noqa: E402
    close_client,
    send_message,
)

DEFAULT_DOC = REPO_ROOT / "docs" / "current" / "phase-3.8-deploy-announcements.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("broadcast")


@dataclass
class Message:
    msg_id: str
    title: str
    body: str


def parse_messages(doc_path: Path) -> dict[str, Message]:
    """Extract messages from the announcement markdown.

    Convention: each message is an H2 section containing a line
    ``**ID:** `<id>``` and a fenced code block. Body = first fenced
    block after the ID line.
    """
    text = doc_path.read_text(encoding="utf-8")
    messages: dict[str, Message] = {}

    section_re = re.compile(r"^## (Message \d+ — [^\n]+)$", re.MULTILINE)
    sections = list(section_re.finditer(text))

    for i, match in enumerate(sections):
        title = match.group(1).strip()
        start = match.end()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
        block = text[start:end]

        id_match = re.search(r"\*\*ID:\*\*\s*`([a-z0-9_-]+)`", block)
        if not id_match:
            continue
        msg_id = id_match.group(1)

        code_match = re.search(r"```\n(.*?)\n```", block, re.DOTALL)
        if not code_match:
            log.warning("Section '%s' has ID but no fenced body — skipped", title)
            continue
        body = code_match.group(1).rstrip()

        messages[msg_id] = Message(msg_id=msg_id, title=title, body=body)

    return messages


async def collect_recipients(
    only: int | None,
    skip_engaged: bool,
    launch_date: date | None,
) -> list[tuple[int, str | None]]:
    """Return list of (telegram_id, display_name) for the broadcast.

    `skip_engaged` excludes users who created a goal on or after
    launch_date — a proxy for "already tried the new features". Extend
    as more 3.8 signals become available (rental flag, income stream).
    """
    factory = get_session_factory()
    async with factory() as db:
        if only is not None:
            rows = (
                await db.execute(
                    select(User.telegram_id, User.display_name).where(
                        User.telegram_id == only
                    )
                )
            ).all()
            return [(int(tg_id), name) for tg_id, name in rows]

        rows = (
            await db.execute(
                select(User.telegram_id, User.display_name, User.id).where(
                    User.is_active.is_(True)
                )
            )
        ).all()

        if not skip_engaged:
            return [(int(tg_id), name) for tg_id, name, _ in rows]

        if launch_date is None:
            log.warning(
                "--skip-engaged given without --launch-date; ignoring filter"
            )
            return [(int(tg_id), name) for tg_id, name, _ in rows]

        engaged_ids = await _engaged_user_ids(db, launch_date)
        filtered = [
            (int(tg_id), name)
            for tg_id, name, uid in rows
            if uid not in engaged_ids
        ]
        log.info(
            "skip-engaged: %d users excluded (engaged since %s)",
            len(rows) - len(filtered),
            launch_date,
        )
        return filtered


async def _engaged_user_ids(db, launch_date: date) -> set:
    """Best-effort detection of users who engaged with Phase 3.8 features.

    Uses goals table (exists today). If the Phase 3.8 income/recurring
    models are present, extends the check. Missing tables don't error.
    """
    engaged: set = set()
    cutoff = datetime.combine(launch_date, datetime.min.time())

    try:
        from backend.models.goal import Goal  # type: ignore

        rows = (
            await db.execute(
                select(Goal.user_id).where(Goal.created_at >= cutoff).distinct()
            )
        ).all()
        engaged.update(uid for (uid,) in rows)
    except Exception as e:
        log.debug("goal engagement check skipped: %s", e)

    return engaged


def confirm(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return ans in {"y", "yes"}


async def broadcast(
    message: Message,
    recipients: list[tuple[int, str | None]],
    throttle_ms: int,
) -> tuple[int, int]:
    """Send `message` to each recipient. Returns (sent, failed)."""
    sent = failed = 0
    delay = throttle_ms / 1000.0

    for idx, (tg_id, name) in enumerate(recipients, start=1):
        try:
            result = await send_message(tg_id, message.body, parse_mode="Markdown")
            if result is None:
                failed += 1
                log.warning(
                    "[%d/%d] failed (no response) -> %s (%s)",
                    idx,
                    len(recipients),
                    tg_id,
                    name,
                )
            else:
                sent += 1
                log.info(
                    "[%d/%d] sent -> %s (%s)", idx, len(recipients), tg_id, name
                )
        except Exception as e:
            failed += 1
            log.error(
                "[%d/%d] error -> %s (%s): %s",
                idx,
                len(recipients),
                tg_id,
                name,
                e,
            )

        if delay and idx < len(recipients):
            await asyncio.sleep(delay)

    return sent, failed


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--message", required=True, help="Message ID (e.g. teaser, launch, followup)")
    p.add_argument("--file", type=Path, default=DEFAULT_DOC, help="Source markdown file")
    p.add_argument("--dry-run", action="store_true", help="Show recipients + preview, don't send")
    p.add_argument("--only", type=int, help="Send to a single telegram_id (testing)")
    p.add_argument(
        "--skip-engaged",
        action="store_true",
        help="Exclude users who engaged with Phase 3.8 features since --launch-date",
    )
    p.add_argument(
        "--launch-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="YYYY-MM-DD — required with --skip-engaged",
    )
    p.add_argument("--throttle-ms", type=int, default=50, help="Sleep between sends (ms)")
    p.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN not configured")
        return 2
    if not settings.owner_telegram_id:
        log.error(
            "OWNER_TELEGRAM_ID not configured — refusing to broadcast "
            "(safety check against running with the wrong env)"
        )
        return 2

    if not args.file.exists():
        log.error("Source file not found: %s", args.file)
        return 2

    messages = parse_messages(args.file)
    if args.message not in messages:
        log.error(
            "Message '%s' not found in %s. Available: %s",
            args.message,
            args.file,
            ", ".join(sorted(messages)) or "(none)",
        )
        return 2
    msg = messages[args.message]

    recipients = await collect_recipients(
        only=args.only,
        skip_engaged=args.skip_engaged,
        launch_date=args.launch_date,
    )

    print()
    print(f"=== Broadcast preview ===")
    print(f"Source:     {args.file}")
    print(f"Message ID: {msg.msg_id}")
    print(f"Section:    {msg.title}")
    print(f"Recipients: {len(recipients)}")
    if recipients[:3]:
        sample = ", ".join(f"{tg} ({name})" for tg, name in recipients[:3])
        print(f"  first 3:  {sample}")
    print()
    print("--- Body (first 400 chars) ---")
    print(msg.body[:400] + ("..." if len(msg.body) > 400 else ""))
    print("--- end preview ---")
    print()

    if args.dry_run:
        log.info("dry-run: nothing sent")
        return 0

    if not recipients:
        log.warning("No recipients — nothing to do")
        return 0

    if not args.yes and not confirm(f"Send to {len(recipients)} users?"):
        log.info("Cancelled")
        return 1

    sent, failed = await broadcast(msg, recipients, args.throttle_ms)
    print()
    log.info("Done. sent=%d failed=%d total=%d", sent, failed, len(recipients))
    return 0 if failed == 0 else 1


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print()
        log.warning("Interrupted")
        return 130


async def _run(args: argparse.Namespace) -> int:
    try:
        return await main_async(args)
    finally:
        await close_client()


if __name__ == "__main__":
    sys.exit(main())
