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
from backend.services import reading_service
from backend.services.onboarding import (
    data_quality_service,
    next_action_service,
    onboarding_service,
)
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
            ]
        ]
    }


def _quality_keyboard(value: Decimal) -> dict:
    rows = []
    for idx, (_, candidate) in enumerate(data_quality_service.estimate_options(value)):
        rows.append(
            [
                {
                    "text": f"✅ {format_money_short(candidate)}",
                    "callback_data": f"onboarding_v2:asset_confirm:{idx}",
                }
            ]
        )
    rows.append(
        [{"text": "✍️ Nhập lại", "callback_data": "onboarding_v2:asset_reenter"}]
    )
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


READING_FLAG_ENV = "READING_ENABLED"


def is_reading_enabled() -> bool:
    """The Reading (WOW #1) is on by default; operator can disable via env
    if the minute-1 LLM beat regresses. Read here at the handler edge
    (never in ``reading_service``) per the layer contract — same pattern
    as ``is_v2_enabled``.
    """
    import os

    return os.environ.get(READING_FLAG_ENV, "true").lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


SCREENSHOT_ONBOARDING_FLAG_ENV = "SCREENSHOT_ONBOARDING_ENABLED"


def is_screenshot_onboarding_enabled() -> bool:
    """Screenshot onboarding (Phase 4.4 Epic 2, P2) is OFF by default.

    When a user is on the first-asset step they can paste a screenshot of
    their bank/wallet balance instead of typing the number. This is a
    cuttable nicety, so it ships dark — operator flips it on once the
    balance-OCR path is validated in prod. The flag is consulted at the
    worker edge (photo routing) and here for the prompt hint; the env read
    never reaches a service (layer contract), same pattern as
    ``is_reading_enabled``.
    """
    import os

    return os.environ.get(SCREENSHOT_ONBOARDING_FLAG_ENV, "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
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


async def _send_name_prompt(chat_id: int) -> None:
    await send_message(
        chat_id,
        "Trước tiên, Bé Tiền muốn gọi bạn là gì? ✨\n\n"
        "(Bạn chỉ cần nhắn tên bạn vào đây)",
        parse_mode="HTML",
    )


async def handle_name_text_input(
    db: AsyncSession, chat_id: int, user: User, raw_text: str
) -> bool:
    """Consume free-text name input at the start of V2 onboarding."""
    session = await onboarding_service.get_session(db, user.id)
    if (
        session is None
        or session.current_step != STEP_GOAL_QUESTION
        or session.goal_choice is not None
    ):
        return False

    is_valid, name = legacy_onboarding_service.validate_display_name(raw_text)
    if not is_valid:
        await send_message(
            chat_id,
            "Tên chưa hợp lệ nè 💚 Bạn nhập tên ngắn gọn (tối đa 24 ký tự) nhé.",
            parse_mode="HTML",
        )
        return True

    await legacy_onboarding_service.set_display_name(db, user.id, name)
    user.display_name = name
    await db.flush()

    await send_message(
        chat_id,
        f"Chào {name} 👋 Mình hỏi nhanh 1 câu để cá nhân hoá nhé:",
        parse_mode="HTML",
    )
    await _send_salutation_question(db, chat_id, user)
    analytics.track("onboarding_v2_name_captured", user_id=user.id)
    return True


async def _send_salutation_question(db: AsyncSession, chat_id: int, user: User) -> None:
    copy = onboarding_service.load_copy()
    step = copy["step_salutation"]
    prefix = step["callback_prefix"]
    text = f"<b>{step['header']}</b>\n\n{step['body']}"
    keyboard = {
        "inline_keyboard": [
            [{"text": step["buttons"]["anh"], "callback_data": f"{prefix}anh"}],
            [{"text": step["buttons"]["chị"], "callback_data": f"{prefix}chị"}],
            [{"text": step["buttons"]["bạn"], "callback_data": f"{prefix}bạn"}],
        ]
    }
    await send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard)
    analytics.track("onboarding_v2_salutation_asked", user_id=user.id)


