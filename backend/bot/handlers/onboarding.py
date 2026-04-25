"""Onboarding handlers — one function per step of the 5-step flow.

Adapted to the Phase 1 raw-webhook router (no python-telegram-bot
framework). Each handler takes plain primitives (db, chat_id, user,
...) so it can be called from `routers/telegram.py` or tests.

Copy is intentionally warm but never sycophantic — see
`docs/tone_guide.md` → "Never cross into cheesy".
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.personality.onboarding_flow import (
    GOAL_RESPONSES,
    PRIMARY_GOALS,
    OnboardingStep,
)
from backend.models.user import User
from backend.services import dashboard_service, onboarding_service
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_menu,
    send_message,
)

logger = logging.getLogger(__name__)


class OnboardingEvent:
    """Analytics event names for the onboarding funnel."""
    STARTED = "onboarding_started"
    STEP_1_WELCOME_SHOWN = "onboarding_step_1_welcome_shown"
    STEP_2_NAME_ASKED = "onboarding_step_2_name_asked"
    STEP_2_NAME_CAPTURED = "onboarding_step_2_completed"
    STEP_3_GOAL_ASKED = "onboarding_step_3_goal_asked"
    STEP_3_GOAL_CAPTURED = "onboarding_step_3_completed"
    STEP_4_FIRST_TX_INVITED = "onboarding_step_4_first_tx_invited"
    STEP_4_FIRST_TX_LOGGED = "onboarding_step_4_completed"
    STEP_5_AHA_SHOWN = "onboarding_step_5_aha_shown"
    STEP_6_FIRST_ASSET_INVITED = "onboarding_step_6_first_asset_invited"
    FIRST_ASSET_ADDED = "first_asset_added"
    FIRST_ASSET_SKIPPED = "first_asset_skipped"
    COMPLETED = "onboarding_completed"
    SKIPPED = "onboarding_skipped"


# ---------- Keyboards ------------------------------------------------

def _welcome_keyboard() -> dict:
    return {
        "inline_keyboard": [[
            {"text": "✨ Bắt đầu", "callback_data": "onboarding:start"},
            {"text": "⏭ Bỏ qua", "callback_data": "onboarding:skip"},
        ]]
    }


def _goal_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": f"onboarding:goal:{code}"}]
            for code, label in PRIMARY_GOALS.items()
        ]
    }


def _completion_keyboard() -> dict:
    return {
        "inline_keyboard": [[
            {"text": "🚀 Bắt đầu", "callback_data": "onboarding:complete"},
        ]]
    }


def _first_asset_keyboard() -> dict:
    """Step 6 — choose how to add the first asset (or skip).

    Phase 3A: cash is the easiest entry; invest / real-estate route to
    their wizards directly. Skip is honest — we set
    ``onboarding_skipped_asset`` and complete the flow so the user is
    not blocked.
    """
    return {
        "inline_keyboard": [
            [{
                "text": "💵 Tiền trong NH (5 giây)",
                "callback_data": "onboarding:first_asset:cash",
            }],
            [{
                "text": "📈 Tôi có đầu tư",
                "callback_data": "onboarding:first_asset:stock",
            }],
            [{
                "text": "🏠 Tôi có BĐS",
                "callback_data": "onboarding:first_asset:real_estate",
            }],
            [{
                "text": "⏭ Skip, thêm sau",
                "callback_data": "onboarding:first_asset:skip",
            }],
        ]
    }


# ---------- Step messages --------------------------------------------

async def step_1_welcome(db: AsyncSession, chat_id: int, user: User) -> None:
    """Step 1 — warm greeting with 2 buttons (no plain text)."""
    text = (
        "👋 Chào bạn!\n\n"
        "Mình là trợ lý tài chính của bạn — mình không chỉ ghi chép, "
        "mình hiểu bạn.\n\n"
        "Trước khi bắt đầu, cho mình hỏi 2 câu nhẹ nhé?\n"
        "(Mất khoảng 1 phút, nhưng giúp mình phục vụ bạn tốt hơn nhiều!)"
    )
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=_welcome_keyboard(),
    )
    await onboarding_service.set_step(db, user.id, OnboardingStep.WELCOME)
    analytics.track(OnboardingEvent.STEP_1_WELCOME_SHOWN, user_id=user.id)


async def step_2_ask_name(db: AsyncSession, chat_id: int, user: User) -> None:
    """Step 2 — open-ended text prompt for the name."""
    text = (
        "Tuyệt!\n\n"
        "Bạn muốn mình gọi bạn là gì? 😊\n"
        "(Tên, nickname, gì cũng được — miễn là bạn thấy thoải mái)"
    )
    await send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    await onboarding_service.set_step(db, user.id, OnboardingStep.ASKING_NAME)
    analytics.track(OnboardingEvent.STEP_2_NAME_ASKED, user_id=user.id)


async def handle_name_input(
    db: AsyncSession, chat_id: int, user: User, raw_text: str
) -> bool:
    """Process a free-text message while the user is at ASKING_NAME.

    Returns True if the text was consumed (valid or invalid) so the
    generic transaction-text router should NOT also try to parse it.
    """
    if user.onboarding_step != int(OnboardingStep.ASKING_NAME):
        return False

    is_valid, name = onboarding_service.validate_display_name(raw_text)
    if not is_valid:
        if len(raw_text.strip()) > onboarding_service.MAX_DISPLAY_NAME_LEN:
            await send_message(
                chat_id=chat_id,
                text="Ôi tên hơi dài quá 😅 Bạn dùng tên ngắn hơn (tối đa 50 ký tự) được không?",
                parse_mode="HTML",
            )
        else:
            await send_message(
                chat_id=chat_id,
                text="Bạn nhập tên lại giúp mình nhé 🙏",
                parse_mode="HTML",
            )
        return True

    await onboarding_service.set_display_name(db, user.id, name)
    analytics.track(
        OnboardingEvent.STEP_2_NAME_CAPTURED,
        user_id=user.id,
        properties={"name_length": len(name)},
    )

    # Refresh user object so step 3 renders with the new name
    user.display_name = name
    await step_3_ask_goal(db, chat_id, user)
    return True


async def step_3_ask_goal(db: AsyncSession, chat_id: int, user: User) -> None:
    """Step 3 — 4 inline buttons for primary goal."""
    name = user.get_greeting_name()
    text = (
        f"Rất vui được gặp {name}! 🌱\n\n"
        f"{name} ơi, bạn đang muốn cải thiện điều gì nhất về tài chính lúc này?\n\n"
        "(Chọn 1 cái cũng được, không có đáp án \"đúng\" đâu)"
    )
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=_goal_keyboard(),
    )
    await onboarding_service.set_step(db, user.id, OnboardingStep.ASKING_GOAL)
    analytics.track(OnboardingEvent.STEP_3_GOAL_ASKED, user_id=user.id)


async def handle_goal_selection(
    db: AsyncSession,
    chat_id: int,
    message_id: int,
    callback_id: str,
    user: User,
    goal_code: str,
) -> None:
    """Process a goal-button tap from step 3."""
    if not onboarding_service.is_valid_goal_code(goal_code):
        await answer_callback(callback_id, text="Lựa chọn không hợp lệ")
        return

    await onboarding_service.set_primary_goal(db, user.id, goal_code)
    user.primary_goal = goal_code
    analytics.track(
        OnboardingEvent.STEP_3_GOAL_CAPTURED,
        user_id=user.id,
        properties={"goal": goal_code},
    )

    response = GOAL_RESPONSES.get(goal_code, "Cảm ơn bạn đã chia sẻ!")
    await answer_callback(callback_id)
    # Replace the goal-question message with the personalised reply
    # so the user has a clean thread.
    try:
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=response,
            parse_mode="HTML",
            reply_markup={"inline_keyboard": []},
        )
    except Exception:
        # edit can fail if the message is too old — just fall through.
        logger.debug("edit_message_text after goal pick failed", exc_info=True)

    await step_4_first_transaction(db, chat_id, user)


async def step_4_first_transaction(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Step 4 — invite the user to log their first expense."""
    name = user.get_greeting_name()
    text = (
        f"Giờ mình thử ngay nhé {name}!\n\n"
        "Bạn hôm nay đã chi gì rồi không?\n"
        "Gõ số tiền và mô tả ngắn, ví dụ:\n\n"
        "💬 \"45k phở\"\n"
        "💬 \"120k xăng\"\n"
        "💬 \"35000 cafe\"\n\n"
        "Thử đi, mình sẽ ghi lại cho bạn 👇"
    )
    await send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    await onboarding_service.set_step(
        db, user.id, OnboardingStep.FIRST_TRANSACTION
    )
    analytics.track(OnboardingEvent.STEP_4_FIRST_TX_INVITED, user_id=user.id)


