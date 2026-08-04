"""Zalo-first onboarding — Phase 5.1 E4 #4.3.

Until now every account started on Telegram and the Zalo OA could only
*find* people. This module makes the OA a signup channel: a stranger who
messages the OA without a ``BT-XXXXXX`` token gets the same onboarding
the Telegram wizard runs (name → salutation → goal → trust → asset →
Twin), rendered through the Zalo renderer and answered with plain text.

Why plain text and not callbacks: a callback-only ``Button`` maps to
``oa.query.show``, which makes Zalo send *the button's own label back as
an ordinary inbound message*. The buttons are therefore suggestions, not
a separate input channel — every step must be answerable by typing, and
the parser matches against button **titles**.

There is deliberately no "Zalo version" of any onboarding service: this
handler drives ``backend.services.onboarding`` exactly as the Telegram
handler does, and the channel difference lives entirely in the copy
(``content/zalo.yaml``) and the renderer.

Layer contract: handler routes and formats, services flush, the worker
commits at the boundary.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from backend import analytics
from backend.adapters.zalo_content_renderer import ZaloContentRenderer
from backend.bot.handlers.onboarding_v2 import (
    is_onboarding_reset_enabled,
    is_trust_card_enabled,
)
from backend.config import get_settings
from backend.models.onboarding_session import (
    ALL_SALUTATIONS,
    STEP_COMPLETED,
    STEP_FIRST_ASSET,
    STEP_GOAL_QUESTION,
    STEP_TRUST_PRIVACY,
    STEP_TWIN_SHOWN,
)
from backend.models.user import User
from backend.ports.content_renderer import Button, ChannelContent, TwinViewSnapshot
from backend.services import onboarding_service as legacy_onboarding_service
from backend.services import zalo_linking_service
from backend.services.onboarding import onboarding_service
from backend.utils.zalo_copy import text as zalo_text
from backend.wealth.services import asset_service

logger = logging.getLogger(__name__)

# handlers → bot → backend → repo root
_TRUST_COPY_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "onboarding" / "trust_card.yaml"
)

# Mirrors ``onboarding_v2``: the reset cohort's copy block wins when the
# flag is on, but the ack lookup scans both so a flag flipped mid-session
# still resolves the code the user actually picked.
_GOAL_COPY_BLOCKS = ("step_1_goal_reset", "step_1_goal")
_DEFAULT_GOAL_ORDER = ("understand_wealth", "plan_goal", "track_spending")

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")
# Strips decorative emoji from the head of a bullet. ``\w`` is unicode by
# default, so Vietnamese letters survive and only the ornament goes — the
# trust card carries three emoji and Zalo copy allows two per message.
_LEADING_ORNAMENT_RE = re.compile(r"^[^\w]+", flags=re.UNICODE)

_ZALO_CHAT_ID = 0  # Zalo notifiers address the sender, not a chat id.


def _norm(value: str) -> str:
    """Fold a reply for comparison against a button title.

    ``oa.query.show`` echoes the label verbatim, but people also retype
    it by hand, so punctuation, emoji and spacing are all noise.
    """
    lowered = (value or "").strip().lower()
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", lowered)).strip()


def _match_option(text: str, options: dict[str, str]) -> str | None:
    """Resolve free text to an option code by label or by code."""
    target = _norm(text)
    if not target:
        return None
    for code, label in options.items():
        if target == _norm(label) or target == _norm(code):
            return code
    return None


def _args(user: User, **extra: Any) -> dict[str, Any]:
    """Format args for ``zalo_copy.text``.

    Both cases are always supplied: a missing key makes the copy helper
    return the raw template, i.e. literal ``{braces}`` in the user's face.
    """
    value = onboarding_service.salutation_of(user)
    return {"salutation": value, "Salutation": value.capitalize(), **extra}


async def _say(
    notifier,
    key: str,
    user: User,
    *,
    buttons: tuple[tuple[Button, ...], ...] = (),
    **extra: Any,
) -> Any:
    body = zalo_text("onboarding", key, **_args(user, **extra))
    if not body:
        logger.warning("Zalo onboarding copy missing: onboarding.%s", key)
        return None
    if buttons:
        return await notifier.send_message(_ZALO_CHAT_ID, body, buttons=buttons)
    return await notifier.send_message(_ZALO_CHAT_ID, body)


def _one_button(label: str) -> tuple[tuple[Button, ...], ...]:
    if not label:
        return ()
    return ((Button(text=label),),)


def _option_buttons(options: dict[str, str]) -> tuple[tuple[Button, ...], ...]:
    """One row per option — ``oa.query.show``, so tapping simply types it."""
    return tuple((Button(text=label),) for label in options.values() if label)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


async def start_new_user(db, *, notifier, zalo_user_id: str) -> User | None:
    """Mint (or recover) the account behind ``zalo_user_id`` and greet it."""
    user, created = await zalo_linking_service.get_or_create_zalo_user(db, zalo_user_id)
    await onboarding_service.start_or_resume(db, user.id)
    if created:
        analytics.track("zalo_onboarding_started", user_id=user.id)
    await _say(notifier, "welcome", user)
    await _say(notifier, "ask_name", user)
    return user


async def handle_text(db, *, notifier, user: User, text: str) -> bool:
    """Consume ``text`` as an onboarding answer. Returns True if consumed.

    False means "this isn't onboarding" and the caller should fall
    through to normal intent dispatch.
    """
    # Checked first: the invitation is sent *after* the session is
    # completed, so a decline arrives when no step is left to route on.
    if await _handle_invite_answer(db, notifier=notifier, user=user, text=text):
        return True

    session = await onboarding_service.get_session(db, user.id)
    if session is None or session.current_step == STEP_COMPLETED:
        return False

    step = session.current_step
    if step == STEP_GOAL_QUESTION:
        return await _handle_identity_step(db, notifier=notifier, user=user, text=text)
    if step == STEP_TRUST_PRIVACY:
        return await _handle_trust_step(db, notifier=notifier, user=user)
    if step == STEP_FIRST_ASSET:
        return await _handle_asset_step(db, notifier=notifier, user=user, text=text)
    if step == STEP_TWIN_SHOWN:
        # Twin already drawn; anything they say closes onboarding out.
        await _finish(db, notifier=notifier, user=user)
        return True
    return False


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------


async def _handle_identity_step(db, *, notifier, user: User, text: str) -> bool:
    substep = onboarding_service.goal_substep(user)

    if substep == onboarding_service.SUBSTEP_NAME:
        ok, name = legacy_onboarding_service.validate_display_name(text)
        if not ok:
            await _say(notifier, "name_invalid", user)
            return True
        await legacy_onboarding_service.set_display_name(db, user.id, name)
        await onboarding_service.touch_session(db, user.id)
        await _say(
            notifier,
            "ask_salutation",
            user,
            buttons=_option_buttons(_salutation_options()),
        )
        return True

    if substep == onboarding_service.SUBSTEP_SALUTATION:
        options = _salutation_options()
        code = _match_option(text, options)
        if code is None:
            await _say(notifier, "salutation_invalid", user)
            return True
        updated = await onboarding_service.set_salutation(db, user.id, code)
        if updated is None:
            await _say(notifier, "salutation_invalid", user)
            return True
        await onboarding_service.touch_session(db, user.id)
        ack = _salutation_ack(code)
        if ack:
            await notifier.send_message(_ZALO_CHAT_ID, ack)
        await _say(notifier, "ask_goal", user, buttons=_option_buttons(_goal_options()))
        return True

    # SUBSTEP_GOAL
    options = _goal_options()
    code = _match_option(text, options)
    if code is None:
        await _say(notifier, "goal_invalid", user)
        return True
    trust_enabled = is_trust_card_enabled()
    session = await onboarding_service.set_goal(
        db, user.id, code, trust_card_enabled=trust_enabled
    )
    if session is None:
        await _say(notifier, "goal_invalid", user)
        return True
    ack = _goal_ack(code)
    if ack:
        await notifier.send_message(_ZALO_CHAT_ID, ack)
    if trust_enabled:
        await _send_trust_card(db, notifier=notifier, user=user)
    else:
        await _ask_asset(notifier, user)
    return True


async def _handle_trust_step(db, *, notifier, user: User) -> bool:
    """Any reply continues.

    The Telegram trust card has one button and no decline path — it is a
    promise, not a consent gate — so there is nothing here to refuse.
    """
    await onboarding_service.accept_trust(db, user.id)
    await _ask_asset(notifier, user)
    return True


async def _handle_asset_step(db, *, notifier, user: User, text: str) -> bool:
    demo_label = zalo_text("onboarding", "asset_demo_label")
    if demo_label and _norm(text) == _norm(demo_label):
        await _capture_asset(
            db,
            notifier=notifier,
            user=user,
            value=onboarding_service.DEMO_ASSET_VND,
            raw_text=None,
            demo=True,
        )
        return True

    value = onboarding_service.parse_asset_amount(text)
    if value is None:
        await _say(notifier, "asset_invalid", user)
        return True
    if value < onboarding_service.MIN_ASSET_VND:
        await _say(notifier, "asset_too_small", user)
        return True
    if value > onboarding_service.MAX_ASSET_VND:
        await _say(notifier, "asset_too_large", user)
        return True

    await _capture_asset(
        db, notifier=notifier, user=user, value=value, raw_text=text, demo=False
    )
    return True


async def _capture_asset(
    db,
    *,
    notifier,
    user: User,
    value: Decimal,
    raw_text: str | None,
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
    )
    await onboarding_service.set_first_asset(db, user.id, value, demo=demo)
    analytics.track(
        "zalo_onboarding_asset_captured",
        user_id=user.id,
        properties={"demo": demo},
    )
    await _say(notifier, "asset_demo_note" if demo else "asset_ack", user)
    await _send_twin(db, notifier=notifier, user=user, demo=demo)
    await _finish(db, notifier=notifier, user=user)


async def _finish(db, *, notifier, user: User) -> None:
    await onboarding_service.mark_completed(db, user.id)
    await legacy_onboarding_service.mark_completed(db, user.id)
    analytics.track("zalo_onboarding_completed", user_id=user.id)
    await _say(notifier, "done", user)
    await _maybe_invite_telegram(db, notifier=notifier, user=user)


# --------------------------------------------------------------------------
# Trust card
# --------------------------------------------------------------------------


def _load_trust_copy() -> dict[str, Any]:
    """Read the shared trust card.

    Loaded from the same YAML the Telegram card uses on purpose: it is a
    promise about the user's data, and a promise that reads differently
    per channel is a broken promise.
    """
    try:
        with open(_TRUST_COPY_PATH, encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except OSError:
        logger.exception("Zalo onboarding: trust card copy unreadable")
        return {}


async def _send_trust_card(db, *, notifier, user: User) -> None:
    copy = _load_trust_copy()
    header = (copy.get("header") or "").strip()
    body = (copy.get("body") or "").strip()
    bullets = copy.get("bullets") or []

    lines: list[str] = []
    if header:
        lines.append(header)
    if body:
        lines.append(body)
    for bullet in bullets:
        cleaned = _LEADING_ORNAMENT_RE.sub("", str(bullet).strip()).strip()
        if cleaned:
            lines.append(f"- {cleaned}")

    if not lines:
        # No card to show — don't strand the user on a step with no prompt.
        await _ask_asset(notifier, user)
        return

    label = zalo_text("onboarding", "trust_ok_label")
    await notifier.send_message(
        _ZALO_CHAT_ID, "\n".join(lines), buttons=_one_button(label)
    )
    await onboarding_service.mark_trust_shown(db, user.id)


async def _ask_asset(notifier, user: User) -> None:
    label = zalo_text("onboarding", "asset_demo_label")
    await _say(notifier, "ask_asset", user, buttons=_one_button(label))


# --------------------------------------------------------------------------
# Twin
# --------------------------------------------------------------------------


async def _send_twin(db, *, notifier, user: User, demo: bool) -> None:
    cone, base_year = await _resolve_cone(db, user, demo=demo)
    if not cone:
        await _say(notifier, "twin_failed", user)
        return

    point = max(cone, key=lambda p: int(p.get("year", 0)))
    salutation = onboarding_service.salutation_of(user)
    snapshot = TwinViewSnapshot(
        user_name=user.get_greeting_name(),
        target_year=base_year + int(point.get("year", 0)),
        p10=Decimal(str(point.get("p10", 0))),
        p50=Decimal(str(point.get("p50", 0))),
        p90=Decimal(str(point.get("p90", 0))),
        age_text="",
        cone=cone,
        salutation=salutation,
    )
    content = ZaloContentRenderer().render_twin_view(snapshot)
    await _send_content(notifier, content)
    await onboarding_service.mark_twin_shown(db, user.id)


async def _resolve_cone(db, user: User, *, demo: bool) -> tuple[list | None, int]:
    """Return ``(cone_points, base_year)`` — ``(None, 0)`` when unavailable.

    Imported locally to keep the twin stack out of the inbound import
    chain, matching ``onboarding_v2._resolve_twin_cone``.
    """
    if demo:
        from backend.twin.services import demo_twin_service

        return demo_twin_service.compute_demo_cone(), datetime.now(timezone.utc).year

    from backend.twin.services import twin_projection_service

    try:
        projections = await twin_projection_service.compute_and_store(
            db, user.id, scenario="current"
        )
    except Exception:
        logger.exception("Zalo onboarding: Twin projection failed for %s", user.id)
        return None, 0
    if not projections:
        return None, 0

    projection = projections[0]
    computed_at = getattr(projection, "computed_at", None)
    base_year = computed_at.year if computed_at else datetime.now(timezone.utc).year
    return projection.cone_data, base_year


async def _send_content(notifier, content: ChannelContent) -> None:
    if content.images:
        await notifier.send_photo(
            _ZALO_CHAT_ID,
            content.images[0],
            caption=content.text,
            filename=content.filename or "be-tien-twin.png",
        )
        return
    await notifier.send_message(_ZALO_CHAT_ID, content.text)


# --------------------------------------------------------------------------
# One-time Telegram invitation
# --------------------------------------------------------------------------


async def _maybe_invite_telegram(db, *, notifier, user: User) -> None:
    """Ask once whether they also want Bé Tiền on Telegram.

    Honest reason, honest refusal, never repeated. Zalo is reactive-first
    — the OA can only answer, never start — so a Zalo-only user gets no
    briefing and no nudge while they are quiet. That is the whole content
    of the ask; there is no urgency copy and no second chance.
    """
    if not zalo_linking_service.telegram_invite_pending(user):
        return

    url = (get_settings().telegram_bot_url or "").strip()
    if not url:
        # No link to offer. Staying silent keeps the one-time chance
        # unspent rather than burning it on a dead button.
        logger.info(
            "Zalo onboarding: telegram_bot_url unset, skipping invite for %s",
            user.id,
        )
        return

    body = zalo_text("onboarding", "telegram_invite", **_args(user))
    accept = zalo_text("onboarding", "telegram_invite_accept_label")
    decline = zalo_text("onboarding", "telegram_invite_decline_label")
    if not body or not accept or not decline:
        logger.warning("Zalo onboarding: telegram invite copy incomplete")
        return

    buttons = (
        (
            Button(text=accept, web_app_url=url),
            Button(text=decline),
        ),
    )
    sent = await notifier.send_message(_ZALO_CHAT_ID, body, buttons=buttons)
    if sent is None:
        # Blocked window or transport failure — the invitation never
        # arrived, so it must not count as having been shown.
        logger.info(
            "Zalo onboarding: telegram invite not delivered for %s, still pending",
            user.id,
        )
        return

    await zalo_linking_service.mark_telegram_invite_shown(db, user)
    analytics.track("zalo_telegram_invite_shown", user_id=user.id)


async def _handle_invite_answer(db, *, notifier, user: User, text: str) -> bool:
    """Record a refusal of the Telegram invitation, once."""
    if user.zalo_telegram_invite_at is None:
        return False
    if user.zalo_telegram_invite_response is not None:
        return False
    label = zalo_text("onboarding", "telegram_invite_decline_label")
    if not label or _norm(text) != _norm(label):
        return False

    await zalo_linking_service.record_telegram_invite_response(
        db, user, zalo_linking_service.INVITE_RESPONSE_DECLINED
    )
    await _say(notifier, "telegram_invite_declined", user)
    analytics.track("zalo_telegram_invite_declined", user_id=user.id)
    return True


# --------------------------------------------------------------------------
# Copy lookups (shared with the Telegram wizard)
# --------------------------------------------------------------------------


def _salutation_options() -> dict[str, str]:
    block = onboarding_service.load_copy().get("step_salutation") or {}
    buttons = block.get("buttons") or {}
    if not buttons:
        return {code: code for code in ALL_SALUTATIONS}
    return {str(code): str(label) for code, label in buttons.items()}


def _salutation_ack(code: str) -> str:
    block = onboarding_service.load_copy().get("step_salutation") or {}
    acks = block.get("acks") or {}
    return str(acks.get(code, "")).strip()


def _goal_block() -> dict[str, Any]:
    copy = onboarding_service.load_copy()
    if is_onboarding_reset_enabled():
        reset = copy.get("step_1_goal_reset")
        if reset:
            return reset
    return copy.get("step_1_goal") or {}


def _goal_options() -> dict[str, str]:
    block = _goal_block()
    buttons = block.get("buttons") or {}
    if not buttons:
        return {code: code for code in _DEFAULT_GOAL_ORDER}
    order = block.get("order") or list(buttons.keys())
    ordered = [code for code in order if code in buttons]
    ordered += [code for code in buttons if code not in ordered]
    return {str(code): str(buttons[code]) for code in ordered}


def _goal_ack(code: str) -> str:
    """Scan both goal blocks — a flag flipped mid-session must still ack."""
    copy = onboarding_service.load_copy()
    for name in _GOAL_COPY_BLOCKS:
        block = copy.get(name) or {}
        acks = block.get("goal_acks") or {}
        if code in acks:
            return str(acks[code]).strip()
    return ""
