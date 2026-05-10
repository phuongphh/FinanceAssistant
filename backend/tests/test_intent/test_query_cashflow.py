"""Tests for the cashflow handler (#126 wealth-aware composition)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.handlers.query_cashflow import QueryCashflowHandler
from backend.intent.intents import IntentResult, IntentType
from backend.intent.wealth_adapt import style_for_level
from backend.wealth.ladder import WealthLevel


def _user(name: str = "An") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = name
    user.monthly_income = None
    return user


def _fake_db_with_streams(streams: list) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = streams
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute.return_value = result
    return db


def _stream(amount_monthly: Decimal):
    """Phase 3.8 Epic 2: handler aggregates via ``monthly_equivalent``.
    Mock both the new property and the legacy field so tests stay
    decoupled from which name the handler currently uses."""
    s = MagicMock()
    s.monthly_equivalent = amount_monthly
    s.amount = amount_monthly
    s.amount_monthly = amount_monthly
    s.is_active = True
    return s


@pytest.mark.asyncio
async def test_starter_gets_simple_message_no_jargon():
    """Starter sees encouraging plain-Vietnamese, no savings rate %.

    Either positive ("dư") or negative ("vượt thu") wording is fine —
    the point is that the body has no % savings-rate row, no Thu/Chi
    breakdown table.
    """
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_CASHFLOW,
        confidence=0.9,
        parameters={"time_range": "last_month"},
        raw_text="tháng trước dư bao nhiêu",
    )

    db = _fake_db_with_streams([_stream(Decimal("15000000"))])
    style = style_for_level(WealthLevel.STARTER, Decimal("10000000"))

    expense = MagicMock()
    expense.amount = Decimal("3000000")

    with patch(
        "backend.intent.handlers.query_cashflow._fetch_expenses",
        AsyncMock(return_value=[expense]),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    body = response.split("\n\n")[0]
    assert "dư" in body.lower() or "vượt thu" in body.lower()
    # Starter must not see Thu/Chi breakdown or savings-rate percent.
    assert "%" not in body
    assert "Thu:" not in body


@pytest.mark.asyncio
async def test_mass_affluent_gets_savings_rate_breakdown():
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_CASHFLOW,
        confidence=0.9,
        parameters={"time_range": "this_month"},
        raw_text="cashflow",
    )
    db = _fake_db_with_streams([_stream(Decimal("60000000"))])
    style = style_for_level(WealthLevel.MASS_AFFLUENT, Decimal("500000000"))

    expenses = [MagicMock(amount=Decimal("20000000"))]
    with patch(
        "backend.intent.handlers.query_cashflow._fetch_expenses",
        AsyncMock(return_value=expenses),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    # MA shows breakdown + savings rate.
    assert "Thu" in response
    assert "Chi" in response
    assert "%" in response  # savings rate


@pytest.mark.asyncio
async def test_no_data_message():
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_CASHFLOW,
        confidence=0.9,
        parameters={"time_range": "this_month"},
        raw_text="cashflow",
    )
    db = _fake_db_with_streams([])
    style = style_for_level(WealthLevel.STARTER, Decimal("0"))

    with patch(
        "backend.intent.handlers.query_cashflow._fetch_expenses",
        AsyncMock(return_value=[]),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    assert "chưa có dữ liệu" in response.lower()

@pytest.mark.asyncio
async def test_cashflow_overview_splits_income_and_expense_cards():
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_CASHFLOW,
        confidence=1.0,
        parameters={"time_range": "this_month"},
        raw_text="[menu:cashflow:overview]",
    )
    salary = _stream(Decimal("30000000"))
    salary.stream_type = "salary"
    salary.name = "Lương"
    db = _fake_db_with_streams([salary])
    style = style_for_level(WealthLevel.MASS_AFFLUENT, Decimal("500000000"))

    food = MagicMock(amount=Decimal("2000000"), category="food")
    shopping = MagicMock(amount=Decimal("1000000"), category="shopping")
    with patch(
        "backend.intent.handlers.query_cashflow._fetch_expenses",
        AsyncMock(return_value=[food, shopping]),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    assert "💼 *Thu nhập tháng*" in response
    assert "💸 *Chi tiêu tháng*" in response
    assert "💎 *Tỷ lệ tiết kiệm*" in response
    assert "So sánh" not in response


@pytest.mark.asyncio
async def test_cashflow_current_month_detail_report():
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_CASHFLOW,
        confidence=1.0,
        parameters={"focus": "current_month_detail", "time_range": "this_month"},
        raw_text="[menu:cashflow:monthly_report]",
    )
    salary = _stream(Decimal("40000000"))
    salary.stream_type = "salary"
    salary.name = "Lương công ty"
    db = _fake_db_with_streams([salary])
    style = style_for_level(WealthLevel.MASS_AFFLUENT, Decimal("500000000"))

    tx1 = MagicMock(
        amount=Decimal("2500000"),
        category="food",
        merchant="Nhà hàng",
        expense_date=date.today().replace(day=3),
    )
    tx2 = MagicMock(
        amount=Decimal("7000000"),
        category="housing",
        merchant="Tiền nhà",
        expense_date=date.today().replace(day=5),
    )
    with patch(
        "backend.intent.handlers.query_cashflow._fetch_expenses",
        AsyncMock(return_value=[tx1, tx2]),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    assert "📅 *Dòng tiền tháng này*" in response
    assert "Net flow" in response
    assert "💼 *Top nguồn thu*" in response
    assert "💸 *Top nhóm chi*" in response
    assert "📈 *Nhịp chi tiêu theo ngày*" in response
    assert "🔎 *3 giao dịch lớn nhất*" in response
    assert "Tiền nhà" in response
