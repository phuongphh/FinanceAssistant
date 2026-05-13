"""ComputeMetricTool — diversification math + dispatch sanity.

Most metric helpers hit the DB so we focus on the diversification
score (pure-Python, deterministic) and the dispatch table."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.tools.compute_metric import (
    ComputeMetricTool,
    compute_diversification_score,
)
from backend.agent.tools.schemas import ComputeMetricInput, MetricName
from backend.wealth.services import net_worth_calculator


@pytest.mark.asyncio
class TestDiversificationScore:
    async def test_single_class_zero_score(self, monkeypatch):
        async def fake(_db, _uid):
            br = net_worth_calculator.NetWorthBreakdown()
            br.total = Decimal("100_000_000")
            br.by_type = {"cash": Decimal("100_000_000")}
            return br

        monkeypatch.setattr(net_worth_calculator, "calculate", fake)
        u = MagicMock()
        u.id = uuid.uuid4()
        result = await compute_diversification_score(MagicMock(), u, None)
        assert result.value == 0.0
        assert result.unit == "score"

    async def test_equal_weight_two_classes(self, monkeypatch):
        async def fake(_db, _uid):
            br = net_worth_calculator.NetWorthBreakdown()
            br.total = Decimal("200_000_000")
            br.by_type = {
                "cash": Decimal("100_000_000"),
                "stock": Decimal("100_000_000"),
            }
            return br

        monkeypatch.setattr(net_worth_calculator, "calculate", fake)
        u = MagicMock()
        u.id = uuid.uuid4()
        result = await compute_diversification_score(MagicMock(), u, None)
        # HHI = 2 * 0.5^2 = 0.5 → score = 50
        assert result.value == pytest.approx(50.0, abs=0.5)

    async def test_empty_returns_zero(self, monkeypatch):
        async def fake(_db, _uid):
            return net_worth_calculator.NetWorthBreakdown()

        monkeypatch.setattr(net_worth_calculator, "calculate", fake)
        u = MagicMock()
        u.id = uuid.uuid4()
        result = await compute_diversification_score(MagicMock(), u, None)
        assert result.value == 0.0


@pytest.mark.asyncio
class TestDispatch:
    async def test_unknown_metric_caught_at_validation(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ComputeMetricInput(metric_name="not_a_thing")

    async def test_dispatch_routes_correctly(self, monkeypatch):
        called = {"name": None}

        async def fake_div(_db, _user, _months):
            called["name"] = "diversification"
            return MagicMock(
                model_dump=lambda **_: {
                    "metric_name": "diversification_score",
                    "value": 0,
                    "unit": "score",
                    "period": "current",
                    "context": None,
                }
            )

        monkeypatch.setattr(
            "backend.agent.tools.compute_metric.compute_diversification_score",
            fake_div,
        )
        # Re-bind the dispatch table to pick up the patched function
        from backend.agent.tools import compute_metric as cm
        cm._DISPATCH[MetricName.DIVERSIFICATION_SCORE] = fake_div

        tool = ComputeMetricTool()
        await tool.execute(
            ComputeMetricInput(metric_name="diversification_score"),
            MagicMock(id=uuid.uuid4()),
            MagicMock(),
        )
        assert called["name"] == "diversification"
