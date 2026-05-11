"""Telegram /life_events command + wizard — Phase 4B Epic 2 (S9).

Two surfaces share this module:
- The top-level ``/life_events`` (alias ``/kehoach``) menu and its
  ``life_event:menu``/``life_event:list``/``life_event:delete_*`` callbacks.
- The add-event wizard, persisted on ``users.wizard_state`` so it survives
  process restarts mid-flow.

Flow names persisted in wizard_state.flow:
  life_event_picker     — type picker shown, nothing chosen yet
  life_event_preset     — preset chosen, awaiting year / customize choice
  life_event_custom     — CUSTOM type, full custom-entry flow
  life_event_delete     — delete picker open

Step names within each flow (state.step):
  ``ask_year``, ``review_preset``, ``ask_title``, ``ask_one_time``,
  ``ask_monthly``, ``ask_duration``, ``confirm``.

Layer contract: handler may flush via ``life_event_service`` / wizard_service
but never commits. The worker owns the transaction boundary.

Side effects after save:
  1. Trigger Twin recompute via ``recompute_service.enqueue_recompute_if_needed``
     using ``one_time_cost`` as delta (same threshold logic as asset edits).
  2. Send the before/after impact chart (S10) inline.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.menu_formatter import back_to_main_keyboard
from backend.bot.formatters.money import format_money_short
from backend.bot.keyboards.common import parse_callback
from backend.bot.keyboards.life_event_keyboard import (
    CB_LIFE_EVENT,
    back_to_menu_keyboard,
    confirm_save_keyboard,
    delete_confirm_keyboard,
    delete_pick_keyboard,
    event_type_picker_keyboard,
    life_events_menu_keyboard,
)
from backend.life_events import service as life_event_service
from backend.life_events.presets import get_preset
from backend.life_events.schemas import LifeEventCreate
from backend.models.life_event import LifeEvent, LifeEventType
from backend.models.user import User
from backend.services import wizard_service
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import (
    answer_callback,
    edit_message_text,
    send_message,
    send_photo,
)
from backend.wealth.amount_parser import parse_amount

logger = logging.getLogger(__name__)


FLOW_PICKER = "life_event_picker"
FLOW_PRESET = "life_event_preset"
FLOW_CUSTOM = "life_event_custom"
FLOW_DELETE = "life_event_delete"

# Used by the worker's auto-exit guard — see telegram_worker.py.
ALL_FLOWS = (FLOW_PICKER, FLOW_PRESET, FLOW_CUSTOM, FLOW_DELETE)


class LifeEventEvent:
    """Analytics event names for the life-event wizard funnel."""

    WIZARD_OPENED = "life_event_wizard_opened"
    TYPE_PICKED = "life_event_type_picked"
    EVENT_SAVED = "life_event_saved"
    EVENT_DELETED = "life_event_deleted"
    WIZARD_CANCELED = "life_event_wizard_canceled"
    PARSE_FAILED = "life_event_wizard_parse_failed"


_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "life_events.yaml"
_MIN_PLANNED_YEAR_OFFSET = 0       # current year is the earliest allowed
_MAX_PLANNED_YEAR_OFFSET = 50      # 50 years out is a generous horizon


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _money_short(value: Decimal | int | float | str | None) -> str:
    if value is None or Decimal(str(value)) == 0:
        return "0"
    return format_money_short(Decimal(str(value)))


def _preset_meta() -> dict[str, dict[str, str]]:
    """Return preset metadata keyed by LifeEventType.value for keyboard rendering."""
    return _copy().get("presets", {})


def _type_label_map() -> dict[LifeEventType, dict[str, str]]:
    """Build a {LifeEventType: {icon, short_label}} map from the YAML."""
    meta = _preset_meta()
    return {
        event_type: {
            "icon": meta.get(event_type.value, {}).get("icon", ""),
            "short_label": meta.get(event_type.value, {}).get("short_label", event_type.value),
            "label": meta.get(event_type.value, {}).get("label", event_type.value),
        }
        for event_type in LifeEventType
    }


# -----------------------------------------------------------------------------
# /life_events command and top-level menu
# -----------------------------------------------------------------------------


async def cmd_life_events(db: AsyncSession, chat_id: int, user: User | None) -> None:
    """Entry point: /life_events command."""
    if user is None:
        await send_message(
            chat_id=chat_id,
            text="Gõ /start để mình chào bạn trước nhé 🌱",
        )
        return
    copy = _copy()["menu"]
    await send_message(
        chat_id=chat_id,
        text=copy["intro"],
        reply_markup=life_events_menu_keyboard(),
    )
    analytics.track(LifeEventEvent.WIZARD_OPENED, user_id=user.id)


async def _show_menu(db: AsyncSession, chat_id: int, message_id: int | None) -> None:
    copy = _copy()["menu"]
    if message_id is not None:
        await edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=copy["intro"],
            reply_markup=life_events_menu_keyboard(),
        )
    else:
        await send_message(
            chat_id=chat_id,
            text=copy["intro"],
            reply_markup=life_events_menu_keyboard(),
        )


# -----------------------------------------------------------------------------
# View list
# -----------------------------------------------------------------------------


def _format_event_line(event: LifeEvent, idx: int, copy_menu: dict) -> str:
    meta = _preset_meta().get(event.event_type, {})
    icon = meta.get("icon", "•")
    title = event.title or meta.get("label", event.event_type)
    date_str = (
        str(event.planned_date.year) if event.planned_date else copy_menu["list_no_date"]
    )
    cost_parts = []
    if event.one_time_cost and Decimal(str(event.one_time_cost)) > 0:
        cost_parts.append(_money_short(event.one_time_cost))
    if (
        event.recurring_monthly_delta
        and Decimal(str(event.recurring_monthly_delta)) != 0
    ):
        sign = "" if Decimal(str(event.recurring_monthly_delta)) < 0 else "+"
        cost_parts.append(
            f"{sign}{_money_short(event.recurring_monthly_delta)}/th"
        )
    cost_str = " · ".join(cost_parts) if cost_parts else copy_menu["list_no_cost"]
    return copy_menu["list_item"].format(
        idx=idx, icon=icon, title=title, date=date_str, cost=cost_str
    )


async def show_list(db: AsyncSession, chat_id: int, user: User) -> None:
    copy_menu = _copy()["menu"]
    events = await life_event_service.list_for_user(db, user.id)
    if not events:
        await send_message(
            chat_id=chat_id,
            text=copy_menu["empty"],
            reply_markup=back_to_menu_keyboard(),
        )
        return
    lines = [copy_menu["list_header"], ""]
    for idx, event in enumerate(events, start=1):
        lines.append(_format_event_line(event, idx, copy_menu))
    await send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        reply_markup=back_to_menu_keyboard(),
    )


# -----------------------------------------------------------------------------
# Add flow — type picker → preset / custom → year → confirm
# -----------------------------------------------------------------------------


async def start_add_flow(db: AsyncSession, chat_id: int, user: User) -> None:
    """Show the 6-button type picker. First step of the add flow."""
    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_PICKER,
        step="type",
        draft={},
    )
    await send_message(
        chat_id=chat_id,
        text=_copy()["menu"]["intro"],
        reply_markup=event_type_picker_keyboard(_type_label_map()),
    )


async def _handle_pick_type(
    db: AsyncSession,
    chat_id: int,
    user: User,
    event_type: LifeEventType,
) -> None:
    """User chose a type — branch into preset review or custom flow."""
    if event_type == LifeEventType.CUSTOM:
        await wizard_service.start_flow(
            db,
            user.id,
            FLOW_CUSTOM,
            step="ask_title",
            draft={"event_type": event_type.value},
        )
        await send_message(
            chat_id=chat_id,
            text=_copy()["prompts"]["ask_custom_title"],
        )
        analytics.track(
            LifeEventEvent.TYPE_PICKED,
            user_id=user.id,
            properties={"event_type": event_type.value, "branch": "custom"},
        )
        return

    preset = get_preset(event_type)
    draft = {
        "event_type": event_type.value,
        "one_time_cost": str(preset.one_time_cost),
        "recurring_monthly_delta": str(preset.recurring_monthly_delta),
        "recurring_duration_months": preset.recurring_duration_months,
    }
    await wizard_service.start_flow(
        db, user.id, FLOW_PRESET, step="ask_year", draft=draft
    )
    meta = _preset_meta().get(event_type.value, {})
    duration_years = preset.recurring_duration_months // 12
    summary = meta.get("summary", "").format(
        one_time=_money_short(preset.one_time_cost),
        monthly=_money_short(preset.recurring_monthly_delta),
        duration_years=duration_years,
    )
    await send_message(chat_id=chat_id, text=summary)
    analytics.track(
        LifeEventEvent.TYPE_PICKED,
        user_id=user.id,
        properties={"event_type": event_type.value, "branch": "preset"},
    )


# -----------------------------------------------------------------------------
# Mid-wizard text input
# -----------------------------------------------------------------------------


async def handle_life_event_text_input(
    db: AsyncSession, message: dict[str, Any]
) -> bool:
    """Consume a free-text message belonging to an active life-event wizard.

    Returns True if consumed (so the NL expense parser is bypassed).
    """
    chat_id = message.get("chat", {}).get("id")
    telegram_id = (message.get("from") or {}).get("id")
    text_raw = (message.get("text") or "").strip()
    if chat_id is None or telegram_id is None or not text_raw:
        return False
    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None or not user.wizard_state:
        return False
    flow = wizard_service.get_flow(user.wizard_state)
    if flow not in {FLOW_PRESET, FLOW_CUSTOM}:
        return False
    step = wizard_service.get_step(user.wizard_state)
    draft = wizard_service.get_draft(user.wizard_state)

    try:
        if step == "ask_year":
            await _consume_year(db, chat_id, user, draft, flow, text_raw)
        elif step == "ask_title":
            await _consume_title(db, chat_id, user, draft, text_raw)
        elif step == "ask_one_time":
            await _consume_one_time(db, chat_id, user, draft, text_raw)
        elif step == "ask_monthly":
            await _consume_monthly(db, chat_id, user, draft, text_raw)
        elif step == "ask_duration":
            await _consume_duration(db, chat_id, user, draft, text_raw)
        elif step == "customize_one_time":
            await _consume_one_time(db, chat_id, user, draft, text_raw, next_step="customize_monthly")
        elif step == "customize_monthly":
            await _consume_monthly(db, chat_id, user, draft, text_raw, next_step="customize_duration")
        elif step == "customize_duration":
            await _consume_duration(db, chat_id, user, draft, text_raw, next_step="ask_year")
        else:
            return False
    except Exception:
        logger.exception("life-event text input failed: step=%s", step)
        await send_message(
            chat_id=chat_id, text=_copy()["errors"]["generic"]
        )
        return True
    return True


async def _consume_year(
    db: AsyncSession,
    chat_id: int,
    user: User,
    draft: dict,
    flow: str,
    text_raw: str,
) -> None:
    year = _parse_year(text_raw)
    today = _today()
    min_year = today.year + _MIN_PLANNED_YEAR_OFFSET
    max_year = today.year + _MAX_PLANNED_YEAR_OFFSET
    if year is None or year < min_year or year > max_year:
        await send_message(
            chat_id=chat_id,
            text=_copy()["prompts"]["invalid_year"].format(
                min_year=min_year, max_year=max_year
            ),
        )
        analytics.track(
            LifeEventEvent.PARSE_FAILED,
            user_id=user.id,
            properties={"step": "ask_year", "input": text_raw[:50]},
        )
        return
    # Normalize to Jan 1 of selected year — wizard only asks year.
    planned_date = date(year, 1, 1)
    draft["planned_date"] = planned_date.isoformat()
    await wizard_service.update_step(db, user.id, "confirm", draft_patch=draft)
    await _send_review(db, chat_id, user, draft)


async def _consume_title(
    db: AsyncSession, chat_id: int, user: User, draft: dict, text_raw: str
) -> None:
    title = text_raw[:120]
    draft["title"] = title
    await wizard_service.update_step(db, user.id, "ask_one_time", draft_patch=draft)
    await send_message(chat_id=chat_id, text=_copy()["prompts"]["ask_custom_one_time"])


async def _consume_one_time(
    db: AsyncSession,
    chat_id: int,
    user: User,
    draft: dict,
    text_raw: str,
    *,
    next_step: str = "ask_monthly",
) -> None:
    amount = _parse_amount_or_zero(text_raw)
    if amount is None or amount < 0:
        await send_message(chat_id=chat_id, text=_copy()["prompts"]["invalid_amount"])
        return
    draft["one_time_cost"] = str(amount)
    if next_step == "customize_monthly":
        await wizard_service.update_step(db, user.id, "customize_monthly", draft_patch=draft)
        await send_message(chat_id=chat_id, text=_copy()["prompts"]["ask_custom_monthly"])
    else:
        await wizard_service.update_step(db, user.id, "ask_monthly", draft_patch=draft)
        await send_message(chat_id=chat_id, text=_copy()["prompts"]["ask_custom_monthly"])


async def _consume_monthly(
    db: AsyncSession,
    chat_id: int,
    user: User,
    draft: dict,
    text_raw: str,
    *,
    next_step: str = "ask_duration",
) -> None:
    # Accept positive numbers and store with a negative sign — life events are
    # outflows by default. Power users can prefix "+" to indicate inflow.
    raw = text_raw.strip()
    sign = -1
    if raw.startswith("+"):
        sign = 1
        raw = raw[1:].strip()
    amount = _parse_amount_or_zero(raw)
    if amount is None:
        await send_message(chat_id=chat_id, text=_copy()["prompts"]["invalid_amount"])
        return
    if amount == 0:
        signed = Decimal("0")
    else:
        signed = amount * Decimal(sign)
    draft["recurring_monthly_delta"] = str(signed)
    target_step = "customize_duration" if next_step == "customize_duration" else "ask_duration"
    await wizard_service.update_step(db, user.id, target_step, draft_patch=draft)
    await send_message(chat_id=chat_id, text=_copy()["prompts"]["ask_custom_duration"])


async def _consume_duration(
    db: AsyncSession,
    chat_id: int,
    user: User,
    draft: dict,
    text_raw: str,
    *,
    next_step: str = "ask_year",
) -> None:
    try:
        months = int("".join(ch for ch in text_raw if ch.isdigit()) or "0")
    except ValueError:
        months = -1
    if months < 0 or months > 600:
        await send_message(chat_id=chat_id, text=_copy()["prompts"]["invalid_duration"])
        return
    draft["recurring_duration_months"] = months
    await wizard_service.update_step(db, user.id, "ask_year", draft_patch=draft)
    short_label = _type_label_map().get(LifeEventType(draft["event_type"]), {}).get(
        "short_label", ""
    )
    await send_message(
        chat_id=chat_id,
        text=_copy()["prompts"]["ask_year"].format(short_label=short_label),
    )


# -----------------------------------------------------------------------------
# Confirmation review
# -----------------------------------------------------------------------------


async def _send_review(
    db: AsyncSession, chat_id: int, user: User, draft: dict
) -> None:
    event_type = LifeEventType(draft.get("event_type", LifeEventType.CUSTOM.value))
    meta = _preset_meta().get(event_type.value, {})
    icon = meta.get("icon", "•")
    title = draft.get("title") or meta.get("label", event_type.value)
    planned_iso = draft.get("planned_date")
    year = "—"
    if planned_iso:
        try:
            year = str(date.fromisoformat(planned_iso).year)
        except ValueError:
            year = "—"
    one_time = Decimal(str(draft.get("one_time_cost") or "0"))
    monthly = Decimal(str(draft.get("recurring_monthly_delta") or "0"))
    duration_months = int(draft.get("recurring_duration_months") or 0)
    copy = _copy()["confirm"]
    if monthly == 0 or duration_months == 0:
        duration_text = "" if monthly == 0 else (
            " (kéo dài đến cuối horizon)" if duration_months == 0 and monthly != 0 else ""
        )
    else:
        duration_text = copy["duration_suffix"].format(duration_years=duration_months // 12)
    monthly_text = (
        copy["no_recurring"] if monthly == 0 else f"{_money_short(monthly)}/tháng"
    )
    body = copy["body"].format(
        icon=icon,
        title=title,
        year=year,
        one_time=_money_short(one_time) if one_time != 0 else "0",
        monthly=monthly_text,
        duration_text=duration_text,
    )
    text = f"{copy['title']}\n\n{body}"
    await send_message(
        chat_id=chat_id, text=text, reply_markup=confirm_save_keyboard()
    )


async def _handle_use_preset(db: AsyncSession, chat_id: int, user: User) -> None:
    draft = wizard_service.get_draft(user.wizard_state)
    if "planned_date" in draft:
        await wizard_service.update_step(db, user.id, "confirm", draft_patch=draft)
        await _send_review(db, chat_id, user, draft)
        return
    event_type = LifeEventType(draft.get("event_type", LifeEventType.CUSTOM.value))
    short_label = (
        _type_label_map().get(event_type, {}).get("short_label", event_type.value)
    )
    await wizard_service.update_step(db, user.id, "ask_year", draft_patch=draft)
    await send_message(
        chat_id=chat_id,
        text=_copy()["prompts"]["ask_year"].format(short_label=short_label),
    )


async def _handle_customize(db: AsyncSession, chat_id: int, user: User) -> None:
    draft = wizard_service.get_draft(user.wizard_state)
    await wizard_service.update_step(
        db, user.id, "customize_one_time", draft_patch=draft
    )
    await send_message(chat_id=chat_id, text=_copy()["prompts"]["ask_custom_one_time"])


async def _handle_confirm(db: AsyncSession, chat_id: int, user: User) -> None:
    draft = wizard_service.get_draft(user.wizard_state)
    try:
        event_type = LifeEventType(draft.get("event_type", LifeEventType.CUSTOM.value))
    except ValueError:
        event_type = LifeEventType.CUSTOM
    planned_iso = draft.get("planned_date")
    planned_date = None
    if planned_iso:
        try:
            planned_date = date.fromisoformat(planned_iso)
        except ValueError:
            planned_date = None
    payload = LifeEventCreate(
        event_type=event_type,
        title=draft.get("title") or _type_label_map().get(event_type, {}).get("label"),
        planned_date=planned_date,
        one_time_cost=_decimal_or_none(draft.get("one_time_cost")),
        recurring_monthly_delta=_decimal_or_none(draft.get("recurring_monthly_delta")),
        recurring_duration_months=_int_or_none(draft.get("recurring_duration_months")),
    )
    event = await life_event_service.create_life_event(db, user.id, payload)
    await wizard_service.clear(db, user.id)
    analytics.track(
        LifeEventEvent.EVENT_SAVED,
        user_id=user.id,
        properties={
            "event_type": event_type.value,
            "planned_year": planned_date.year if planned_date else None,
            "has_one_time": payload.one_time_cost is not None and payload.one_time_cost > 0,
            "has_recurring": payload.recurring_monthly_delta not in (None, Decimal("0")),
        },
    )
    title = event.title or event_type.value
    await send_message(
        chat_id=chat_id, text=_copy()["post_save"]["saved"].format(title=title)
    )
    # Trigger Twin recompute + send impact chart in the background so the user
    # gets immediate UI feedback while heavy compute runs in its own session.
    asyncio.create_task(
        _recompute_and_send_impact(user_id=user.id, chat_id=chat_id, event_id=event.id)
    )


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except Exception:
        return None
    return d if d != 0 else None


def _int_or_none(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


async def _recompute_and_send_impact(
    *, user_id: uuid.UUID, chat_id: int, event_id: uuid.UUID
) -> None:
    """Run Twin recompute and post the before/after impact chart.

    Owns its own DB session so we don't keep the wizard's session open during
    the heavy MC work. Errors are logged but never raised — the user already
    received the save confirmation; chart failure should not break the flow.
    """
    from backend.database import get_session_factory
    from backend.life_events.chart import render_life_event_impact_chart

    session_factory = get_session_factory()
    copy_post = _copy()["post_save"]
    try:
        async with session_factory() as db:
            try:
                event = await life_event_service.get_by_id(db, user_id, event_id)
                if event is None:
                    return
                # Recompute Twin from scratch — applies all active events.
                from backend.twin.services.twin_projection_service import (
                    compute_and_store,
                )

                await compute_and_store(db, user_id, scenario="both")
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("life-event recompute failed user=%s", user_id)
                await send_message(
                    chat_id=chat_id, text=copy_post["recompute_failed"]
                )
                return

        async with session_factory() as db:
            event = await life_event_service.get_by_id(db, user_id, event_id)
            if event is None:
                return
            chart_png = await render_life_event_impact_chart(db, user_id, event)
            if chart_png is None:
                return
            caption = copy_post["recompute_done"]
            await send_photo(
                chat_id=chat_id,
                photo_bytes=chart_png,
                caption=caption,
                filename="be-tien-life-event.png",
                parse_mode=None,
            )
    except Exception:
        logger.exception("life-event impact chart failed user=%s", user_id)


async def _handle_restart(db: AsyncSession, chat_id: int, user: User) -> None:
    """Reset to the type picker so the user can re-pick from scratch."""
    await start_add_flow(db, chat_id, user)


# -----------------------------------------------------------------------------
# Delete flow
# -----------------------------------------------------------------------------


async def show_delete_menu(db: AsyncSession, chat_id: int, user: User) -> None:
    events = await life_event_service.list_for_user(db, user.id)
    if not events:
        await send_message(
            chat_id=chat_id,
            text=_copy()["menu"]["empty"],
            reply_markup=back_to_menu_keyboard(),
        )
        return
    await wizard_service.start_flow(db, user.id, FLOW_DELETE, step="pick", draft={})
    await send_message(
        chat_id=chat_id,
        text="🗑 Chọn mốc bạn muốn xóa:",
        reply_markup=delete_pick_keyboard(events),
    )


async def _handle_delete_pick(
    db: AsyncSession, chat_id: int, user: User, event_id: uuid.UUID
) -> None:
    event = await life_event_service.get_by_id(db, user.id, event_id)
    if event is None:
        await send_message(chat_id=chat_id, text=_copy()["delete"]["not_found"])
        return
    title = event.title or event.event_type
    await send_message(
        chat_id=chat_id,
        text=(
            _copy()["delete"]["confirm_title"].format(title=title)
            + "\n"
            + _copy()["delete"]["confirm_body"]
        ),
        reply_markup=delete_confirm_keyboard(event.id),
    )


async def _handle_delete_confirm(
    db: AsyncSession, chat_id: int, user: User, event_id: uuid.UUID
) -> None:
    event = await life_event_service.get_by_id(db, user.id, event_id)
    if event is None:
        await send_message(chat_id=chat_id, text=_copy()["delete"]["not_found"])
        return
    title = event.title or event.event_type
    deleted = await life_event_service.soft_delete(db, user.id, event_id)
    if not deleted:
        await send_message(chat_id=chat_id, text=_copy()["delete"]["not_found"])
        return
    await wizard_service.clear(db, user.id)
    analytics.track(
        LifeEventEvent.EVENT_DELETED,
        user_id=user.id,
        properties={"event_id": str(event_id)},
    )
    await send_message(
        chat_id=chat_id,
        text=_copy()["delete"]["done"].format(title=title),
        reply_markup=back_to_main_keyboard(),
    )
    # Trigger Twin recompute so projections reflect the deletion.
    asyncio.create_task(_recompute_after_delete(user_id=user.id))


async def _recompute_after_delete(user_id: uuid.UUID) -> None:
    """Recompute Twin in the background after a soft delete."""
    from backend.database import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            from backend.twin.services.twin_projection_service import compute_and_store

            await compute_and_store(db, user_id, scenario="both")
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("life-event delete-recompute failed user=%s", user_id)


# -----------------------------------------------------------------------------
# Cancel
# -----------------------------------------------------------------------------


async def cancel_wizard(db: AsyncSession, chat_id: int, user: User) -> bool:
    """Clear an active life-event wizard state if present."""
    flow = (user.wizard_state or {}).get("flow") or ""
    if flow not in ALL_FLOWS:
        return False
    await wizard_service.clear(db, user.id)
    analytics.track(LifeEventEvent.WIZARD_CANCELED, user_id=user.id)
    await send_message(chat_id=chat_id, text="Đã huỷ. Quay lại lúc nào cũng được 👋")
    return True


# -----------------------------------------------------------------------------
# Callback router
# -----------------------------------------------------------------------------


async def handle_life_event_callback(
    db: AsyncSession, callback_query: dict[str, Any]
) -> bool:
    """Route every ``life_event:*`` callback. Returns True once handled."""
    data: str = callback_query.get("data") or ""
    if not data.startswith(f"{CB_LIFE_EVENT}:") and data != CB_LIFE_EVENT:
        return False
    prefix, args = parse_callback(data)
    if prefix != CB_LIFE_EVENT:
        return False
    action = args[0] if args else ""
    callback_id = callback_query["id"]
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    from_user = callback_query.get("from") or {}
    telegram_id = from_user.get("id")
    user = await get_user_by_telegram_id(db, telegram_id) if telegram_id else None
    if user is None or chat_id is None:
        await answer_callback(callback_id)
        return True

    await answer_callback(callback_id)
    try:
        if action == "menu":
            await _show_menu(db, chat_id, message_id)
        elif action == "list":
            await show_list(db, chat_id, user)
        elif action == "add":
            await start_add_flow(db, chat_id, user)
        elif action == "pick_type" and len(args) >= 2:
            try:
                event_type = LifeEventType(args[1])
            except ValueError:
                event_type = LifeEventType.CUSTOM
            await _handle_pick_type(db, chat_id, user, event_type)
        elif action == "use_preset":
            await _handle_use_preset(db, chat_id, user)
        elif action == "customize":
            await _handle_customize(db, chat_id, user)
        elif action == "confirm":
            await _handle_confirm(db, chat_id, user)
        elif action == "restart":
            await _handle_restart(db, chat_id, user)
        elif action == "cancel":
            await cancel_wizard(db, chat_id, user)
        elif action == "delete_menu":
            await show_delete_menu(db, chat_id, user)
        elif action == "delete_pick" and len(args) >= 2:
            event_id = _parse_uuid(args[1])
            if event_id:
                await _handle_delete_pick(db, chat_id, user, event_id)
        elif action == "delete_confirm" and len(args) >= 2:
            event_id = _parse_uuid(args[1])
            if event_id:
                await _handle_delete_confirm(db, chat_id, user, event_id)
        else:
            logger.warning("Unknown life_event callback: %s", data)
    except Exception:
        logger.exception("life_event callback failed: %s", data)
        await send_message(chat_id=chat_id, text=_copy()["errors"]["generic"])
    return True


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _parse_year(text: str) -> int | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits[:4])
    except ValueError:
        return None


def _parse_amount_or_zero(text: str) -> Decimal | None:
    """Return a parsed amount, ``Decimal(0)`` for "0", or ``None`` for invalid."""
    stripped = text.strip()
    if stripped in {"0", "không", "khong", "no", "không có", "khong co"}:
        return Decimal("0")
    parsed = parse_amount(stripped)
    if parsed is None:
        return None
    return parsed


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
