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
    TwinComparisonSnapshot,
    TwinViewSnapshot,
)
from backend.twin.services.twin_chart_service import render_projection_chart

_COPY_PATH = Path(__file__).resolve().parents[2] / "content" / "twin_copy.yaml"


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def twin_view_buttons() -> tuple[tuple[Button, ...], ...]:
    """Default Telegram Twin action rows as channel-neutral buttons.

    The "📸 Lưu thành ảnh" row (Phase 4.1 Story B.1) is gated by the
    ``TWIN_SHARE_ENABLED`` env flag. When off, the row disappears so
    users never see a button that would error.
    """
    from backend.services.twin.twin_share_service import is_share_enabled

    rows: list[tuple[Button, ...]] = []
    if is_share_enabled():
        share_label = _copy().get("share", {}).get("button", "📸 Lưu thành ảnh")
        rows.append((Button(share_label, callback_data="menu:twin:share"),))
    rows.extend(
        [
            (Button("⚖️ So tối ưu", callback_data="menu:twin:compare_optimal"),),
            (Button("❓ Cách hoạt động", callback_data="menu:twin:how_it_works"),),
            (Button("◀️ Quay về Twin", callback_data="menu:twin:view_current"),),
        ]
    )
    return tuple(rows)


class TelegramContentRenderer(ContentRenderer):
    """Render Financial Twin content into Telegram-friendly copy and PNGs."""

    def __init__(self, chart_renderer=render_projection_chart):
        self._chart_renderer = chart_renderer

    def render_twin_view(self, snapshot: TwinViewSnapshot) -> ChannelContent:
        copy = _copy()["trajectory"]
        png = self._chart_renderer(snapshot.cone, optimal=snapshot.optimal_cone)
        labels = snapshot.scenario_labels or {}
        caption = copy["caption"].format(
            name=snapshot.user_name,
            target_year=snapshot.target_year,
            p10=format_money_short(snapshot.p10),
            p50=format_money_short(snapshot.p50),
            p90=format_money_short(snapshot.p90),
            p10_label=labels.get("p10", "🌧️ Khiêm tốn"),
            p50_label=labels.get("p50", "⛅ Bình thường"),
            p90_label=labels.get("p90", "☀️ Lạc quan"),
            age_text=snapshot.age_text,
        )
        card_lines = self._scenario_card_lines(snapshot.scenario_cards)
        if card_lines:
            caption = f"{caption}\n\n{card_lines}"
        if snapshot.present_anchor:
            caption = f"{snapshot.present_anchor}\n\n{caption}"
        if snapshot.life_outcome:
            caption += f"\n\n⛅ Ví dụ dễ hình dung: {snapshot.life_outcome}"
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

    @staticmethod
    def _scenario_card_lines(cards: list[dict[str, Any]]) -> str:
        """Render the three weather cards as Telegram-safe text.

        Telegram captions cannot embed three independent image cards next to the
        chart, so this keeps the card semantics visible and relies on each
        card's emoji fallback when mascot images are unavailable.
        """
        if not cards:
            return ""
        personality = {
            "p10": "áo mưa sẵn sàng, ưu tiên giữ an toàn",
            "p50": "cầm dù vừa đủ, đi đều và cân bằng",
            "p90": "đeo kính nắng, tận dụng nhịp thuận lợi",
        }
        lines = ["Ba sắc thái Bé Tiền trong vùng dự phóng:"]
        for card in cards[:3]:
            p_code = str(card.get("p_code") or "").lower()
            label = card.get("label") or card.get("p_code") or ""
            amount = format_money_short(card.get("amount") or 0)
            detail = personality.get(p_code)
            if not detail:
                mascot = card.get("mascot") or {}
                detail = mascot.get("mood") or "giữ nhịp phù hợp"
            lines.append(f"• {label} — khoảng {amount}: {detail}.")
        return "\n".join(lines)

    def render_twin_comparison(
        self, snapshot: TwinComparisonSnapshot
    ) -> ChannelContent:
        copy = _copy()["comparison"]
        png = self._chart_renderer(snapshot.current_cone, optimal=snapshot.optimal_cone)
        caption = copy["caption"].format(
            target_year=snapshot.target_year,
            current_p50=format_money_short(snapshot.current_p50),
            optimal_p50=format_money_short(snapshot.optimal_p50),
            delta_pct=snapshot.delta_pct,
            actions=snapshot.actions,
            disclaimer=snapshot.disclaimer,
        )
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
