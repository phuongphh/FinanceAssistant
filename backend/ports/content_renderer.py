"""Channel-agnostic content rendering contracts for user-facing flows.

Handlers and services prepare domain/read-model data, then a renderer turns it
into transport-neutral text, images, and buttons. Delivery adapters (Telegram
now, Zalo later) only translate this structure to their wire format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class Button:
    """A transport-neutral action button."""

    text: str
    callback_data: str | None = None
    web_app_url: str | None = None


@dataclass(frozen=True)
class ChannelContent:
    """Rendered content that can be delivered on any supported channel."""

    text: str
    images: tuple[bytes, ...] = field(default_factory=tuple)
    buttons: tuple[tuple[Button, ...], ...] = field(default_factory=tuple)
    filename: str | None = None


@dataclass(frozen=True)
class TwinViewSnapshot:
    """Read model needed to render a Twin trajectory view."""

    user_name: str
    target_year: int
    p10: Decimal
    p50: Decimal
    p90: Decimal
    age_text: str
    cone: list[dict[str, Any]]
    optimal_cone: list[dict[str, Any]] | None = None
    narrative: str = ""
    present_anchor: str = ""
    life_outcome: str = ""
    scenario_labels: dict[str, str] = field(default_factory=dict)
    is_stale: bool = False
    filename: str = "be-tien-twin.png"


@dataclass(frozen=True)
class TwinComparisonSnapshot:
    """Read model needed to render Current vs Optimal Twin comparison."""

    target_year: int
    current_p50: Decimal
    optimal_p50: Decimal
    delta_pct: str
    actions: str
    disclaimer: str
    current_cone: list[dict[str, Any]]
    optimal_cone: list[dict[str, Any]]
    filename: str = "be-tien-twin-optimal.png"


@dataclass(frozen=True)
class BriefingSnapshot:
    """Minimal briefing render model for channel renderers."""

    text: str
    buttons: tuple[tuple[Button, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MilestoneSnapshot:
    """Minimal milestone render model for channel renderers."""

    text: str
    buttons: tuple[tuple[Button, ...], ...] = field(default_factory=tuple)


class ContentRenderer(Protocol):
    """Port for rendering channel-ready content without sending it."""

    def render_twin_view(self, snapshot: TwinViewSnapshot) -> ChannelContent: ...

    def render_twin_comparison(
        self, snapshot: TwinComparisonSnapshot
    ) -> ChannelContent: ...

    def render_briefing(self, snapshot: BriefingSnapshot) -> ChannelContent: ...

    def render_milestone(self, snapshot: MilestoneSnapshot) -> ChannelContent: ...
