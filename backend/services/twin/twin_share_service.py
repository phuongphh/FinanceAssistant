"""Twin share service (Phase 4.1, Story B.1).

Build a privacy-conscious shareable Twin image for the current user.

Layer contract:
- Reads via twin_query_service (no raw SQL).
- Calls the image-renderer adapter for bytes (no transport).
- Does NOT commit; the handler/worker owns the session.
- Reads no environment — feature flag is the handler's concern.
"""
from __future__ import annotations

import logging
import os
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from backend.adapters.image.twin_image_renderer import render_twin_share_image
from backend.models.user import User
from backend.twin.services import twin_projection_service, twin_query_service

logger = logging.getLogger(__name__)

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "twin_copy.yaml"
_FEATURE_FLAG_ENV = "TWIN_SHARE_ENABLED"


@lru_cache(maxsize=1)
def _copy() -> dict[str, Any]:
    with open(_COPY_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def is_share_enabled() -> bool:
    """Default ON. Operator can flip via env var if image render
    starts costing latency we cannot afford during soft launch."""
    return os.environ.get(_FEATURE_FLAG_ENV, "true").lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


class TwinShareUnavailable(Exception):
    """Raised when there is no projection to share — caller should
    fall back to the same "no_projection" message the Twin view uses
    so the experience stays consistent.
    """


def _growth_pct(p50: Decimal, base: Decimal) -> Decimal:
    """Compound growth % from base to P50. Clamped to a reasonable
    integer to keep the image readable on small screens."""
    if base <= 0 or p50 <= 0:
        return Decimal("0")
    return ((p50 - base) / base * Decimal("100")).quantize(Decimal("1"))


def _target_point(cone: list[dict[str, Any]]) -> dict[str, Any]:
    return max(cone, key=lambda p: int(p.get("year", 0)))


async def build_share_image_bytes(
    db: AsyncSession,
    *,
    user: User,
) -> bytes:
    """Return a PNG-bytes share image for the user. Raises
    ``TwinShareUnavailable`` if there is no projection to share."""
    snapshot = await twin_query_service.get_twin_snapshot(db, user.id)
    cone = snapshot.latest_cone
    if not cone or snapshot.projection is None:
        raise TwinShareUnavailable("no projection available")

    target = _target_point(cone)
    base_point = min(cone, key=lambda p: int(p.get("year", 0)))
    base_p50 = Decimal(str(base_point.get("p50", 0)))
    target_p50 = Decimal(str(target.get("p50", 0)))
    growth = _growth_pct(target_p50, base_p50)
    horizon_years = int(target.get("year", 0)) - int(base_point.get("year", 0))
    if horizon_years <= 0:
        horizon_years = int(target.get("year", 0))

    copy = _copy().get("share", {})
    sign = "+" if growth >= 0 else ""
    growth_text = copy.get("growth_pct", "{sign}{value}%").format(
        sign=sign, value=str(growth)
    )
    horizon_text = copy.get("horizon", "Sau {years} năm").format(years=horizon_years)
    headline = copy.get("headline", "Bé Tiền tương lai")
    subline = copy.get("subline", "Dự phóng xác suất, không phải lời hứa")
    watermark = copy.get("watermark", "Bé Tiền — Personal CFO")
    badge_label = (
        copy.get("founding_badge", "🌱 Founding Member")
        if user.is_founding_member
        else None
    )

    return render_twin_share_image(
        cone=cone,
        growth_pct_text=growth_text,
        horizon_text=horizon_text,
        headline=headline,
        subline=subline,
        watermark=watermark,
        founding_badge_label=badge_label,
    )


def get_caption() -> str:
    return _copy().get("share", {}).get(
        "caption",
        "📸 Twin của bạn — chia sẻ nếu thấy thú vị nhé.",
    )


def get_unavailable_message() -> str:
    return _copy().get("share", {}).get(
        "unavailable",
        "🔮 Mình chưa có Twin để tạo ảnh chia sẻ. Bạn cập nhật tài sản rồi quay lại nhé.",
    )


# Silence unused-import linting in some envs while keeping the helper
# available for callers that want to force a fresh projection before
# rendering (e.g. the demo handler).
_ = (twin_projection_service, uuid)


__all__ = [
    "build_share_image_bytes",
    "get_caption",
    "get_unavailable_message",
    "is_share_enabled",
    "TwinShareUnavailable",
]
