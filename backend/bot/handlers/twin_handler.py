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
    # Delegate to the shared helper so the ``?b=<build_hash>`` cache-bust
    # query stays consistent across every Mini App entry point.
    from backend.miniapp.urls import twin_dashboard_url

    return twin_dashboard_url(source="telegram_twin")


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

    # Phase 4.1 Story B.2 — log snapshot per Twin open and (if enabled
    # + enough completed) append the honest hit-rate section to the
    # narrative. log_open_snapshot is best-effort; failures never
    # block the chart.
    from backend.services.twin import twin_calibration_service

    if snapshot.projection is not None:
        await twin_calibration_service.log_open_snapshot(
            db, user_id=user.id, projection=snapshot.projection
        )
    if twin_calibration_service.is_display_enabled():
        hit = await twin_calibration_service.get_hit_rate(db, user.id)
        if hit is not None:
            calib_copy = _copy().get("calibration", {})
            extra = (
                f"\n\n{calib_copy.get('section_title', '')}\n"
                + calib_copy.get("hit_line", "").format(
                    correct=hit.correct, total=hit.total, pct=hit.pct
                )
            )
            if hit.is_low_confidence:
                extra += "\n" + calib_copy.get("learning_note", "")
            narrative = (narrative or "") + extra

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
    await _maybe_send_next_action(db, chat_id, user, notifier)


async def _maybe_send_next_action(
    db: AsyncSession, chat_id: int, user: User, notifier: Notifier
) -> None:
    """Recompute activation CTA when the user opens Twin view."""
    from backend.models.onboarding_session import OnboardingSession
    from backend.services.onboarding import next_action_service

    session = await db.get(OnboardingSession, user.id)
    if (
        session is None
        or session.first_twin_shown_at is None
        or session.next_best_action_taken is not None
    ):
        return
    cta = await next_action_service.compute(db, user.id)
    await notifier.send_message(
        chat_id, cta.message_text, parse_mode="HTML", reply_markup=cta.reply_markup
    )


async def send_twin_share(
    db: AsyncSession,
    *,
    chat_id: int,
    user: User,
    notifier: Notifier | None = None,
) -> None:
    """Phase 4.1 Story B.1 — render and send the shareable Twin PNG.

    Privacy contract: the image contains NO absolute money amounts;
    only % growth + horizon. The caption nudges the user to share but
    Bé Tiền does NOT auto-post anywhere — user controls the share.
    """
    import logging

    from backend.services.twin import twin_share_service

    notifier = notifier or get_notifier()
    if not twin_share_service.is_share_enabled():
        await notifier.send_message(
            chat_id,
            _copy().get("share", {}).get(
                "disabled",
                "📸 Tính năng tạm tắt — quay lại sau bạn nhé.",
            ),
            parse_mode=None,
            reply_markup=back_to_main_keyboard(),
        )
        return
    try:
        png = await twin_share_service.build_share_image_bytes(db, user=user)
    except twin_share_service.TwinShareUnavailable:
        await notifier.send_message(
            chat_id,
            twin_share_service.get_unavailable_message(),
            parse_mode=None,
            reply_markup=back_to_main_keyboard(),
        )
        return
    except Exception:
        logging.getLogger(__name__).exception(
            "twin_share: render failed user=%s", user.id
        )
        await notifier.send_message(
            chat_id,
            twin_share_service.get_unavailable_message(),
            parse_mode=None,
            reply_markup=back_to_main_keyboard(),
        )
        return

    await notifier.send_photo(
        chat_id,
        png,
        caption=twin_share_service.get_caption(),
        reply_markup=back_to_main_keyboard(),
        filename="be-tien-twin-share.png",
    )


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