async def step_5_aha_moment(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Step 5 — celebrate the first transaction, introduce 3 input modes.

    Called from the transaction handler AFTER the expense has been
    saved successfully. Phase 3A: this is no longer the terminal step —
    the user proceeds to ``step_6_first_asset`` next. The 🚀 button
    callback ``onboarding:complete`` now opens that step instead of
    finishing onboarding.
    """
    name = user.get_greeting_name()
    text = (
        f"🎉 Tuyệt vời {name}!\n\n"
        "Đó là giao dịch đầu tiên của bạn với mình.\n"
        "Từ giờ, bạn có 3 cách để ghi chép — cái nào tiện thì dùng:\n\n"
        "📝 Gõ text: như vừa rồi\n"
        "📸 Gửi ảnh hóa đơn: mình đọc được\n"
        "🎤 Gửi voice: mình hiểu luôn\n\n"
        "Sẵn sàng đi tiếp chưa? 💪"
    )
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=_completion_keyboard(),
    )
    analytics.track(OnboardingEvent.STEP_4_FIRST_TX_LOGGED, user_id=user.id)
    analytics.track(OnboardingEvent.STEP_5_AHA_SHOWN, user_id=user.id)

    # Step out of FIRST_TRANSACTION so subsequent expenses don't
    # retrigger this handler. AHA_MOMENT is the staging state until the
    # user taps 🚀 and lands on step 6.
    await onboarding_service.set_step(db, user.id, OnboardingStep.AHA_MOMENT)


async def step_6_first_asset(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Step 6 — invite the user to add their first asset (Phase 3A).

    The keyboard offers 3 fast routes (cash / stock / real-estate) plus
    an honest skip. Skip flips ``onboarding_skipped_asset`` and
    completes onboarding so the user isn't blocked behind an asset add.
    """
    name = user.get_greeting_name()
    text = (
        f"💎 <b>Bước cuối quan trọng {name}!</b>\n\n"
        "Hãy thêm <b>ít nhất 1 tài sản</b> của bạn — không cần đầy đủ.\n\n"
        "Đơn giản nhất là tiền trong ngân hàng — bao nhiêu trong TK cũng được.\n\n"
        "Sẵn sàng chưa?"
    )
    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=_first_asset_keyboard(),
    )
    await onboarding_service.set_step(db, user.id, OnboardingStep.FIRST_ASSET)
    analytics.track(OnboardingEvent.STEP_6_FIRST_ASSET_INVITED, user_id=user.id)


