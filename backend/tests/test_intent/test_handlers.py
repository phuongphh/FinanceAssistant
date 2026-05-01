"""Tests for the concrete intent handlers.

Exercises the response shape (Vietnamese tone, key facts present) +
empty-state behaviour. DB interactions are stubbed via the existing
fake-session pattern from test_asset_service.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.intents import IntentResult, IntentType


def _user(name: str = "An") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = name
    user.monthly_income = None
    return user


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _fake_asset(
    *,
    name: str = "VCB tiết kiệm",
    asset_type: str = "cash",
    current_value: Decimal = Decimal("100000000"),
    initial_value: Decimal | None = None,
    extra: dict | None = None,
) -> MagicMock:
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.name = name
    asset.asset_type = asset_type
    asset.subtype = None
    asset.current_value = current_value
    asset.initial_value = initial_value if initial_value is not None else current_value
    asset.extra = extra or {}
    asset.gain_loss_pct = (
        float(
            (Decimal(current_value) - Decimal(asset.initial_value))
            / Decimal(asset.initial_value)
            * 100
        )
        if asset.initial_value
        else None
    )
    return asset


# ---------------------- query_assets ----------------------


@pytest.mark.asyncio
async def test_query_assets_handler_lists_all_types():
    from backend.intent.handlers.query_assets import QueryAssetsHandler

    assets = [
        _fake_asset(name="VCB savings", asset_type="cash",
                    current_value=Decimal("80000000")),
        _fake_asset(name="VNM 100 cổ", asset_type="stock",
                    current_value=Decimal("4500000")),
        _fake_asset(name="Nhà Q1", asset_type="real_estate",
                    current_value=Decimal("3000000000")),
    ]
    with patch(
        "backend.intent.handlers.query_assets.asset_service.get_user_assets",
        AsyncMock(return_value=assets),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_ASSETS,
            confidence=0.95,
            raw_text="tài sản của tôi",
        )
        response = await QueryAssetsHandler().handle(intent, _user(), _fake_db())

    assert "Tài sản hiện tại của An" in response
    assert "VCB savings" in response
    assert "VNM" in response
    assert "Nhà Q1" in response
    # Net worth total in the header.
    assert "3,084,500,000" in response or "3,084" in response


@pytest.mark.asyncio
async def test_query_assets_handler_empty_state():
    from backend.intent.handlers.query_assets import QueryAssetsHandler

    with patch(
        "backend.intent.handlers.query_assets.asset_service.get_user_assets",
        AsyncMock(return_value=[]),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_ASSETS,
            confidence=0.95,
            raw_text="tài sản",
        )
        response = await QueryAssetsHandler().handle(intent, _user(), _fake_db())

    assert "chưa thêm tài sản" in response
    assert "/themtaisan" in response


# ---------------------- query_net_worth ----------------------


@pytest.mark.asyncio
async def test_query_net_worth_handler_includes_change_when_baseline_exists():
    from backend.intent.handlers.query_net_worth import QueryNetWorthHandler

    breakdown = MagicMock()
    breakdown.total = Decimal("500000000")
    breakdown.asset_count = 3

    change = MagicMock()
    change.previous = Decimal("450000000")
    change.change_absolute = Decimal("50000000")
    change.change_percentage = 11.11
    change.period_label = "tháng trước"

    with patch(
        "backend.intent.handlers.query_net_worth.net_worth_calculator.calculate",
        AsyncMock(return_value=breakdown),
    ), patch(
        "backend.intent.handlers.query_net_worth.net_worth_calculator.calculate_change",
        AsyncMock(return_value=change),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_NET_WORTH,
            confidence=0.95,
            raw_text="tổng tài sản",
        )
        response = await QueryNetWorthHandler().handle(intent, _user("An"), _fake_db())

    assert "500,000,000" in response
    assert "tháng trước" in response
    assert "📈" in response or "📉" in response


@pytest.mark.asyncio
async def test_query_net_worth_handler_zero_assets():
    from backend.intent.handlers.query_net_worth import QueryNetWorthHandler

    breakdown = MagicMock()
    breakdown.total = Decimal(0)

    with patch(
        "backend.intent.handlers.query_net_worth.net_worth_calculator.calculate",
        AsyncMock(return_value=breakdown),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_NET_WORTH,
            confidence=0.95,
            raw_text="tổng tài sản",
        )
        response = await QueryNetWorthHandler().handle(intent, _user(), _fake_db())

    assert "chưa có tài sản" in response


# ---------------------- query_portfolio ----------------------


@pytest.mark.asyncio
async def test_query_portfolio_handler_shows_positions_and_pnl():
    from backend.intent.handlers.query_portfolio import QueryPortfolioHandler

    stocks = [
        _fake_asset(
            name="VNM",
            asset_type="stock",
            current_value=Decimal("4500000"),
            initial_value=Decimal("4000000"),
            extra={"ticker": "VNM", "quantity": 100},
        ),
    ]
    with patch(
        "backend.intent.handlers.query_portfolio.asset_service.get_user_assets",
        AsyncMock(return_value=stocks),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_PORTFOLIO,
            confidence=0.95,
            raw_text="portfolio",
        )
        response = await QueryPortfolioHandler().handle(intent, _user(), _fake_db())

    assert "VNM" in response
    assert "100 cổ" in response
    # P&L was +12.5% so the green emoji should appear.
    assert "🟢" in response


@pytest.mark.asyncio
async def test_query_portfolio_empty_state():
    from backend.intent.handlers.query_portfolio import QueryPortfolioHandler

    with patch(
        "backend.intent.handlers.query_portfolio.asset_service.get_user_assets",
        AsyncMock(return_value=[]),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_PORTFOLIO,
            confidence=0.95,
            raw_text="portfolio",
        )
        response = await QueryPortfolioHandler().handle(intent, _user(), _fake_db())

    assert "chưa có cổ phiếu" in response


# ---------------------- query_market ----------------------


@pytest.mark.asyncio
async def test_query_market_handler_shows_price_and_personal_holding():
    from backend.intent.handlers.query_market import QueryMarketHandler

    snapshot = MagicMock()
    snapshot.price = 75000
    snapshot.change_1d_pct = 1.2

    holding = _fake_asset(
        name="VNM 100 cổ",
        asset_type="stock",
        current_value=Decimal("4500000"),
        extra={"ticker": "VNM", "quantity": 100},
    )

    handler = QueryMarketHandler()
    handler._latest_snapshot = AsyncMock(return_value=snapshot)
    handler._user_holding = AsyncMock(return_value=holding)

    intent = IntentResult(
        intent=IntentType.QUERY_MARKET,
        confidence=0.92,
        parameters={"ticker": "VNM"},
        raw_text="VNM giá",
    )
    response = await handler.handle(intent, _user(), _fake_db())

    assert "VNM" in response
    assert "75,000" in response
    assert "100" in response  # quantity
    assert "📈" in response


@pytest.mark.asyncio
async def test_query_market_handler_unknown_ticker():
    from backend.intent.handlers.query_market import QueryMarketHandler

    handler = QueryMarketHandler()
    handler._latest_snapshot = AsyncMock(return_value=None)
    handler._user_holding = AsyncMock(return_value=None)

    intent = IntentResult(
        intent=IntentType.QUERY_MARKET,
        confidence=0.92,
        parameters={"ticker": "FOO"},
        raw_text="FOO giá",
    )
    response = await handler.handle(intent, _user(), _fake_db())

    assert "chưa có dữ liệu" in response.lower() or "chưa hỗ trợ" in response.lower()


@pytest.mark.asyncio
async def test_query_market_handler_no_ticker():
    from backend.intent.handlers.query_market import QueryMarketHandler

    intent = IntentResult(
        intent=IntentType.QUERY_MARKET,
        confidence=0.85,
        parameters={},
        raw_text="giá",
    )
    response = await QueryMarketHandler().handle(intent, _user(), _fake_db())
    assert "VNM" in response or "BTC" in response


# ---------------------- query_goals + progress ----------------------


@pytest.mark.asyncio
async def test_query_goals_lists_with_progress_bars():
    from backend.intent.handlers.query_goals import QueryGoalsHandler

    goals = [
        MagicMock(goal_name="Mua xe", target_amount=Decimal("500000000"),
                  current_amount=Decimal("100000000"), deadline=None),
    ]
    with patch(
        "backend.intent.handlers.query_goals.goal_service.list_goals",
        AsyncMock(return_value=goals),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_GOALS, confidence=0.95, raw_text="mục tiêu"
        )
        response = await QueryGoalsHandler().handle(intent, _user(), _fake_db())

    assert "Mua xe" in response
    assert "20%" in response  # 100M / 500M


@pytest.mark.asyncio
async def test_query_goals_empty_state():
    from backend.intent.handlers.query_goals import QueryGoalsHandler

    with patch(
        "backend.intent.handlers.query_goals.goal_service.list_goals",
        AsyncMock(return_value=[]),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_GOALS, confidence=0.95, raw_text="mục tiêu"
        )
        response = await QueryGoalsHandler().handle(intent, _user(), _fake_db())

    assert "chưa đặt mục tiêu" in response


@pytest.mark.asyncio
async def test_query_goal_progress_finds_named_goal():
    from backend.intent.handlers.query_goals import QueryGoalProgressHandler

    goals = [
        MagicMock(goal_name="Mua xe", target_amount=Decimal("500000000"),
                  current_amount=Decimal("100000000"), deadline=date(2027, 12, 31)),
        MagicMock(goal_name="Mua nhà", target_amount=Decimal("3000000000"),
                  current_amount=Decimal("0"), deadline=None),
    ]
    with patch(
        "backend.intent.handlers.query_goals.goal_service.list_goals",
        AsyncMock(return_value=goals),
    ):
        intent = IntentResult(
            intent=IntentType.QUERY_GOAL_PROGRESS,
            confidence=0.95,
            parameters={"goal_name": "mua xe"},
            raw_text="mua xe cần bao nhiêu",
        )
        response = await QueryGoalProgressHandler().handle(intent, _user(), _fake_db())

    assert "Mua xe" in response
    assert "400" in response  # remaining = 400tr


# ---------------------- query_income ----------------------


@pytest.mark.asyncio
async def test_query_income_lists_streams():
    from backend.intent.handlers.query_income import QueryIncomeHandler

    streams = [
        MagicMock(source_type="salary", name="Lương FPT",
                  amount_monthly=Decimal("30000000")),
        MagicMock(source_type="dividend", name="Cổ tức VNM",
                  amount_monthly=Decimal("500000")),
    ]
    db = _fake_db()
    result_obj = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = streams
    result_obj.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result_obj)

    intent = IntentResult(
        intent=IntentType.QUERY_INCOME, confidence=0.95, raw_text="thu nhập"
    )
    response = await QueryIncomeHandler().handle(intent, _user(), db)

    assert "Lương FPT" in response
    assert "Cổ tức VNM" in response
    assert "30,500,000" in response


@pytest.mark.asyncio
async def test_query_income_falls_back_to_user_monthly_income():
    from backend.intent.handlers.query_income import QueryIncomeHandler

    db = _fake_db()
    result_obj = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    result_obj.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result_obj)

    user = _user()
    user.monthly_income = 25000000

    intent = IntentResult(
        intent=IntentType.QUERY_INCOME, confidence=0.95, raw_text="thu nhập"
    )
    response = await QueryIncomeHandler().handle(intent, user, db)
    assert "25,000,000" in response
