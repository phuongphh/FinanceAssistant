"""Telegram surface for Phase 4A Financial Twin."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.menu_formatter import back_to_main_keyboard
from backend.bot.formatters.money import format_money_short
from backend.ports.content_renderer import (
    Button,
    ChannelContent,
    ContentRenderer,
    TwinComparisonSnapshot,
    TwinViewSnapshot,
)
from backend.ports.notifier import Notifier, get_notifier
from backend.adapters.telegram_content_renderer import TelegramContentRenderer
from backend.config import get_settings
from backend.models.user import User
from backend.twin.allocation.target_allocation import (
    get_allocation_disclaimer,
    top_rebalance_deltas,
)
from backend.twin.services import twin_projection_service, twin_query_service
from backend.twin.services.twin_narrative_service import build_twin_narrative
from backend.twin.services.twin_chart_service import render_projection_chart

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_copy.yaml"
_MIN_TWIN_NET_WORTH = Decimal("10000000")


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _name(user: User) -> str:
    return (
        user.get_greeting_name()
        if hasattr(user, "get_greeting_name")
        else (user.display_name or "bạn")
    )


def _age_text(days: int | None) -> str:
    copy = _copy()["trajectory"]
    if not days:
        return copy["age_today"]
    return copy["age_days"].format(days=days)


def _target_point(cone: list[dict[str, Any]]) -> dict[str, Any]:
    if not cone:
        raise ValueError("cone must not be empty")
    return max(cone, key=lambda point: int(point.get("year", 0)))


def _telegram_reply_markup(buttons: tuple[tuple[Button, ...], ...]) -> dict | None:
    if not buttons:
        return None
    inline_keyboard = []
    for row in buttons:
        rendered_row = []
        for button in row:
            payload: dict[str, Any] = {"text": button.text}
            if button.web_app_url:
                payload["web_app"] = {"url": button.web_app_url}
            elif button.callback_data:
                payload["callback_data"] = button.callback_data
            rendered_row.append(payload)
        if rendered_row:
            inline_keyboard.append(rendered_row)
    return {"inline_keyboard": inline_keyboard} if inline_keyboard else None


async def _send_channel_content(
    notifier: Notifier, chat_id: int, content: ChannelContent
) -> None:
    reply_markup = _telegram_reply_markup(content.buttons)
    if content.images:
        await notifier.send_photo(
            chat_id,
            content.images[0],
            caption=content.text,
            reply_markup=reply_markup,
            filename=content.filename or "be-tien-content.png",
        )
        return
    await notifier.send_message(
        chat_id, content.text, parse_mode=None, reply_markup=reply_markup
    )


def _miniapp_url() -> str | None:
    base = (get_settings().miniapp_base_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}/miniapp/twin?source=telegram_twin"


async def send_twin_current(
    db: AsyncSession,
    *,
    chat_id: int,
    user: User,
    notifier: Notifier | None = None,
    renderer: ContentRenderer | None = None,
) -> None:
    """Send current Financial Twin trajectory as rendered channel content."""
    notifier = notifier or get_notifier()
    renderer = renderer or TelegramContentRenderer(
        chart_renderer=render_projection_chart
    )
    copy = _copy()
    snapshot = await twin_query_service.get_twin_snapshot(db, user.id)
    if snapshot.actual_nw < _MIN_TWIN_NET_WORTH:
        await notifier.send_message(
            chat_id,
            copy["trajectory"]["empty_state"],
            parse_mode=None,
            reply_markup=back_to_main_keyboard(),
        )
        return

    if snapshot.projection is None:
        await notifier.send_message(
            chat_id, copy["trajectory"]["recomputing"], parse_mode=None
        )
        try:
            await twin_projection_service.compute_and_store(
                db, user.id, scenario="both"
            )
            snapshot = await twin_query_service.get_twin_snapshot(db, user.id)
        except Exception:
            await notifier.send_message(
                chat_id,
                copy["trajectory"]["no_projection"],
                parse_mode=None,
                reply_markup=back_to_main_keyboard(),
            )
            return

    cone = snapshot.latest_cone or []
    point = _target_point(cone)
    optimal_projection = await twin_query_service.get_latest_projection(
        db, user.id, scenario=twin_projection_service.SCENARIO_OPTIMAL
    )
    narrative = await build_twin_narrative(
        db, user, cone, cone_age_days=snapshot.cone_age_days
    )
    content = renderer.render_twin_view(
        TwinViewSnapshot(
            user_name=_name(user),
            target_year=int(point.get("year", 0)),
            p10=Decimal(str(point.get("p10", 0))),
            p50=Decimal(str(point.get("p50", 0))),
            p90=Decimal(str(point.get("p90", 0))),
            age_text=_age_text(snapshot.cone_age_days),
            cone=cone,
            optimal_cone=optimal_projection.cone_data if optimal_projection else None,
            narrative=narrative,
            is_stale=snapshot.is_stale,
            filename="be-tien-twin.png",
        )
    )
    await _send_channel_content(notifier, chat_id, content)


async def send_twin_how_it_works(
    *, chat_id: int, notifier: Notifier | None = None
) -> None:
    notifier = notifier or get_notifier()
    await notifier.send_message(
        chat_id,
        _copy()["how_it_works"],
        parse_mode=None,
        reply_markup=back_to_main_keyboard(),
    )


async def send_twin_miniapp_link(
    *, chat_id: int, notifier: Notifier | None = None
) -> None:
    notifier = notifier or get_notifier()
    copy = _copy()["miniapp"]
    url = _miniapp_url()
    if not url:
        await notifier.send_message(
            chat_id,
            copy["not_configured"],
            parse_mode=None,
            reply_markup=back_to_main_keyboard(),
        )
        return
    await notifier.send_message(
        chat_id,
        copy["open_text"],
        parse_mode=None,
        reply_markup={
            "inline_keyboard": [[{"text": copy["button"], "web_app": {"url": url}}]]
        },
    )


def _pct(value: Decimal | int | float | str) -> str:
    pct = Decimal(str(value)) * Decimal("100")
    return str(pct.quantize(Decimal("1")))


def _delta_pct(current: Decimal, optimal: Decimal) -> str:
    if current <= 0:
        return "+0%"
    raw = ((optimal - current) / current * Decimal("100")).quantize(Decimal("1"))
    sign = "+" if raw >= 0 else ""
    return f"{sign}{raw}%"


def _action_lines(current_projection: Any, optimal_projection: Any) -> str:
    copy = _copy()["comparison"]
    labels = _copy().get("asset_labels", {})
    actions = [
        copy["action_savings"].format(
            current_savings=format_money_short(
                Decimal(str(current_projection.monthly_savings))
            ),
            optimal_savings=format_money_short(
                Decimal(str(optimal_projection.monthly_savings))
            ),
        )
    ]
    deltas = top_rebalance_deltas(
        current_projection.allocation_snapshot or {},
        optimal_projection.allocation_snapshot or {},
        base_net_worth=current_projection.base_net_worth,
        limit=2,
    )
    for delta in deltas:
        template_key = (
            "action_rebalance_add"
            if delta.delta_weight > 0
            else "action_rebalance_trim"
        )
        actions.append(
            copy[template_key].format(
                asset_label=labels.get(delta.asset_class, delta.asset_class),
                current_pct=_pct(delta.current_weight),
                target_pct=_pct(delta.target_weight),
                amount=format_money_short(abs(delta.amount_delta)),
            )
        )
    if len(actions) == 1:
        actions.append(copy["action_hold"])
    return "\n".join(actions[:3])


async def send_twin_compare_optimal(
    db: AsyncSession,
    *,
    chat_id: int,
    user: User,
    notifier: Notifier | None = None,
    renderer: ContentRenderer | None = None,
) -> None:
    """Send Current vs Optimal dual-cone comparison."""
    notifier = notifier or get_notifier()
    renderer = renderer or TelegramContentRenderer(
        chart_renderer=render_projection_chart
    )
    copy = _copy()["comparison"]
    current = await twin_query_service.get_latest_projection(
        db, user.id, scenario=twin_projection_service.SCENARIO_CURRENT
    )
    optimal = await twin_query_service.get_latest_projection(
        db, user.id, scenario=twin_projection_service.SCENARIO_OPTIMAL
    )
    if current is None or optimal is None:
        await notifier.send_message(chat_id, copy["recomputing"], parse_mode=None)
        try:
            await twin_projection_service.compute_and_store(
                db, user.id, scenario="both"
            )
            current = await twin_query_service.get_latest_projection(
                db, user.id, scenario=twin_projection_service.SCENARIO_CURRENT
            )
            optimal = await twin_query_service.get_latest_projection(
                db, user.id, scenario=twin_projection_service.SCENARIO_OPTIMAL
            )
        except Exception:
            await notifier.send_message(
                chat_id,
                copy["no_projection"],
                parse_mode=None,
                reply_markup=back_to_main_keyboard(),
            )
            return

    if (
        current is None
        or optimal is None
        or not current.cone_data
        or not optimal.cone_data
    ):
        await notifier.send_message(
            chat_id,
            copy["no_projection"],
            parse_mode=None,
            reply_markup=back_to_main_keyboard(),
        )
        return

    current_point = _target_point(current.cone_data)
    optimal_point = _target_point(optimal.cone_data)
    current_p50 = Decimal(str(current_point.get("p50", 0)))
    optimal_p50 = Decimal(str(optimal_point.get("p50", 0)))
    content = renderer.render_twin_comparison(
        TwinComparisonSnapshot(
            target_year=int(current_point.get("year", 0)),
            current_p50=current_p50,
            optimal_p50=optimal_p50,
            delta_pct=_delta_pct(current_p50, optimal_p50),
            actions=_action_lines(current, optimal),
            disclaimer=get_allocation_disclaimer(),
            current_cone=current.cone_data,
            optimal_cone=optimal.cone_data,
            filename="be-tien-twin-optimal.png",
        )
    )
    await _send_channel_content(notifier, chat_id, content)
