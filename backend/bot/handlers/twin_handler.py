"""Telegram surface for Phase 4A Financial Twin."""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.telegram_notifier import TelegramNotifier
from backend.bot.formatters.menu_formatter import back_to_main_keyboard
from backend.bot.formatters.money import format_money_short
from backend.config import get_settings
from backend.models.user import User
from backend.twin.services import twin_projection_service, twin_query_service
from backend.twin.services.twin_chart_service import render_projection_chart
from backend.twin.services.twin_narrative_service import build_twin_narrative

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_copy.yaml"
_MIN_TWIN_NET_WORTH = Decimal("10000000")


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _name(user: User) -> str:
    return user.get_greeting_name() if hasattr(user, "get_greeting_name") else (user.display_name or "bạn")


def _age_text(days: int | None) -> str:
    copy = _copy()["trajectory"]
    if not days:
        return copy["age_today"]
    return copy["age_days"].format(days=days)


def _target_point(cone: list[dict[str, Any]]) -> dict[str, Any]:
    if not cone:
        raise ValueError("cone must not be empty")
    return max(cone, key=lambda point: int(point.get("year", 0)))


def _trajectory_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "⚖️ So tối ưu", "callback_data": "menu:twin:compare_optimal"}],
            [{"text": "❓ Cách hoạt động", "callback_data": "menu:twin:how_it_works"}],
            [{"text": "◀️ Quay về Twin", "callback_data": "menu:twin"}],
        ]
    }


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
    notifier: TelegramNotifier | None = None,
) -> None:
    """Send current Financial Twin trajectory as PNG + caption."""
    notifier = notifier or TelegramNotifier()
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
        await notifier.send_message(chat_id, copy["trajectory"]["recomputing"], parse_mode=None)
        try:
            await twin_projection_service.compute_and_store(db, user.id, scenario="both")
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
    png = render_projection_chart(
        cone,
        optimal=optimal_projection.cone_data if optimal_projection else None,
    )
    narrative = await build_twin_narrative(
        db, user, cone, cone_age_days=snapshot.cone_age_days
    )
    caption = copy["trajectory"]["caption"].format(
        name=_name(user),
        target_year=point.get("year"),
        p10=format_money_short(Decimal(str(point.get("p10", 0)))),
        p50=format_money_short(Decimal(str(point.get("p50", 0)))),
        p90=format_money_short(Decimal(str(point.get("p90", 0)))),
        age_text=_age_text(snapshot.cone_age_days),
    )
    if snapshot.is_stale:
        caption += copy["trajectory"]["stale_note"]
    caption = f"{caption}\n\n{narrative}"
    await notifier.send_photo(
        chat_id,
        png,
        caption=caption[:1024],
        reply_markup=_trajectory_keyboard(),
        filename="be-tien-twin.png",
    )


async def send_twin_how_it_works(
    *, chat_id: int, notifier: TelegramNotifier | None = None
) -> None:
    notifier = notifier or TelegramNotifier()
    await notifier.send_message(
        chat_id,
        _copy()["how_it_works"],
        parse_mode=None,
        reply_markup=back_to_main_keyboard(),
    )


async def send_twin_miniapp_link(
    *, chat_id: int, notifier: TelegramNotifier | None = None
) -> None:
    notifier = notifier or TelegramNotifier()
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
        reply_markup={"inline_keyboard": [[{"text": copy["button"], "web_app": {"url": url}}]]},
    )


async def send_twin_compare_placeholder(
    *, chat_id: int, notifier: TelegramNotifier | None = None
) -> None:
    notifier = notifier or TelegramNotifier()
    await notifier.send_message(
        chat_id,
        "⚖️ So sánh tối ưu sẽ dùng lộ trình tiết kiệm +10% và tái cân bằng ở Epic 5. Hiện biểu đồ lộ trình đã kèm đường tối ưu tham khảo nếu có dữ liệu.",
        parse_mode=None,
        reply_markup=back_to_main_keyboard(),
    )
