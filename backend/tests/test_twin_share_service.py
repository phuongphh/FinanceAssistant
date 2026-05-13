"""Twin share service tests (Phase 4.1, Story B.1).

Cover the privacy contract (no absolute amounts in image bytes is
already enforced by the renderer; here we assert the service's data
shaping + error path) and the founding-badge branching.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.twin import twin_share_service


def _user(*, founding: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_founding_member=founding)


def _snapshot(cone):
    return SimpleNamespace(
        latest_cone=cone,
        projection=SimpleNamespace(cone_data=cone),
    )


@pytest.mark.asyncio
async def test_build_image_raises_when_no_projection():
    user = _user()
    with patch(
        "backend.services.twin.twin_share_service.twin_query_service.get_twin_snapshot",
        new=AsyncMock(return_value=_snapshot(None)),
    ):
        with pytest.raises(twin_share_service.TwinShareUnavailable):
            await twin_share_service.build_share_image_bytes(None, user=user)


@pytest.mark.asyncio
async def test_build_image_produces_png_bytes_starting_with_signature():
    cone = [
        {"year": 0, "p10": 90_000_000, "p50": 100_000_000, "p90": 110_000_000},
        {"year": 5, "p10": 200_000_000, "p50": 300_000_000, "p90": 450_000_000},
    ]
    user = _user(founding=True)
    with patch(
        "backend.services.twin.twin_share_service.twin_query_service.get_twin_snapshot",
        new=AsyncMock(return_value=_snapshot(cone)),
    ):
        png = await twin_share_service.build_share_image_bytes(None, user=user)
    # PNG magic number — proves we got a real image, not an HTML error.
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # Sanity: should be a non-trivial size (cone + badge + mascot).
    assert len(png) > 10_000


def test_feature_flag_default_on():
    os.environ.pop("TWIN_SHARE_ENABLED", None)
    assert twin_share_service.is_share_enabled() is True


def test_feature_flag_off_via_env():
    os.environ["TWIN_SHARE_ENABLED"] = "false"
    try:
        assert twin_share_service.is_share_enabled() is False
    finally:
        os.environ.pop("TWIN_SHARE_ENABLED", None)


def test_growth_pct_handles_zero_base():
    assert twin_share_service._growth_pct(Decimal("100"), Decimal("0")) == Decimal("0")


def test_growth_pct_positive():
    assert twin_share_service._growth_pct(
        Decimal("300"), Decimal("100")
    ) == Decimal("200")
