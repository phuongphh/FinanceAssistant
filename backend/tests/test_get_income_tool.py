"""Unit tests for ``backend.agent.tools.get_income.GetIncomeTool``.

Covers:
- Tool registration (default registry includes ``get_income``).
- Input filters pass through correctly to the service.
- Aggregations match what the service computes.
- Critical spec query: "thu nhập thụ động" → only passive types.
- Output schema includes the ``monthly_equivalent`` so the LLM
  formatter doesn't need to redo schedule math.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from backend.agent.tools import build_default_registry
from backend.agent.tools.get_income import GetIncomeTool
from backend.agent.tools.schemas import (
    GetIncomeInput,
    GetIncomeOutput,
    IncomeStreamType,
)
from backend.models.user import User
from backend.wealth.models.income_stream import IncomeStream


def _user() -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 1
    return u


def _stream(stream_type: str, amount: Decimal, schedule: str = "monthly", *, is_passive: bool, name: str = "x") -> IncomeStream:
    s = IncomeStream()
    s.id = uuid.uuid4()
    s.user_id = uuid.uuid4()
    s.stream_type = stream_type
    s.is_passive = is_passive
    s.name = name
    s.amount = amount
    s.currency = "VND"
    s.schedule_type = schedule
    s.start_date = date.today()
    s.is_active = True
    s.schedule_day = None
    s.schedule_month = None
    return s


class TestRegistration:
    def test_get_income_in_default_registry(self):
        r = build_default_registry()
        assert "get_income" in r.names()
        tool = r.get("get_income")
        assert isinstance(tool, GetIncomeTool)


@pytest.mark.asyncio
class TestExecute:
    async def test_no_filter_returns_all_streams(self):
        user = _user()
        salary = _stream("salary", Decimal("30000000"), is_passive=False, name="Lương")
        dividend = _stream("dividend", Decimal("12000000"), schedule="annually", is_passive=True, name="VNM")
        rental = _stream("rental", Decimal("13500000"), is_passive=True, name="Nhà 1")

        with patch(
            "backend.agent.tools.get_income.income_service.get_active_streams",
            new=AsyncMock(return_value=[salary, dividend, rental]),
        ):
            tool = GetIncomeTool()
            result = await tool.execute(GetIncomeInput(), user, db=None)

        assert isinstance(result, GetIncomeOutput)
        assert result.count == 3
        # 30tr + 1tr (12/12) + 13.5tr = 44.5tr
        assert result.total_monthly == Decimal("44500000")
        assert result.active_income == Decimal("30000000")
        assert result.passive_income == Decimal("14500000")  # 1tr + 13.5tr

    async def test_filter_passive_only_excludes_salary(self):
        """Spec § P3.8-S6 critical test:
            'thu nhập thụ động của tôi' → returns rental + dividend
            + interest only.
        """
        user = _user()
        rental = _stream("rental", Decimal("13500000"), is_passive=True)
        dividend = _stream("dividend", Decimal("10000000"), schedule="annually", is_passive=True)

        captured_kwargs = {}
        async def fake_get_active_streams(db, user_id, **kwargs):
            captured_kwargs.update(kwargs)
            return [rental, dividend]

        with patch(
            "backend.agent.tools.get_income.income_service.get_active_streams",
            new=fake_get_active_streams,
        ):
            tool = GetIncomeTool()
            result = await tool.execute(
                GetIncomeInput(is_passive=True), user, db=None,
            )

        # Filter pushdown — service was called with is_passive=True.
        assert captured_kwargs.get("is_passive") is True
        assert result.count == 2
        for item in result.streams:
            assert item.is_passive is True

    async def test_filter_by_stream_type(self):
        """'thu nhập từ thuê BĐS' → stream_type='rental'."""
        user = _user()
        rental = _stream("rental", Decimal("13500000"), is_passive=True, name="Nhà Mỹ Đình")

        captured_kwargs = {}
        async def fake_get_active_streams(db, user_id, **kwargs):
            captured_kwargs.update(kwargs)
            return [rental]

        with patch(
            "backend.agent.tools.get_income.income_service.get_active_streams",
            new=fake_get_active_streams,
        ):
            tool = GetIncomeTool()
            result = await tool.execute(
                GetIncomeInput(stream_type=IncomeStreamType.RENTAL),
                user, db=None,
            )

        assert captured_kwargs.get("stream_type") == "rental"
        assert result.count == 1

    async def test_empty_user_passive_ratio_is_none(self):
        user = _user()
        with patch(
            "backend.agent.tools.get_income.income_service.get_active_streams",
            new=AsyncMock(return_value=[]),
        ):
            tool = GetIncomeTool()
            result = await tool.execute(GetIncomeInput(), user, db=None)
        assert result.count == 0
        assert result.passive_ratio is None

    async def test_stream_type_label_is_vietnamese(self):
        """Issue #927 — every income item must carry a Vietnamese
        ``stream_type_label`` derived from income_types YAML."""
        from backend.wealth import income_types as _income_types

        user = _user()
        salary = _stream("salary", Decimal("30000000"), is_passive=False)
        rental = _stream("rental", Decimal("13500000"), is_passive=True)
        with patch(
            "backend.agent.tools.get_income.income_service.get_active_streams",
            new=AsyncMock(return_value=[salary, rental]),
        ):
            tool = GetIncomeTool()
            result = await tool.execute(GetIncomeInput(), user, db=None)

        labels = {s.stream_type: s.stream_type_label for s in result.streams}
        assert labels["salary"] == _income_types.get_label("salary")
        assert labels["rental"] == _income_types.get_label("rental")
        # Whatever the YAML returns, it must NOT be the raw English code.
        assert labels["salary"] != "salary"
        assert labels["rental"] != "rental"

    async def test_monthly_equivalent_in_output(self):
        """Output items carry the normalised monthly figure so the
        LLM formatter doesn't need to redo schedule math."""
        user = _user()
        annual_dividend = _stream(
            "dividend", Decimal("12000000"), schedule="annually",
            is_passive=True, name="Cổ tức",
        )
        with patch(
            "backend.agent.tools.get_income.income_service.get_active_streams",
            new=AsyncMock(return_value=[annual_dividend]),
        ):
            tool = GetIncomeTool()
            result = await tool.execute(GetIncomeInput(), user, db=None)
        assert result.streams[0].amount == Decimal("12000000")
        assert result.streams[0].monthly_equivalent == Decimal("1000000")


class TestToolDescription:
    def test_description_lists_at_least_5_examples(self):
        """Phase 3.7 / 3.8 convention: tool descriptions live or die
        on the example count. Spec § P3.8-S6 requires 5+."""
        tool = GetIncomeTool()
        desc = tool.description
        # Each example line starts with "- '"
        example_count = desc.count("- '")
        assert example_count >= 5, (
            f"Got {example_count} examples; need ≥5 for LLM accuracy"
        )
