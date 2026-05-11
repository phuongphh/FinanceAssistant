"""Zalo renderer stub for Phase 5+ channel expansion."""

from __future__ import annotations

from backend.ports.content_renderer import (
    BriefingSnapshot,
    ChannelContent,
    ContentRenderer,
    MilestoneSnapshot,
    TwinComparisonSnapshot,
    TwinViewSnapshot,
)


class ZaloContentRenderer(ContentRenderer):
    """Intentional stub: Zalo adapter will be wired in Phase 5+."""

    def render_twin_view(self, snapshot: TwinViewSnapshot) -> ChannelContent:
        # TODO(phase-5): map Twin ChannelContent to Zalo Mini Program/OA format.
        raise NotImplementedError("Zalo Twin rendering is planned for Phase 5+")

    def render_twin_comparison(
        self, snapshot: TwinComparisonSnapshot
    ) -> ChannelContent:
        # TODO(phase-5): map comparison charts to Zalo Mini Program/OA format.
        raise NotImplementedError(
            "Zalo Twin comparison rendering is planned for Phase 5+"
        )

    def render_briefing(self, snapshot: BriefingSnapshot) -> ChannelContent:
        # TODO(phase-5): map briefing cards to Zalo OA messages.
        raise NotImplementedError("Zalo briefing rendering is planned for Phase 5+")

    def render_milestone(self, snapshot: MilestoneSnapshot) -> ChannelContent:
        # TODO(phase-5): map milestone cards to Zalo OA messages.
        raise NotImplementedError("Zalo milestone rendering is planned for Phase 5+")
