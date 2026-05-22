from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from backend.twin.services import causality_service
from infra.cache import causality_cache


def _projection(*, projection_id: int, computed_at: datetime, p50: Decimal) -> SimpleNamespace:
    return SimpleNamespace(
        id=projection_id,
        computed_at=computed_at,
        cone_data=[{"year": 1, "p50": str(p50)}],
    )


@pytest.mark.asyncio
async def test_attribute_delta_compares_latest_vs_immediately_previous():
    causality_cache.clear()
    now = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    projections = [
        _projection(projection_id=3, computed_at=now, p50=Decimal("100")),
        _projection(projection_id=2, computed_at=now.replace(hour=8), p50=Decimal("90")),
        _projection(projection_id=1, computed_at=now.replace(hour=7), p50=Decimal("150")),
    ]
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: projections))
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(causality_service, "_recent_factor_events", AsyncMock(return_value=[]))

    breakdown = await causality_service.attribute_delta(db, user_id="u-1")
    monkeypatch.undo()

    assert breakdown.direction == "positive"
    assert breakdown.delta_absolute_vnd == Decimal("10")


@pytest.mark.asyncio
async def test_attribute_delta_cache_key_changes_when_latest_projection_changes():
    causality_cache.clear()
    now = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    # Keep ``computed_at`` unchanged to reproduce DB timestamp truncation.
    first = [
        _projection(projection_id=11, computed_at=now, p50=Decimal("100")),
        _projection(projection_id=10, computed_at=now, p50=Decimal("90")),
    ]
    second = [
        _projection(projection_id=12, computed_at=now, p50=Decimal("80")),
        _projection(projection_id=11, computed_at=now, p50=Decimal("100")),
    ]

    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: first)),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: second)),
    ]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(causality_service, "_recent_factor_events", AsyncMock(return_value=[]))

    b1 = await causality_service.attribute_delta(db, user_id="u-2")
    b2 = await causality_service.attribute_delta(db, user_id="u-2")
    monkeypatch.undo()

    assert b1.direction == "positive"
    assert b2.direction == "negative"
