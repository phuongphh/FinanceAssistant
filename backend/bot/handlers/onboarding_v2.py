"""V2 onboarding handler — 3-step goal-based flow (Phase 4.1, A.1 + A.2 + C.1 + C.4).

Wired alongside the legacy ``backend.bot.handlers.onboarding`` so
existing users (created before this phase) are unaffected. New users
flagged via the feature toggle ``ONBOARDING_V2_ENABLED`` (default ON
for soft launch) go through this handler instead.

Flow:

  /start [invite_<token>?]
    └─ resolve invite → maybe founding banner
       └─ Step 1: goal question (3 buttons)
            └─ Step 2: first asset (free text OR demo button)
                 └─ Step 3: Twin compute → narrative → chart → feedback prompt
                      └─ completed
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.feedback.models.feedback import FEEDBACK_STATUS_NEW, Feedback
from backend.models.onboarding_session import (
    SIGNAL_CONFUSED,
    SIGNAL_DISLIKE,
    SIGNAL_LOVE,
    STEP_COMPLETED,
    STEP_FIRST_ASSET,
    STEP_GOAL_QUESTION,
    STEP_TRUST_PRIVACY,
    STEP_TWIN_SHOWN,
)
from backend.models.user import User
from backend.services import onboarding_service as legacy_onboarding_service
from backend.services.founding import founding_member_service
from backend.services.onboarding import data_quality_service, onboarding_service
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_message,
)
from backend.twin.services import twin_narrative_service_v2
from backend.wealth.services import asset_service

logger = logging.getLogger(__name__)

_TRUST_COPY_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "onboarding" / "trust_card.yaml"
)


def _load_trust_copy() -> dict[str, Any]:
    import yaml

    with open(_TRUST_COPY_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _trust_keyboard(copy: dict[str, Any]) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": copy["buttons"]["ok_label"],
                    "callback_data": copy["callbacks"]["ok"],
                }
            ],
            [
                {
                    "text": copy["buttons"]["question_label"],
                    "callback_data": copy["callbacks"]["question"],
                }
            ],
        ]
    }


def _quality_keyboard(value: Decimal) -> dict:
    rows = []
    for idx, (_, candidate) in enumerate(data_quality_service.estimate_options(value)):
        rows.append([{"text": f"✅ {format_money_short(candidate)}", "callback_data": f"onboarding_v2:asset_confirm:{idx}"}])
    rows.append([{"text": "✍️ Nhập lại", "callback_data": "onboarding_v2:asset_reenter"}])
    return {"inline_keyboard": rows}


# ---------- Feature toggle -------------------------------------------

FEATURE_FLAG_ENV = "ONBOARDING_V2_ENABLED"


def is_v2_enabled() -> bool:
    """V2 is enabled by default for soft launch. Operator can disable
    via env var if onboarding regresses post-deploy.
    """
    import os

    return os.environ.get(FEATURE_FLAG_ENV, "true").lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


# ---------- Entry: /start with optional invite token -----------------


async def handle_start(
    db: AsyncSession,
    chat_id: int,
    user: User,
    *,
    payload: str | None = None,
) -> None:
    """Route a /start command into the v2 onboarding flow.

    ``payload`` is whatever followed ``/start `` (Telegram deep-link
    payload). We support ``invite_<token>`` to redeem invite codes.
    """
    # Redeem invite (if any) BEFORE creating the session so the welcome
    # banner reflects founding-member status.
    founding_banner_text: str | None = None
    if payload and payload.startswith("invite_"):
        token = payload[len("invite_") :]
        founding_banner_text = await _redeem_invite(db, user, token)

    # Resume / start the session.
    session = await onboarding_service.start_or_resume(db, user.id)

    # Already done? Hand off to the menu without re-running onboarding.
    if session.current_step == STEP_COMPLETED:
        from backend.bot.handlers.menu_handler import cmd_menu

        name = user.display_name or "bạn"
        await send_message(chat_id, f"Chào lại {name}! 👋", parse_mode="HTML")
        await cmd_menu(db, chat_id, user)
        return

    # New session: send the welcome (with founding banner if applicable).
    if session.current_step == STEP_GOAL_QUESTION and session.goal_choice is None:
        if founding_banner_text:
            await send_message(chat_id, founding_banner_text, parse_mode="HTML")
        await _send_welcome_and_goal(db, chat_id, user)
        return

    # Mid-flow resume: drop them at the right step.
    await _resume_at(db, chat_id, user, session)


async def _redeem_invite(db: AsyncSession, user: User, token: str) -> str | None:
    """Look up invite token, atomically promote user to founding (if
    granted), return banner text to render (or None if no special copy).
    """
    invite = await founding_member_service.find_invite(db, token)
    if invite is None:
        return None
    if invite.redeemed_by_user_id is not None and invite.redeemed_by_user_id != user.id:
        # Already burned by someone else — treat as no-op (don't reveal).
        return None

    await founding_member_service.mark_invite_redeemed(db, invite, user)

    copy = onboarding_service.load_copy()
    # Source-aware copy prefix (if any).
    source_variants = copy.get("source_variants") or {}
    source_prefix: str | None = None
    if invite.source in source_variants:
        source_prefix = source_variants[invite.source].get("prefix")

    if not invite.grants_founding_status:
        return source_prefix

    # Try to assign founding sequence (race-safe).
    from backend.services.founding.founding_member_service import (
        FoundingCapReachedError,
    )

    try:
        assignment = await founding_member_service.assign_sequence(db, user)
    except FoundingCapReachedError:
        # Cohort full — still welcome them warmly with the cap_reached copy.
        founding_copy = _load_founding_copy()
        text = founding_copy["cap_reached"]
        return f"{source_prefix}\n\n{text}" if source_prefix else text

    founding_copy = _load_founding_copy()
    banner = founding_copy["banner"].format(sequence=assignment.sequence)
    analytics.track(
        "founding_member_activated",
        user_id=user.id,
        properties={"sequence": assignment.sequence, "source": invite.source},
    )
    return f"{source_prefix}\n\n{banner}" if source_prefix else banner


def _load_founding_copy() -> dict[str, Any]:
    from pathlib import Path

    import yaml

    path = (
        Path(__file__).resolve().parents[3]
        / "content"
        / "onboarding"
        / "founding_welcome.yaml"
    )
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------- Step 1 ----------------------------------------------------


async def _send_welcome_and_goal(db: AsyncSession, chat_id: int, user: User) -> None:
    copy = onboarding_service.load_copy()
    intro = copy["intro"]
    # Welcome bubble.
    await send_message(
        chat_id,
        intro["default"],
        parse_mode="HTML",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": intro["cta_label"],
                        "callback_data": intro["cta_callback"],
                    },
                ]
            ]
        },
    )
    analytics.track("onboarding_v2_started", user_id=user.id)


async def _send_goal_question(db: AsyncSession, chat_id: int, user: User) -> None:
    copy = onboarding_service.load_copy()
    step = copy["step_1_goal"]
    prefix = step["callback_prefix"]
    text = f"<b>{step['header']}</b>\n\n{step['body']}"
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": step["buttons"]["understand_wealth"],
                    "callback_data": f"{prefix}understand_wealth",
                }
            ],
            [
                {
                    "text": step["buttons"]["plan_goal"],
                    "callback_data": f"{prefix}plan_goal",
                }
            ],
            [
                {
                    "text": step["buttons"]["track_spending"],
                    "callback_data": f"{prefix}track_spending",
                }
            ],
        ]
    }
    await send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard)
    analytics.track("onboarding_v2_goal_asked", user_id=user.id)


async def _on_goal_picked(
    db: AsyncSession,
    chat_id: int,
    callback_id: str,
    message_id: int | None,
    user: User,
    goal_code: str,
) -> None:
    session = await onboarding_service.set_goal(db, user.id, goal_code)
    if session is None:
        await answer_callback(callback_id, text="Lựa chọn không hợp lệ")
        return
    await answer_callback(callback_id)

    copy = onboarding_service.load_copy()
    ack = copy["step_1_goal"]["goal_acks"].get(goal_code, "")
    if message_id is not None and ack:
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=ack,
                parse_mode="HTML",
                reply_markup={"inline_keyboard": []},
            )
        except Exception:
            logger.debug("edit on goal pick failed", exc_info=True)

    analytics.track(
        "onboarding_v2_goal_picked",
        user_id=user.id,
        properties={"goal": goal_code},
    )
    if session.current_step == STEP_TRUST_PRIVACY:
        await _send_trust_card(db, chat_id, user)
    else:
        await _send_first_asset_prompt(db, chat_id, user)


# ---------- Trust moment ---------------------------------------------


async def _send_trust_card(db: AsyncSession, chat_id: int, user: User) -> None:
    copy = _load_trust_copy()
    bullets = "\n".join(f"• {line}" for line in copy.get("bullets", []))
    text = f"<b>{copy['header']}</b>\n\n{copy['body']}\n\n{bullets}"
    await onboarding_service.mark_trust_shown(db, user.id)
    await send_message(chat_id, text, parse_mode="HTML", reply_markup=_trust_keyboard(copy))
    analytics.track("onboarding_trust_card_shown", user_id=user.id)


async def _on_trust_ok(db: AsyncSession, chat_id: int, callback_id: str, user: User) -> None:
    await onboarding_service.accept_trust(db, user.id)
    await answer_callback(callback_id, text="Cảm ơn bạn 💚")
    analytics.track("onboarding_trust_accepted", user_id=user.id)
    await _send_first_asset_prompt(db, chat_id, user)


async def _on_trust_question(db: AsyncSession, chat_id: int, callback_id: str, user: User) -> None:
    before = await onboarding_service.get_session(db, user.id)
    should_create_feedback = before is not None and before.trust_question_raised_at is None
    await onboarding_service.mark_trust_question_raised(db, user.id)
    if should_create_feedback:
        db.add(Feedback(
            user_id=user.id,
            content="[trust_question] User asked a question before entering assets",
            trigger="onboarding_trust_card",
            status=FEEDBACK_STATUS_NEW,
            priority="high",
        ))
    await db.flush()
    copy = _load_trust_copy()
    await answer_callback(callback_id, text="Đã ghi nhận")
    await send_message(chat_id, copy["question_ack"], parse_mode="HTML")
    analytics.track("onboarding_trust_question_raised", user_id=user.id)


# ---------- Step 2 ----------------------------------------------------


async def _send_first_asset_prompt(db: AsyncSession, chat_id: int, user: User) -> None:
    copy = onboarding_service.load_copy()
    step = copy["step_2_asset"]
    text = f"<b>{step['header']}</b>\n\n{step['body']}"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": step["demo_button"], "callback_data": step["demo_callback"]},
            ]
        ]
    }
    await send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard)


async def handle_asset_text_input(
    db: AsyncSession, chat_id: int, user: User, raw_text: str
) -> bool:
    """Consume free-text input while user is on step 2.

    Returns True if consumed (parser should not run the NL expense
    pipeline on this message).
    """
    session = await onboarding_service.get_session(db, user.id)
    if session is None or session.current_step != STEP_FIRST_ASSET:
        return False

    copy = onboarding_service.load_copy()
    step = copy["step_2_asset"]
    value = onboarding_service.parse_asset_amount(raw_text)
    if value is None:
        await send_message(chat_id, step["invalid"], parse_mode="HTML")
        return True
    if value < onboarding_service.MIN_ASSET_VND:
        await send_message(chat_id, step["too_small"], parse_mode="HTML")
        return True
    if value > onboarding_service.MAX_ASSET_VND:
        await send_message(chat_id, step["too_large"], parse_mode="HTML")
        return True

    warning = await data_quality_service.first_warning(
        db,
        user.id,
        asset_type="cash",
        amount_vnd=value,
        segment=session.inferred_wealth_segment,
    )
    if warning is not None:
        user.wizard_state = {
            "flow": "onboarding_asset_quality",
            "step": "confirm",
            "draft": {
                "value_vnd": str(value),
                "raw_text": raw_text[:500],
                "warning_type": warning.warning_type,
            },
        }
        await db.flush()
        await send_message(
            chat_id,
            f"⚠️ <b>Kiểm tra lại số tiền</b>\n\n{warning.message}\n\nBé Tiền hiểu là <b>{format_money_short(value)}</b>. Bạn chọn số đúng nhé:",
            parse_mode="HTML",
            reply_markup=_quality_keyboard(value),
        )
        analytics.track(
            "data_quality_warning_shown",
            user_id=user.id,
            properties={"warning_type": warning.warning_type, "surface": "onboarding"},
        )
        return True

    await _save_onboarding_first_asset(
        db, chat_id, user, value, raw_text=raw_text, warning_type=None, demo=False
    )
    return True



async def _save_onboarding_first_asset(
    db: AsyncSession,
    chat_id: int,
    user: User,
    value: Decimal,
    *,
    raw_text: str | None,
    warning_type: str | None,
    demo: bool,
) -> None:
    await asset_service.create_asset(
        db,
        user.id,
        asset_type="cash",
        subtype="onboarding_demo" if demo else "onboarding_first_asset",
        name="Twin demo" if demo else "Tài sản ban đầu",
        initial_value=value,
        current_value=value,
        is_placeholder_asset=demo,
        is_confirmed=True,
        source_input_raw=raw_text,
        data_quality_warning_type=warning_type,
    )
    await onboarding_service.set_first_asset(db, user.id, value, demo=demo)
    user.wizard_state = None
    await db.flush()
    analytics.track(
        "onboarding_v2_asset_captured",
        user_id=user.id,
        properties={
            "value_vnd_bucket": _bucket_label(value),
            "demo": demo,
            "warning_type": warning_type,
        },
    )

    name = user.display_name or "bạn"
    await send_message(
        chat_id,
        f"✅ Bé Tiền ghi nhận: <b>{format_money_short(value)}</b>. Đang vẽ Twin cho bạn — chờ chút nhé {name}…",
        parse_mode="HTML",
    )
    await _trigger_first_twin(db, chat_id, user)


def _bucket_label(value: Decimal) -> str:
    # Round to nearest order of magnitude for analytics, NOT for storage.
    if value < Decimal("100_000_000"):
        return "<100tr"
    if value < Decimal("500_000_000"):
        return "100-500tr"
    if value < Decimal("5_000_000_000"):
        return "500tr-5ty"
    return ">5ty"


async def _on_demo_pressed(
    db: AsyncSession, chat_id: int, callback_id: str, user: User
) -> None:
    await answer_callback(callback_id)
    session = await onboarding_service.get_session(db, user.id)
    if session is None:
        return
    copy = onboarding_service.load_copy()
    banner = copy["demo_banner"]
    keyboard = {
        "inline_keyboard": [
            [
                {"text": banner["cta_label"], "callback_data": banner["cta_callback"]},
            ]
        ]
    }
    await send_message(
        chat_id, banner["body"], parse_mode="HTML", reply_markup=keyboard
    )
    analytics.track("onboarding_v2_demo_chosen", user_id=user.id)
    await _save_onboarding_first_asset(
        db,
        chat_id,
        user,
        onboarding_service.DEMO_ASSET_VND,
        raw_text="demo",
        warning_type=None,
        demo=True,
    )


async def _on_exit_demo(
    db: AsyncSession, chat_id: int, callback_id: str, user: User
) -> None:
    """User tapped 'Xem Twin của tôi' after seeing the demo. Re-prompt
    for real first-asset input.
    """
    await answer_callback(callback_id)
    # Reset back to first_asset step so text input triggers real Twin.
    session = await onboarding_service.get_session(db, user.id)
    if session is None:
        return
    session.current_step = STEP_FIRST_ASSET
    session.demo_mode_used = True  # keep the analytics marker
    session.first_asset_value_vnd = None
    await db.flush()
    await _send_first_asset_prompt(db, chat_id, user)



async def _on_asset_quality_confirm(
    db: AsyncSession,
    chat_id: int,
    callback_id: str,
    message_id: int | None,
    user: User,
    option_index: str,
) -> None:
    state = user.wizard_state or {}
    if state.get("flow") != "onboarding_asset_quality":
        await answer_callback(callback_id, text="Không còn yêu cầu xác nhận")
        return
    draft = state.get("draft") or {}
    try:
        original = Decimal(str(draft.get("value_vnd")))
        idx = int(option_index)
        value = data_quality_service.estimate_options(original)[idx][1]
    except Exception:
        await answer_callback(callback_id, text="Lựa chọn không hợp lệ", show_alert=True)
        return
    if message_id is not None:
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"✅ Đã xác nhận: <b>{format_money_short(value)}</b>",
                parse_mode="HTML",
                reply_markup={"inline_keyboard": []},
            )
        except Exception:
            logger.debug("edit quality confirm failed", exc_info=True)
    await answer_callback(callback_id)
    await _save_onboarding_first_asset(
        db,
        chat_id,
        user,
        value,
        raw_text=draft.get("raw_text"),
        warning_type=draft.get("warning_type"),
        demo=False,
    )


async def _on_asset_quality_reenter(
    db: AsyncSession, chat_id: int, callback_id: str, user: User
) -> None:
    user.wizard_state = None
    await db.flush()
    await answer_callback(callback_id)
    await _send_first_asset_prompt(db, chat_id, user)


# ---------- Step 3 ----------------------------------------------------


async def _trigger_first_twin(db: AsyncSession, chat_id: int, user: User) -> None:
    """Compute Twin and push narrative → chart → feedback prompt.

    Twin compute can fail (no assets after demo, market data fetch
    error, etc.); we surface a friendly fallback and let the resume
    worker re-engage the user later.
    """
    from backend.twin.services import twin_chart_service, twin_projection_service

    # Narrative FIRST — sets context before the chart shows up.
    await send_message(
        chat_id, twin_narrative_service_v2.narrative_text(), parse_mode="HTML"
    )

    try:
        projections = await twin_projection_service.compute_and_store(
            db, user.id, scenario="current"
        )
    except Exception:
        logger.exception("First-Twin compute failed for user %s", user.id)
        await send_message(
            chat_id,
            twin_narrative_service_v2.compute_failed_text(),
            parse_mode="HTML",
        )
        # Do NOT mark twin_shown_at; leave for resume worker.
        return

    if not projections:
        await send_message(
            chat_id,
            twin_narrative_service_v2.compute_failed_text(),
            parse_mode="HTML",
        )
        return

    proj = projections[0]
    try:
        png = twin_chart_service.render_projection_chart(proj.cone_data)
    except Exception:
        logger.exception("Twin chart render failed for user %s", user.id)
        await send_message(
            chat_id,
            twin_narrative_service_v2.compute_failed_text(),
            parse_mode="HTML",
        )
        return

    name = user.display_name or "bạn"
    caption = twin_narrative_service_v2.chart_caption(
        name=name, horizon_years=proj.horizon_years
    )

    from backend.ports.notifier import get_notifier

    notifier = get_notifier()
    await notifier.send_photo(
        chat_id=chat_id, photo=png, caption=caption, parse_mode="HTML"
    )

    await onboarding_service.mark_twin_shown(db, user.id)
    analytics.track(
        "onboarding_v2_twin_shown",
        user_id=user.id,
        properties={
            "demo": (await onboarding_service.get_session(db, user.id)).demo_mode_used
        },
    )

    # Schedule the in-moment feedback prompt 7s later in a fire-and-forget
    # task. We capture the chat_id + user_id only (no DB session, no model
    # — those don't survive the worker boundary).
    asyncio.create_task(
        _send_feedback_prompt_after_delay(chat_id=chat_id, user_id=user.id, delay=7.0)
    )


async def _send_feedback_prompt_after_delay(
    *, chat_id: int, user_id, delay: float
) -> None:
    try:
        await asyncio.sleep(delay)
        from backend.ports.notifier import get_notifier

        notifier = get_notifier()
        await notifier.send_message(
            chat_id,
            twin_narrative_service_v2.feedback_prompt_text(),
            reply_markup=twin_narrative_service_v2.feedback_keyboard(),
        )
    except Exception:
        logger.exception("Failed to send feedback prompt to %s", user_id)


# ---------- Feedback signal -------------------------------------------


async def _on_feedback_signal(
    db: AsyncSession,
    chat_id: int,
    callback_id: str,
    message_id: int | None,
    user: User,
    signal: str,
) -> None:
    if signal not in (SIGNAL_LOVE, SIGNAL_CONFUSED, SIGNAL_DISLIKE):
        await answer_callback(callback_id)
        return

    await onboarding_service.record_feedback_signal(db, user.id, signal)

    # Persist as a Feedback row too so /feedback_inbox sees it alongside
    # explicit feedback — the operator triages all signals in one place.
    from backend.feedback.models.feedback import (
        FEEDBACK_STATUS_NEW,
        Feedback,
    )

    fb = Feedback(
        user_id=user.id,
        content=f"[onboarding_signal:{signal}]",
        trigger="onboarding_v2_in_moment",
        status=FEEDBACK_STATUS_NEW,
        onboarding_emoji_signal=signal,
    )
    db.add(fb)
    await db.flush()

    await answer_callback(callback_id, text="💚")
    if message_id is not None:
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=twin_narrative_service_v2.feedback_ack_text(),
                parse_mode="HTML",
                reply_markup={"inline_keyboard": []},
            )
        except Exception:
            await send_message(
                chat_id,
                twin_narrative_service_v2.feedback_ack_text(),
                parse_mode="HTML",
            )

    analytics.track(
        "onboarding_v2_feedback_signal",
        user_id=user.id,
        properties={"signal": signal},
    )
    await _complete(db, chat_id, user)


async def _complete(db: AsyncSession, chat_id: int, user: User) -> None:
    session = await onboarding_service.get_session(db, user.id)
    if session is None or session.current_step == STEP_COMPLETED:
        return
    await onboarding_service.mark_completed(db, user.id)

    # Mirror onto legacy ``users.onboarding_step`` so the rest of the
    # codebase (briefing eligibility, /menu greeting, etc.) sees an
    # onboarded user without needing a parallel branch.
    await legacy_onboarding_service.mark_completed(db, user.id)

    await send_message(
        chat_id, twin_narrative_service_v2.completion_text(), parse_mode="HTML"
    )
    analytics.track(
        "onboarding_v2_completed",
        user_id=user.id,
        properties={
            "goal": session.goal_choice,
            "segment": session.inferred_wealth_segment,
            "demo_used": session.demo_mode_used,
            "duration_s": int(
                (
                    datetime.now(timezone.utc)
                    - session.started_at.replace(tzinfo=timezone.utc)
                ).total_seconds()
            )
            if session.started_at
            else None,
        },
    )


# ---------- Resume ---------------------------------------------------


async def _resume_at(db: AsyncSession, chat_id: int, user: User, session) -> None:
    if session.current_step == STEP_GOAL_QUESTION:
        await _send_goal_question(db, chat_id, user)
    elif session.current_step == STEP_TRUST_PRIVACY:
        await _send_trust_card(db, chat_id, user)
    elif session.current_step == STEP_FIRST_ASSET:
        await _send_first_asset_prompt(db, chat_id, user)
    elif session.current_step == STEP_TWIN_SHOWN:
        # Twin already shown — just complete (feedback is optional).
        await _complete(db, chat_id, user)


# ---------- Callback router ------------------------------------------


async def handle_callback(db: AsyncSession, callback_query: dict) -> bool:
    """Route any ``onboarding_v2:*`` callback. Return True if handled."""
    data: str = callback_query.get("data", "")
    if not data.startswith("onboarding_v2:"):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    telegram_from = callback_query.get("from") or {}
    telegram_id = telegram_from.get("id")

    if chat_id is None or telegram_id is None:
        return False

    from backend.services.dashboard_service import get_user_by_telegram_id

    user = await get_user_by_telegram_id(db, telegram_id)
    if not user:
        await answer_callback(callback_id, text="Người dùng không tìm thấy")
        return True

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "start":
        await answer_callback(callback_id)
        if message_id is not None:
            try:
                await edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Bắt đầu nào ✨",
                    parse_mode="HTML",
                    reply_markup={"inline_keyboard": []},
                )
            except Exception:
                pass
        await _send_goal_question(db, chat_id, user)
        return True

    if action == "goal" and len(parts) >= 3:
        await _on_goal_picked(db, chat_id, callback_id, message_id, user, parts[2])
        return True

    if action == "trust_ok":
        await _on_trust_ok(db, chat_id, callback_id, user)
        return True

    if action == "trust_question":
        await _on_trust_question(db, chat_id, callback_id, user)
        return True

    if action == "asset_confirm" and len(parts) >= 3:
        await _on_asset_quality_confirm(db, chat_id, callback_id, message_id, user, parts[2])
        return True

    if action == "asset_reenter":
        await _on_asset_quality_reenter(db, chat_id, callback_id, user)
        return True

    if action == "demo":
        await _on_demo_pressed(db, chat_id, callback_id, user)
        return True

    if action == "exit_demo":
        await _on_exit_demo(db, chat_id, callback_id, user)
        return True

    if action == "resume":
        await answer_callback(callback_id)
        session = await onboarding_service.get_session(db, user.id)
        if session is not None:
            await _resume_at(db, chat_id, user, session)
        return True

    if action == "fb" and len(parts) >= 3:
        await _on_feedback_signal(db, chat_id, callback_id, message_id, user, parts[2])
        return True

    await answer_callback(callback_id)
    return True
