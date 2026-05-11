"""Telegram implementation of the channel-agnostic ContentRenderer port."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.bot.formatters.money import format_money_short
from backend.ports.content_renderer import (
    BriefingSnapshot,
    Button,
    ChannelContent,
    ContentRenderer,
    MilestoneSnapshot,
    TwinViewSnapshot,
)
from backend.twin.services.twin_chart_service import render_projection_chart

_COPY_PATH = Path(__file__).resolve().parents[2] / "content" / "twin_copy.yaml"


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def twin_view_buttons() -> tuple[tuple[Button, ...], ...]:
    """Default Telegram Twin action rows as channel-neutral buttons."""
    return (
        (Button("⚖️ So tối ưu", callback_data="menu:twin:compare_optimal"),),
        (Button("❓ Cách hoạt động", callback_data="menu:twin:how_it_works"),),
        (Button("◀️ Quay về Twin", callback_data="menu:twin"),),
    )


class TelegramContentRenderer(ContentRenderer):
    """Render Financial Twin content into Telegram-friendly copy and PNGs."""

    def __init__(self, chart_renderer=render_projection_chart):
        self._chart_renderer = chart_renderer

    def render_twin_view(self, snapshot: TwinViewSnapshot) -> ChannelContent:
        copy = _copy()["trajectory"]
        png = self._chart_renderer(snapshot.cone, optimal=snapshot.optimal_cone)
        caption = copy["caption"].format(
            name=snapshot.user_name,
            target_year=snapshot.target_year,
            p10=format_money_short(snapshot.p10),
            p50=format_money_short(snapshot.p50),
            p90=format_money_short(snapshot.p90),
            age_text=snapshot.age_text,
        )
        if snapshot.is_stale:
            caption += copy["stale_note"]
        if snapshot.narrative:
            caption = f"{caption}\n\n{snapshot.narrative}"
        return ChannelContent(
            text=caption[:1024],
            images=(png,),
            buttons=twin_view_buttons(),
            filename=snapshot.filename,
        )

    def render_briefing(self, snapshot: BriefingSnapshot) -> ChannelContent:
        return ChannelContent(text=snapshot.text, buttons=snapshot.buttons)

    def render_milestone(self, snapshot: MilestoneSnapshot) -> ChannelContent:
        return ChannelContent(text=snapshot.text, buttons=snapshot.buttons)