async def _on_salutation_picked(
    db: AsyncSession,
    chat_id: int,
    callback_id: str,
    message_id: int | None,
    user: User,
    salutation: str,
) -> None:
    updated = await onboarding_service.set_salutation(db, user.id, salutation)
    if updated is None:
        await answer_callback(callback_id, text="Lựa chọn không hợp lệ")
        return
    await answer_callback(callback_id)

    copy = onboarding_service.load_copy()
    ack = copy["step_salutation"]["acks"].get(salutation, "")
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
            logger.debug("edit on salutation pick failed", exc_info=True)

    analytics.track(
        "onboarding_v2_salutation_picked",
        user_id=user.id,
        properties={"salutation": salutation},
    )
    await _send_goal_question(db, chat_id, user)


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

    # The Reading v0 (WOW #1): a warm, zero-data "đoán thử" right after
    # the goal pick, before we ask for the first number. Flag-gated at the
    # handler edge; the service guarantees a renderable string so this can
    # never block the flow. We always fall through to the next step.
    if is_reading_enabled():
        await _send_reading(db, chat_id, user, goal_code=goal_code)

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
    await send_message(
        chat_id, text, parse_mode="HTML", reply_markup=_trust_keyboard(copy)
    )
    analytics.track("onboarding_trust_card_shown", user_id=user.id)


async def _on_trust_ok(
    db: AsyncSession, chat_id: int, callback_id: str, user: User
) -> None:
    await onboarding_service.accept_trust(db, user.id)
    await answer_callback(callback_id, text="Cảm ơn bạn 💚")
    analytics.track("onboarding_trust_accepted", user_id=user.id)
    await _send_first_asset_prompt(db, chat_id, user)


# ---------- Step 2 ----------------------------------------------------


async def _send_first_asset_prompt(db: AsyncSession, chat_id: int, user: User) -> None:
    copy = onboarding_service.load_copy()
    step = copy["step_2_asset"]
    body = step["body"]
    # Only advertise the screenshot path when the feature is live, so the
    # hint never promises something the worker won't act on.
    if is_screenshot_onboarding_enabled() and step.get("screenshot_hint"):
        body = f"{body}\n\n{step['screenshot_hint']}"
    text = f"<b>{step['header']}</b>\n\n{body}"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": step["demo_button"], "callback_data": step["demo_callback"]},
            ]
        ]
    }
    await send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard)


async def handle_first_asset_screenshot(
    db: AsyncSession, message: dict, user: User
) -> bool:
    """Read a balance screenshot as the user's first asset (Epic 2).

    Returns ``True`` when the message is consumed — which, once the user
    is on the first-asset step, is *any* photo: a screenshot there is
    meant as a balance, so on OCR failure we nudge them to type the
    number rather than letting the receipt-expense path mis-handle it.
    Returns ``False`` only when the user is NOT on the first-asset step,
    so the caller falls through to the receipt OCR handler.

    The ``SCREENSHOT_ONBOARDING_ENABLED`` flag is checked by the caller
    (worker edge), not here.
    """
    session = await onboarding_service.get_session(db, user.id)
    if session is None or session.current_step != STEP_FIRST_ASSET:
        return False

    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return False

    from backend.bot.handlers.photo_receipt import (
        _MAX_IMAGE_BYTES,
        _extract_message_id,
        _select_photo,
    )
    from backend.services.ocr_service import parse_balance_screenshot
    from backend.services.telegram_service import download_file

    copy = onboarding_service.load_copy()
    step = copy["step_2_asset"]

    photos = message.get("photo") or []
    document = message.get("document") or {}
    doc_is_image = isinstance(document.get("mime_type"), str) and document[
        "mime_type"
    ].startswith("image/")
    if not photos and not doc_is_image:
        return False

    if photos:
        chosen = _select_photo(photos)
        if not chosen:
            return False
        file_id = chosen.get("file_id")
        mime_type = "image/jpeg"
    else:
        file_id = document.get("file_id")
        mime_type = document.get("mime_type") or "image/jpeg"
    if not file_id:
        return False

    ack = await send_message(chat_id, step["screenshot_reading"], parse_mode="HTML")
    ack_id = _extract_message_id(ack)

    async def _finish(text: str, *, keyboard: dict | None = None) -> None:
        if ack_id is not None and keyboard is None:
            try:
                await edit_message_text(
                    chat_id=chat_id, message_id=ack_id, text=text, parse_mode="HTML"
                )
                return
            except Exception:
                logger.debug("balance ack edit failed; sending fresh", exc_info=True)
        await send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard)

    image_bytes = await download_file(file_id)
    if not image_bytes or len(image_bytes) > _MAX_IMAGE_BYTES:
        await _finish(step["screenshot_failed"])
        return True

    try:
        result = await parse_balance_screenshot(
            image_bytes, mime_type, db=db, user_id=user.id
        )
    except ValueError as exc:
        logger.warning("balance screenshot OCR failed: %s", exc)
        await _finish(step["screenshot_failed"])
        return True

    raw_balance = result.get("total_balance")
    if result.get("error") == "not_a_balance" or raw_balance is None:
        await _finish(step["screenshot_not_balance"])
        analytics.track(
            "onboarding_v2_screenshot_no_balance",
            user_id=user.id,
            properties={"confidence": result.get("confidence")},
        )
        return True

    try:
        value = Decimal(str(raw_balance))
    except (ValueError, ArithmeticError):
        await _finish(step["screenshot_failed"])
        return True

    if value < onboarding_service.MIN_ASSET_VND:
        await _finish(step["too_small"])
        return True
    if value > onboarding_service.MAX_ASSET_VND:
        await _finish(step["too_large"])
        return True

    analytics.track(
        "onboarding_v2_screenshot_balance_read",
        user_id=user.id,
        properties={
            "value_vnd_bucket": _bucket_label(value),
            "confidence": result.get("confidence"),
        },
    )

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
                "raw_text": f"[screenshot] {result.get('account_label') or ''}"[:500],
                "warning_type": warning.warning_type,
            },
        }
        await db.flush()
        await _finish(
            step["screenshot_quality_warning"].format(
                warning=warning.message, amount=format_money_short(value)
            ),
            keyboard=_quality_keyboard(value),
        )
        analytics.track(
            "data_quality_warning_shown",
            user_id=user.id,
            properties={
                "warning_type": warning.warning_type,
                "surface": "onboarding_screenshot",
            },
        )
        return True

    await _save_onboarding_first_asset(
        db,
        chat_id,
        user,
        value,
        raw_text=f"[screenshot] {result.get('account_label') or ''}",
        warning_type=None,
        demo=False,
    )
    return True


