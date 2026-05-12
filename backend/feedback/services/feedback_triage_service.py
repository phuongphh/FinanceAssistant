"""Operator-facing feedback triage service (Phase 4.1, A.7).

API:
  - ``list_inbox(db, limit)`` — open feedback, oldest first.
  - ``reply(db, feedback_id, message_text)`` — send to user, stamp
    ``first_responded_at`` + flip to ANSWERED.
  - ``find_breached(db, threshold_hours)`` — feedback open > N hours
    AND not yet alerted. Used by feedback_sla_worker.
  - ``mark_breach_alerted(db, feedback)`` — set
    ``sla_breach_alerted_at`` so we only alert once per row.

The service NEVER reaches into ``user.telegram_id`` directly — it
calls the Notifier port via :func:`resolve_targets` so a Zalo-linked
user receives the operator reply on every channel they've opted into.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.feedback.models.feedback import (
    FEEDBACK_STATUS_ACTIONED,
    FEEDBACK_STATUS_NEW,
    Feedback,
)
from backend.models.user import User
from backend.services.notifier_resolver import resolve_targets

logger = logging.getLogger(__name__)

_TRIAGE_PATH = (
    Path(__file__).resolve().parents[3]
    / "content"
    / "feedback"
    / "triage_responses.yaml"
)


def load_triage_copy() -> dict[str, Any]:
    with open(_TRIAGE_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_template(template_key: str) -> str | None:
    return load_triage_copy()["templates"].get(template_key)


def available_templates() -> list[str]:
    return sorted(load_triage_copy()["templates"].keys())


# ---------- Inbox ----------------------------------------------------


@dataclass
class InboxRow:
    feedback: Feedback
    user: User | None
    age_text: str
    snippet: str


def _format_age(created_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    created = (
        created_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None
        else created_at
    )
    delta = now - created
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "<1h"
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


async def list_inbox(db: AsyncSession, *, limit: int = 25) -> list[InboxRow]:
    stmt = (
        select(Feedback)
        .where(
            Feedback.status == FEEDBACK_STATUS_NEW,
            Feedback.first_responded_at.is_(None),
        )
        .order_by(Feedback.created_at.asc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    out: list[InboxRow] = []
    for fb in rows:
        user = await db.get(User, fb.user_id)
        snippet = (fb.content or "").replace("\n", " ")
        if len(snippet) > 100:
            snippet = snippet[:97] + "…"
        out.append(
            InboxRow(
                feedback=fb,
                user=user,
                age_text=_format_age(fb.created_at),
                snippet=snippet,
            )
        )
    return out


async def find_by_short_id(db: AsyncSession, short_id: str) -> Feedback | None:
    """Look up a feedback row by its 8-char ID prefix.

    The full UUID is too long for an operator command — the inbox
    listing prints the first 8 chars and ``/feedback_reply``
    accepts the same shorthand.

    Falls back to a full UUID parse for the rare case the operator
    pastes the full id.
    """
    short_id = short_id.strip()
    try:
        full = uuid.UUID(short_id)
        return await db.get(Feedback, full)
    except ValueError:
        pass

    # 8-char prefix match. Cast UUID to text in SQL for the LIKE.
    from sqlalchemy import cast, String

    stmt = (
        select(Feedback)
        .where(cast(Feedback.id, String).like(f"{short_id}%"))
        .order_by(Feedback.created_at.desc())
        .limit(2)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if len(rows) == 1:
        return rows[0]
    return None


# ---------- Reply ----------------------------------------------------


async def reply(db: AsyncSession, feedback: Feedback, message_text: str) -> bool:
    """Dispatch the reply via Notifier port. Stamps SLA fields on success.

    Returns True iff at least one channel accepted the message.
    """
    user = await db.get(User, feedback.user_id)
    if user is None:
        return False

    targets = resolve_targets(user)
    sent_any = False
    for target in targets:
        try:
            if target.channel == "telegram":
                await target.notifier.send_message(
                    chat_id=int(target.target_id),
                    text=message_text,
                    parse_mode="HTML",
                )
            else:
                await target.notifier.send_message(
                    chat_id=target.target_id, text=message_text
                )
            sent_any = True
        except Exception:
            logger.exception(
                "feedback_triage: reply send failed user=%s channel=%s",
                user.id,
                target.channel,
            )

    if not sent_any:
        return False

    feedback.first_responded_at = datetime.now(timezone.utc)
    feedback.status = FEEDBACK_STATUS_ACTIONED
    await db.flush()
    return True


# ---------- SLA worker queries ---------------------------------------


async def find_breached(
    db: AsyncSession, *, threshold_hours: int = 24
) -> list[Feedback]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
    stmt = (
        select(Feedback)
        .where(
            Feedback.status == FEEDBACK_STATUS_NEW,
            Feedback.first_responded_at.is_(None),
            Feedback.sla_breach_alerted_at.is_(None),
            Feedback.created_at < cutoff,
        )
        .order_by(Feedback.created_at.asc())
        .limit(50)
    )
    return list((await db.execute(stmt)).scalars().all())


async def mark_breach_alerted(db: AsyncSession, feedback: Feedback) -> None:
    feedback.sla_breach_alerted_at = datetime.now(timezone.utc)
    await db.flush()