async def _finalise_onboarding(
    db: AsyncSession, user: User, *, fired_event: bool = False
) -> None:
    """Stamp ``onboarding_completed_at`` + fire COMPLETED once.

    Used by both the asset-added bridge and the explicit skip path.
    """
    if user.onboarding_completed_at is not None and fired_event:
        return
    if user.onboarding_completed_at is None:
        await onboarding_service.mark_completed(db, user.id)
        user.onboarding_completed_at = datetime.now(timezone.utc)

    duration_seconds: float | None = None
    if user.created_at:
        created = user.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        duration_seconds = (datetime.now(timezone.utc) - created).total_seconds()
    analytics.track(
        OnboardingEvent.COMPLETED,
        user_id=user.id,
        properties=(
            {"duration_seconds": int(duration_seconds)}
            if duration_seconds is not None else {}
        ),
    )


async def note_first_asset_added_if_needed(
    db: AsyncSession, user: User
) -> None:
    """Bridge called by the asset-entry wizard after a successful add.

    Only relevant if the user is on FIRST_ASSET — for everyone else this
    is a no-op. Fires ``first_asset_added`` and finalises onboarding.
    """
    if user.onboarding_step != int(OnboardingStep.FIRST_ASSET):
        return
    analytics.track(OnboardingEvent.FIRST_ASSET_ADDED, user_id=user.id)
    await _finalise_onboarding(db, user)