# ---------- The Reading (Phase 4.4 Epic 1, WOW #1) -------------------


async def _send_reading(
    db: AsyncSession,
    chat_id: int,
    user: User,
    *,
    goal_code: str | None,
    amount_text: str | None = None,
) -> None:
    """Send The Reading. v0 = zero data (no amount); v1 = real number.

    Sends an instant "đang đoán…" placeholder, then edits it in place
    with the composed Reading once the (Groq, sub-second) LLM returns.
    The ``READING_ENABLED`` flag is checked by the caller, not here. The
    service guarantees a renderable string even on LLM failure, so this
    never blocks the onboarding beat.
    """
    copy = onboarding_service.load_copy()["reading"]
    salutation = onboarding_service.salutation_of(user)
    fmt = {"salutation": salutation, "Salutation": salutation.capitalize()}

    message_id = None
    try:
        resp = await send_message(
            chat_id, copy["placeholder"].format(**fmt), parse_mode="HTML"
        )
        message_id = (resp.get("result") or {}).get("message_id") if resp else None
    except Exception:
        logger.debug("reading placeholder send failed", exc_info=True)

    text = await reading_service.generate_reading(
        db=db,
        user_id=user.id,
        salutation=salutation,
        display_name=user.display_name or "",
        goal_label=reading_service.goal_label_for(goal_code),
        amount_text=amount_text,
    )

    if message_id is not None:
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
            )
            return
        except Exception:
            logger.debug("reading edit failed; sending fresh", exc_info=True)
    await send_message(chat_id, text, parse_mode="HTML")


def _step3_header_text(*, demo: bool) -> str:
    copy = onboarding_service.load_copy()
    header = (
        (copy.get("step_3_twin") or {}).get("header") or "(3/3) Twin đầu tiên"
    ).strip()
    if demo:
        return f"<b>{header}</b>\n\n🎭 Dưới đây là bản demo để bạn hình dung trước."
    return f"<b>{header}</b>"


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
        suppress_twin_event=demo,
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

    # Demo gets its own ack so the user doesn't read "Bé Tiền ghi nhận: 50tr"
    # and think we banked their cash. Real input keeps the personal phrasing.
    if demo:
        await send_message(
            chat_id, twin_narrative_service_v2.demo_ack_text(), parse_mode="HTML"
        )
    else:
        name = user.display_name or "bạn"
        await send_message(
            chat_id,
            f"✅ Bé Tiền ghi nhận: <b>{format_money_short(value)}</b>. Đang vẽ Twin cho bạn — chờ chút nhé {name}…",
            parse_mode="HTML",
        )

    # The Reading v1 (WOW #1, real-number pass): re-read with the actual
    # asset so the guess feels earned, then bridge into the Twin. Demo
    # never gets a Reading — the 50tr placeholder isn't the user's number,
    # so a personalized guess off it would read as a lie. Flag-gated at the
    # handler edge; failure-safe via the service fallback.
    if not demo and is_reading_enabled():
        session = await onboarding_service.get_session(db, user.id)
        goal_code = session.goal_choice if session is not None else None
        await _send_reading(
            db,
            chat_id,
            user,
            goal_code=goal_code,
            amount_text=format_money_short(value),
        )

    await _trigger_first_twin(db, chat_id, user, demo=demo)


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


