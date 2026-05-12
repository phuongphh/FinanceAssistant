"""Feedback SLA worker (Phase 4.1, A.7).

Hourly cron: scan ``feedbacks`` for rows open > 24h with no reply and
no prior breach alert. Send ONE operator message per row, set
``sla_breach_alerted_at`` so the next pass skips it.

The partial index ``idx_feedback_unanswered_age`` (Phase 4.1.02) keeps
the scan cheap regardless of historical feedback volume.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from backend.database import get_session_factory
from backend.feedback.services.feedback_triage_service import (
    find_breached,
    load_triage_copy,
    mark_breach_alerted,
)
from backend.ports.notifier import get_notifier

logger = logging.getLogger(__name__)

SLA_THRESHOLD_HOURS = 24


async def run_feedback_sla_job() -> int:
    """Cron entry point. Returns number of alerts sent."""
    operator_chat_raw = os.environ.get("OPERATOR_TELEGRAM_ID", "").strip()
    if not operator_chat_raw:
        return 0
    try:
        operator_chat_id = int(operator_chat_raw)
    except ValueError:
        logger.error("OPERATOR_TELEGRAM_ID is not numeric")
        return 0

    copy = load_triage_copy()["operator"]
    notifier = get_notifier()
    sent = 0

    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            breached = await find_breached(db, threshold_hours=SLA_THRESHOLD_HOURS)
            for fb in breached:
                created = (
                    fb.created_at.replace(tzinfo=timezone.utc)
                    if fb.created_at.tzinfo is None
                    else fb.created_at
                )
                age_h = int(
                    (datetime.now(timezone.utc) - created).total_seconds() // 3600
                )
                snippet = (fb.content or "").replace("\n", " ")[:80]
                msg = copy["sla_alert"].format(
                    id_short=str(fb.id)[:8],
                    age_h=age_h,
                    user_id_short=str(fb.user_id)[:8],
                    snippet=snippet,
                )
                try:
                    await notifier.send_message(
                        chat_id=operator_chat_id,
                        text=msg,
                        parse_mode="HTML",
                    )
                    await mark_breach_alerted(db, fb)
                    sent += 1
                except Exception:
                    logger.exception("SLA alert send failed for feedback=%s", fb.id)

            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return sent