# ---------- Completion & skip ----------------------------------------

async def complete_onboarding(
    db: AsyncSession,
    chat_id: int,
    message_id: int,
    callback_id: str,
    user: User,
) -> None:
    """User taps 🚀 Bắt đầu after step 5.

    Phase 3A: this is no longer terminal — it routes into ``step_6_first_asset``.
    For users who somehow reach this button already past FIRST_ASSET
    (e.g. they re-tapped the old 🚀), we just acknowledge.
    """
    await answer_callback(callback_id, text="Đi tiếp nào ✨")
    try:
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✅ Tuyệt!",
            parse_mode="HTML",
            reply_markup={"inline_keyboard": []},
        )
    except Exception:
        logger.debug("edit_message_text on completion failed", exc_info=True)

    if user.onboarding_completed_at is not None:
        # Already done — don't re-prompt for an asset.
        return

    await step_6_first_asset(db, chat_id, user)


async def handle_first_asset_choice(
    db: AsyncSession,
    chat_id: int,
    message_id: int,
    callback_id: str,
    user: User,
    choice: str,
) -> None:
    """Step 6 callbacks: cash / stock / real_estate / skip."""
    await answer_callback(callback_id)
    try:
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Đang chuẩn bị… ⏳",
            parse_mode="HTML",
            reply_markup={"inline_keyboard": []},
        )
    except Exception:
        logger.debug("edit_message_text on first_asset choice failed", exc_info=True)

    if choice == "skip":
        user.onboarding_skipped_asset = True
        # Service mutation goes through the model directly; finalise
        # also flushes the skipped flag.
        await _finalise_onboarding(db, user)
        analytics.track(OnboardingEvent.FIRST_ASSET_SKIPPED, user_id=user.id)
        await send_message(
            chat_id=chat_id,
            text=(
                "Không sao, bạn có thể thêm sau bất cứ lúc nào 🙂\n"
                "Gõ /menu để xem các tính năng."
            ),
        )
        return

    # Route into the asset-entry wizard for the chosen type.
    # Lazy import keeps this handler decoupled from the wizard module
    # (avoids circular import — wizard imports back into onboarding).
    from backend.bot.handlers import asset_entry

    starters = {
        "cash": asset_entry._start_cash_subtype_pick,
        "stock": asset_entry._start_stock_subtype_pick,
        "real_estate": asset_entry._start_real_estate_subtype_pick,
    }
    starter = starters.get(choice)
    if starter is None:
        await send_message(chat_id=chat_id, text="Lựa chọn không hợp lệ.")
        return
    await starter(db, chat_id, user)


async def skip_onboarding(
    db: AsyncSession,
    chat_id: int,
    message_id: int,
    callback_id: str,
    user: User,
) -> None:
    """User taps ⏭ Bỏ qua on the welcome step."""
    await onboarding_service.mark_skipped(db, user.id)
    analytics.track(OnboardingEvent.SKIPPED, user_id=user.id)

    await answer_callback(callback_id)
    try:
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "Không sao cả 🙂\n\n"
                "Bạn có thể bắt đầu ghi giao dịch bất cứ lúc nào — "
                "ví dụ gõ \"45k phở\". Gõ /menu để xem hướng dẫn."
            ),
            parse_mode="HTML",
            reply_markup={"inline_keyboard": []},
        )
    except Exception:
        logger.debug("edit_message_text on skip failed", exc_info=True)