async def _on_retry_twin(
    db: AsyncSession, chat_id: int, callback_id: str, user: User
) -> None:
    """User tapped the 🔄 Thử lại button after a compute_failed message.

    Re-derives demo vs real from the session (the user may have already
    pressed demo) and re-runs the Twin pipeline. Safe to call repeatedly:
    the demo path is idempotent, and the real path re-inserts a fresh
    ``TwinProjection`` row.
    """
    await answer_callback(callback_id)
    session = await onboarding_service.get_session(db, user.id)
    if session is None:
        return
    # Nothing to recompute if the user never picked an asset/demo value.
    if session.first_asset_value_vnd is None:
        await _send_first_asset_prompt(db, chat_id, user)
        return
    demo = bool(session.demo_mode_used)
    analytics.track(
        "onboarding_v2_twin_retry", user_id=user.id, properties={"demo": demo}
    )
    await _trigger_first_twin(db, chat_id, user, demo=demo)


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
        await answer_callback(
            callback_id, text="Lựa chọn không hợp lệ", show_alert=True
        )
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


async def _trigger_first_twin(
    db: AsyncSession, chat_id: int, user: User, *, demo: bool = False
) -> None:
    """Compute Twin and push narrative → chart → feedback prompt.

    Demo flow uses a deterministic precomputed cone (no DB writes, no
    upstream reads) so it ALWAYS succeeds — the demo Twin is the user's
    first product moment and it cannot fail. Real flow runs the full
    Monte Carlo and persists a ``TwinProjection`` row.

    On failure the user gets a clear ⚠️ message with a retry button —
    we never promise a phantom "1-minute" background recompute that
    doesn't exist.
    """
    from backend.twin.services import twin_chart_service

    cone_data, horizon_years = await _resolve_twin_cone(db, user, demo=demo)
    if cone_data is None:
        await _send_twin_compute_failed(chat_id)
        # Do NOT mark twin_shown_at; the retry button drives recovery.
        return

    await send_message(
        chat_id,
        _step3_header_text(demo=demo),
        parse_mode="HTML",
    )

    # Narrative after successful compute resolution so users never read
    # Twin-copy when compute actually failed (prevents UX contradiction).
    salutation = onboarding_service.salutation_of(user)
    await send_message(
        chat_id,
        twin_narrative_service_v2.narrative_text(demo=demo, salutation=salutation),
        parse_mode="HTML",
    )

    try:
        png = twin_chart_service.render_projection_chart(cone_data)
    except Exception:
        logger.exception("Twin chart render failed for user %s", user.id)
        await _send_twin_compute_failed(chat_id)
        return

    name = user.display_name or "bạn"
    caption = twin_narrative_service_v2.chart_caption(
        name=name, horizon_years=horizon_years, demo=demo
    )

    from backend.ports.notifier import get_notifier

    notifier = get_notifier()
    await notifier.send_photo(
        chat_id=chat_id, photo=png, caption=caption, parse_mode="HTML"
    )

    # Demo path only: reframe the chart so the user doesn't anchor on the
    # thin 2-asset demo allocation. The real Twin will look better — say so.
    if demo:
        await send_message(
            chat_id,
            twin_narrative_service_v2.demo_post_chart_emphasis_text(),
            parse_mode="HTML",
        )

    await onboarding_service.mark_twin_shown(db, user.id)
    analytics.track(
        "onboarding_v2_twin_shown",
        user_id=user.id,
        properties={"demo": demo},
    )

    # Schedule the in-moment feedback prompt 7s later in a fire-and-forget
    # task. We capture the chat_id + user_id only (no DB session, no model
    # — those don't survive the worker boundary).
    asyncio.create_task(
        _send_feedback_prompt_after_delay(chat_id=chat_id, user_id=user.id, delay=7.0)
    )


