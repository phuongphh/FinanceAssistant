"""Operator triage commands (Phase 4.1, A.7).

Adds:

  /feedback_inbox                 — list open feedback (oldest first)
  /feedback_reply <id> <text>     — send a custom reply
  /feedback_reply <id> --template <key>  — send a templated reply

All three are gated on ``OPERATOR_TELEGRAM_ID``. Non-operators get a
gentle "unauthorized" message rather than a silent fail (the operator
might mistype the env var; we want to fail loudly enough to notice).
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession

from backend.feedback.services.feedback_triage_service import (
    available_templates,
    find_by_short_id,
    get_template,
    list_inbox,
    load_triage_copy,
    reply,
)
from backend.services.telegram_service import send_message

logger = logging.getLogger(__name__)


def _is_operator(telegram_id: int | None) -> bool:
    raw = os.environ.get("OPERATOR_TELEGRAM_ID", "").strip()
    if not raw or telegram_id is None:
        return False
    try:
        return int(raw) == int(telegram_id)
    except ValueError:
        return False


async def cmd_feedback_inbox(
    db: AsyncSession, chat_id: int, telegram_id: int | None
) -> None:
    copy = load_triage_copy()["operator"]
    if not _is_operator(telegram_id):
        await send_message(chat_id, copy["unauthorized"], parse_mode="HTML")
        return

    rows = await list_inbox(db, limit=25)
    if not rows:
        await send_message(chat_id, copy["inbox_empty"], parse_mode="HTML")
        return

    header = copy["inbox_header"].format(count=len(rows))
    lines = [header]
    for row in rows:
        fb = row.feedback
        # Wealth segment from the linked onboarding session, if any.
        segment = "?"
        founding = ""
        if row.user is not None:
            from backend.models.onboarding_session import OnboardingSession

            session = await db.get(OnboardingSession, row.user.id)
            if session and session.inferred_wealth_segment:
                segment = session.inferred_wealth_segment
            if row.user.is_founding_member:
                founding = " 🌱"
        emoji = ""
        if fb.onboarding_emoji_signal:
            emoji = {"love": "😍 ", "confused": "🤔 ", "dislike": "😕 "}.get(
                fb.onboarding_emoji_signal, ""
            )
        lines.append(
            copy["inbox_row"].format(
                id_short=str(fb.id)[:8],
                segment=segment,
                founding=founding,
                age=row.age_text,
                emoji=emoji,
                snippet=row.snippet,
            )
        )
    await send_message(chat_id, "\n".join(lines), parse_mode="HTML")


async def cmd_feedback_reply(
    db: AsyncSession,
    chat_id: int,
    telegram_id: int | None,
    raw_text: str,
) -> None:
    """Parse ``/feedback_reply <id> <message>`` (or ``--template <key>``)."""
    copy = load_triage_copy()["operator"]
    if not _is_operator(telegram_id):
        await send_message(chat_id, copy["unauthorized"], parse_mode="HTML")
        return

    # Strip the command name itself.
    parts = raw_text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await send_message(
            chat_id,
            "Cú pháp: <code>/feedback_reply &lt;id&gt; &lt;message&gt;</code> "
            "hoặc <code>/feedback_reply &lt;id&gt; --template &lt;key&gt;</code>",
            parse_mode="HTML",
        )
        return

    _cmd, short_id, rest = parts[0], parts[1], parts[2]

    feedback = await find_by_short_id(db, short_id)
    if feedback is None:
        await send_message(
            chat_id,
            copy["feedback_not_found"].format(feedback_id_short=short_id),
            parse_mode="HTML",
        )
        return

    # Template branch.
    template_key: str | None = None
    if rest.startswith("--template"):
        tokens = rest.split(maxsplit=1)
        if len(tokens) == 2:
            template_key = tokens[1].strip()

    if template_key:
        message_text = get_template(template_key)
        if not message_text:
            await send_message(
                chat_id,
                copy["unknown_template"].format(
                    template=template_key,
                    available=", ".join(available_templates()),
                ),
                parse_mode="HTML",
            )
            return
    else:
        message_text = rest

    ok = await reply(db, feedback, message_text)
    if not ok:
        await send_message(chat_id, copy["reply_failed"], parse_mode="HTML")
        return

    user_id_short = str(feedback.user_id)[:8]
    await send_message(
        chat_id,
        copy["reply_sent_ack"].format(user_id_short=user_id_short),
        parse_mode="HTML",
    )