# ---------- Routing helpers ------------------------------------------

async def resume_or_start(
    db: AsyncSession, chat_id: int, user: User
) -> None:
    """Entry point for /start — drops the user at the correct step."""
    if user.is_onboarded:
        await send_welcome_back(chat_id, user)
        return

    step = OnboardingStep(user.onboarding_step)
    analytics.track(OnboardingEvent.STARTED, user_id=user.id)

    if step == OnboardingStep.NOT_STARTED:
        await step_1_welcome(db, chat_id, user)
    elif step == OnboardingStep.WELCOME:
        # User retriggered /start after seeing the welcome buttons —
        # treat as "yes, start".
        await step_2_ask_name(db, chat_id, user)
    elif step == OnboardingStep.ASKING_NAME:
        await send_message(
            chat_id=chat_id,
            text="Bạn muốn mình gọi bạn là gì nhỉ? 😊",
            parse_mode="HTML",
        )
    elif step == OnboardingStep.ASKING_GOAL:
        await step_3_ask_goal(db, chat_id, user)
    elif step == OnboardingStep.FIRST_TRANSACTION:
        await step_4_first_transaction(db, chat_id, user)
    elif step == OnboardingStep.AHA_MOMENT:
        # User completed first transaction but hasn't tapped 🚀 yet —
        # jump straight to step 6 (the 🚀 button is purely a transition).
        await step_6_first_asset(db, chat_id, user)
    elif step == OnboardingStep.FIRST_ASSET:
        await step_6_first_asset(db, chat_id, user)
    else:  # COMPLETED shouldn't reach here (is_onboarded catches it)
        await send_welcome_back(chat_id, user)


async def send_welcome_back(chat_id: int, user: User) -> None:
    """Short, friendly re-entry message for users already past onboarding.

    Also shows the main feature menu so behaviour matches the existing
    `/start` UX for pre-Phase-2 users (PR #46) — we don't want the bot
    to feel emptier just because they're past onboarding.
    """
    name = user.get_greeting_name()
    text = (
        f"Chào lại {name}! 👋\n\n"
        "Mình vẫn ở đây. Gõ giao dịch, gửi ảnh hoá đơn, hoặc chọn một "
        "mục bên dưới."
    )
    await send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    await send_menu(chat_id)


async def handle_onboarding_callback(
    db: AsyncSession, callback_query: dict
) -> bool:
    """Route any ``onboarding:*`` callback. Returns True if handled."""
    data: str = callback_query.get("data", "")
    if not data.startswith("onboarding:"):
        return False

    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    telegram_from = callback_query.get("from") or {}
    telegram_id = telegram_from.get("id")

    if chat_id is None or telegram_id is None:
        logger.warning("onboarding callback missing chat/telegram id: %s", data)
        return False

    user = await dashboard_service.get_user_by_telegram_id(db, telegram_id)
    if not user:
        await answer_callback(callback_id, text="Người dùng không tìm thấy")
        return True

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "start":
        await answer_callback(callback_id)
        # Collapse the original welcome buttons so only the new prompt remains.
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Bắt đầu nào! ✨",
                parse_mode="HTML",
                reply_markup={"inline_keyboard": []},
            )
        except Exception:
            logger.debug("edit on onboarding:start failed", exc_info=True)
        await step_2_ask_name(db, chat_id, user)
        return True

    if action == "skip":
        await skip_onboarding(db, chat_id, message_id, callback_id, user)
        return True

    if action == "goal" and len(parts) == 3:
        await handle_goal_selection(
            db, chat_id, message_id, callback_id, user, parts[2]
        )
        return True

    if action == "complete":
        await complete_onboarding(db, chat_id, message_id, callback_id, user)
        return True

    if action == "first_asset" and len(parts) == 3:
        await handle_first_asset_choice(
            db, chat_id, message_id, callback_id, user, parts[2]
        )
        return True

    await answer_callback(callback_id)
    return True