async def _resolve_twin_cone(
    db: AsyncSession, user: User, *, demo: bool
) -> tuple[list[dict[str, Any]] | None, int]:
    """Return (cone_data, horizon_years) or (None, 0) if compute failed.

    Demo flow short-circuits to the precomputed/cached cone — the demo
    is identical for every user so we never hit the DB and never let
    a transient upstream flake break the first product moment.
    """
    if demo:
        from backend.twin.services import demo_twin_service

        return (
            demo_twin_service.compute_demo_cone(),
            demo_twin_service.demo_horizon_years(),
        )

    from backend.twin.services import twin_projection_service

    try:
        projections = await twin_projection_service.compute_and_store(
            db, user.id, scenario="current"
        )
    except Exception:
        logger.exception("First-Twin compute failed for user %s", user.id)
        return None, 0
    if not projections:
        logger.warning("First-Twin compute returned no rows for user %s", user.id)
        return None, 0
    proj = projections[0]
    return proj.cone_data, proj.horizon_years


async def _send_twin_compute_failed(chat_id: int) -> None:
    await send_message(
        chat_id,
        twin_narrative_service_v2.compute_failed_text(),
        parse_mode="HTML",
        reply_markup=twin_narrative_service_v2.compute_failed_keyboard(),
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
    # Silently finalize the session before the CTA so /menu, briefing
    # eligibility, etc. light up immediately — but DO NOT send the
    # "Xong! Bé Tiền và bạn chính thức đồng hành" message yet. That
    # message fires only after the user takes the first next-best-action
    # (tap CTA button OR free-text a question); otherwise it lands
    # before the user has actually done anything and reads as premature.
    await _finalize_session_silently(db, user)
    await _send_next_best_action(db, chat_id, user)


async def _finalize_session_silently(db: AsyncSession, user: User) -> None:
    """Mark the session COMPLETED without sending the activation bubble.

    Separated from ``_send_activation_message_if_first_engagement`` so the
    DB state machine can advance to COMPLETED (legacy ``users.onboarding_step``
    mirror included) without the user-facing message. The visible "we're
    officially in this together" message is gated on engagement — see
    ``_send_activation_message_if_first_engagement``.
    """
    session = await onboarding_service.get_session(db, user.id)
    if session is None or session.current_step == STEP_COMPLETED:
        return
    await onboarding_service.mark_completed(db, user.id)

    # Mirror onto legacy ``users.onboarding_step`` so the rest of the
    # codebase (briefing eligibility, /menu greeting, etc.) sees an
    # onboarded user without needing a parallel branch.
    await legacy_onboarding_service.mark_completed(db, user.id)

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


async def _send_activation_message_if_first_engagement(
    db: AsyncSession, chat_id: int, user: User
) -> bool:
    """Send the "🎉 Xong! Bé Tiền và bạn chính thức đồng hành…" bubble
    exactly once, on the user's first post-Twin engagement.

    Gating signal: ``OnboardingSession.next_best_action_taken``. If it is
    None at the start of the call, the user has not yet engaged → this
    IS their first engagement → send the message. Both call sites
    (button tap and free-text query) invoke this BEFORE ``mark_taken``
    so the gate fires reliably.

    Returns True if the message was sent, False otherwise. Safe to call
    when the session is missing or not yet finalized — those branches
    no-op silently.
    """
    session = await onboarding_service.get_session(db, user.id)
    if session is None:
        return False
    if session.next_best_action_taken is not None:
        return False
    if session.current_step != STEP_COMPLETED:
        # Finalization hasn't run yet (e.g., user typed a question before
        # tapping any feedback). Don't show the activation bubble until
        # the session is actually complete — that would lie about state.
        return False
    await send_message(
        chat_id, twin_narrative_service_v2.completion_text(), parse_mode="HTML"
    )
    return True


async def _send_next_best_action(db: AsyncSession, chat_id: int, user: User) -> None:
    """Insert the personalized CTA before the morning-briefing promise."""
    cta = await next_action_service.compute(db, user.id)
    await send_message(
        chat_id,
        cta.message_text,
        parse_mode="HTML",
        reply_markup=cta.reply_markup,
    )
    analytics.track(
        "next_best_action_shown",
        user_id=user.id,
        properties={
            "asset_state": cta.asset_state,
            "goal": cta.goal,
            "button_key": cta.button_key,
        },
    )


async def maybe_mark_query_next_action(
    db: AsyncSession, chat_id: int | None, user: User
) -> None:
    """Mark free-text after first Twin as query-first activation.

    ``chat_id`` may be None when the caller has no chat context (unusual
    but defensive); in that case the activation message is skipped — the
    user will see it on their next button tap.
    """
    session = await onboarding_service.get_session(db, user.id)
    if (
        session is None
        or session.first_twin_shown_at is None
        or session.next_best_action_taken is not None
    ):
        return
    # First post-Twin engagement via free text → show the activation
    # bubble BEFORE marking taken so the gate inside the helper still
    # sees ``next_best_action_taken is None``.
    if chat_id is not None:
        await _send_activation_message_if_first_engagement(db, chat_id, user)
    await next_action_service.mark_taken(
        db, user.id, next_action_service.ACTION_ASKED_QUERY
    )
    analytics.track(
        "next_best_action_taken",
        user_id=user.id,
        properties={"action_type": next_action_service.ACTION_ASKED_QUERY},
    )


async def handle_next_action_callback(db: AsyncSession, callback_query: dict) -> bool:
    """Route ``next_action:*`` shortcut buttons."""
    data = callback_query.get("data") or ""
    if not data.startswith("next_action:"):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    telegram_id = (callback_query.get("from") or {}).get("id")
    if chat_id is None or telegram_id is None:
        await answer_callback(callback_id)
        return True

    from backend.services.dashboard_service import get_user_by_telegram_id

    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None:
        await answer_callback(callback_id, text="Gõ /start để bắt đầu nhé")
        return True

    action = data.split(":", 1)[1]
    action_type = next_action_service.action_type_for_callback(data) or action
    # Show the warm "we're officially in this together" bubble BEFORE
    # marking the action taken — the helper gates on
    # ``next_best_action_taken IS NULL`` to ensure single-fire, so order
    # matters here. If the user already engaged via free-text the helper
    # is a no-op.
    await _send_activation_message_if_first_engagement(db, chat_id, user)
    await next_action_service.mark_taken(db, user.id, action_type)
    analytics.track(
        "next_best_action_taken",
        user_id=user.id,
        properties={"action_type": action_type, "button_key": action},
    )
    await answer_callback(callback_id, text="Bắt đầu nhé 💚")

    if action == "add_asset":
        from backend.bot.handlers.asset_entry import start_asset_wizard

        await start_asset_wizard(db, chat_id, user)
    elif action == "add_income":
        from backend.bot.handlers.income_entry import start_income_wizard

        await start_income_wizard(db, chat_id, user)
    elif action == "set_goal":
        from backend.bot.handlers.goal_entry import start_goals_wizard

        await start_goals_wizard(db, chat_id, user)
    elif action == "log_expense":
        await send_message(
            chat_id,
            "🧾 Gõ khoản chi đầu tiên, ví dụ: <code>ăn trưa 80k</code>",
            parse_mode="HTML",
        )
    else:
        await send_message(chat_id, "Gõ /menu để chọn bước tiếp theo nhé.")
    return True


# ---------- Resume ---------------------------------------------------


async def _resume_at(db: AsyncSession, chat_id: int, user: User, session) -> None:
    if session.current_step == STEP_GOAL_QUESTION:
        await _send_goal_question(db, chat_id, user)
    elif session.current_step == STEP_TRUST_PRIVACY:
        await _send_trust_card(db, chat_id, user)
    elif session.current_step == STEP_FIRST_ASSET:
        await _send_first_asset_prompt(db, chat_id, user)
    elif session.current_step == STEP_TWIN_SHOWN:
        # Twin already shown — finalize the session silently so /menu and
        # briefings light up, then hand off to the menu for a normal
        # returning-user experience. The activation bubble waits for the
        # user's first deliberate engagement (button tap or free text).
        await _finalize_session_silently(db, user)
        from backend.bot.handlers.menu_handler import cmd_menu

        name = user.display_name or "bạn"
        await send_message(chat_id, f"Chào lại {name}! 👋", parse_mode="HTML")
        await cmd_menu(db, chat_id, user)


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
        await _send_name_prompt(chat_id)
        return True

    if action == "salutation" and len(parts) >= 3:
        await _on_salutation_picked(
            db, chat_id, callback_id, message_id, user, parts[2]
        )
        return True

    if action == "goal" and len(parts) >= 3:
        await _on_goal_picked(db, chat_id, callback_id, message_id, user, parts[2])
        return True

    if action == "trust_ok":
        await _on_trust_ok(db, chat_id, callback_id, user)
        return True

    if action == "asset_confirm" and len(parts) >= 3:
        await _on_asset_quality_confirm(
            db, chat_id, callback_id, message_id, user, parts[2]
        )
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

    if action == "retry_twin":
        await _on_retry_twin(db, chat_id, callback_id, user)
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
