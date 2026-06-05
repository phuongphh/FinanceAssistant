"""Tests for the cashflow handler (#126 wealth-aware composition)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.extractors.time_range import TimeRange
from backend.intent.handlers.query_cashflow import (
    QueryCashflowHandler,
    _income_for_period_from_streams,
    _strip_legacy_prefix,
    _top_income_sources,
)
from backend.intent.intents import IntentResult, IntentType
from backend.intent.wealth_adapt import style_for_level
from backend.wealth.ladder import WealthLevel

# 30-day window so ``amount * days / 30`` equals ``monthly_equivalent``
# exactly — keeps the assertions in TestTopIncomeSources easy to read.
_THIRTY_DAYS = TimeRange(
    start=date(2026, 4, 13),
    end=date(2026, 5, 12),
    label="this_month",
)


def _fetch_expenses_side_effect(expenses=None, money_in=None):
    """Return a side_effect for ``_fetch_expenses`` that routes by
    ``transaction_type`` so tests don't need to know call order."""
    expenses = expenses or []
    money_in = money_in or []

    async def _impl(db, user, *, start, end, category=None, transaction_type="expense"):
        if transaction_type == "money_in":
            return money_in
        return expenses

    return _impl


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
        new=AsyncMock(side_effect=_fetch_expenses_side_effect(expenses=[expense])),
    ), patch(
        "backend.intent.handlers.query_cashflow._recurring_expense_for_period",
        AsyncMock(return_value=Decimal("0")),
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
        new=AsyncMock(side_effect=_fetch_expenses_side_effect(expenses=expenses)),
    ), patch(
        "backend.intent.handlers.query_cashflow._recurring_expense_for_period",
        AsyncMock(return_value=Decimal("0")),
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
        new=AsyncMock(side_effect=_fetch_expenses_side_effect()),
    ), patch(
        "backend.intent.handlers.query_cashflow._recurring_expense_for_period",
        AsyncMock(return_value=Decimal("0")),
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
        new=AsyncMock(side_effect=_fetch_expenses_side_effect(expenses=[food, shopping])),
    ), patch(
        "backend.intent.handlers.query_cashflow._recurring_expense_for_period",
        AsyncMock(return_value=Decimal("500000")),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    assert (
        f"Dòng tiền tháng này tính đến hôm nay {date.today().strftime('%d/%m/%Y')}"
        in response
    )
    assert "💼 *Thu nhập tháng*" in response
    assert "💸 *Chi tiêu tháng*" in response
    assert "Chi tiêu hiện tại" in response
    assert "Chi phí định kì" in response
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
        new=AsyncMock(side_effect=_fetch_expenses_side_effect(expenses=[tx1, tx2])),
    ), patch(
        "backend.intent.handlers.query_cashflow._recurring_expense_for_period",
        AsyncMock(return_value=Decimal("3000000")),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    assert (
        f"📅 *Dòng tiền tháng này tính đến hôm nay {date.today().strftime('%d/%m/%Y')}*"
        in response
    )
    assert "Dư / thiếu" in response
    assert "Net flow" not in response
    assert "💼 *Top nguồn thu*" in response
    assert "💸 *Top nhóm chi*" in response
    assert "📈 *Nhịp chi tiêu theo ngày*" in response
    assert "🔎 *3 giao dịch lớn nhất*" in response
    assert "Chi tiêu hiện tại" in response
    assert "Chi phí định kì" in response
    assert "Tiền nhà" in response


@pytest.mark.asyncio
async def test_cashflow_overview_includes_money_in_card_and_correct_net():
    """Bug fix: money_in must show as a separate card AND be added to net
    (net = income + money_in - spend_total), not folded into expenses."""
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

    expense = MagicMock(amount=Decimal("10000000"), category="food")
    gift = MagicMock(amount=Decimal("2000000"), category="other", merchant="Bố cho")
    with patch(
        "backend.intent.handlers.query_cashflow._fetch_expenses",
        new=AsyncMock(
            side_effect=_fetch_expenses_side_effect(
                expenses=[expense], money_in=[gift]
            )
        ),
    ), patch(
        "backend.intent.handlers.query_cashflow._recurring_expense_for_period",
        AsyncMock(return_value=Decimal("0")),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    assert "💰 *Tiền vào tháng*" in response
    # Net = 30M income + 2M money_in - 10M spend = 22M dư
    assert "dư 22tr" in response.lower() or "22.000.000" in response


@pytest.mark.asyncio
async def test_cashflow_monthly_detail_shows_money_in_line():
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_CASHFLOW,
        confidence=1.0,
        parameters={"focus": "current_month_detail", "time_range": "this_month"},
        raw_text="[menu:cashflow:monthly_report]",
    )
    salary = _stream(Decimal("20000000"))
    salary.stream_type = "salary"
    salary.name = "Lương"
    db = _fake_db_with_streams([salary])
    style = style_for_level(WealthLevel.MASS_AFFLUENT, Decimal("500000000"))

    expense = MagicMock(
        amount=Decimal("5000000"),
        category="food",
        merchant="Nhà hàng",
        expense_date=date.today().replace(day=3),
    )
    gift = MagicMock(
        amount=Decimal("1000000"),
        category="other",
        merchant="Tìm trong ngăn bàn",
        expense_date=date.today().replace(day=2),
    )
    with patch(
        "backend.intent.handlers.query_cashflow._fetch_expenses",
        new=AsyncMock(
            side_effect=_fetch_expenses_side_effect(
                expenses=[expense], money_in=[gift]
            )
        ),
    ), patch(
        "backend.intent.handlers.query_cashflow._recurring_expense_for_period",
        AsyncMock(return_value=Decimal("0")),
    ), patch(
        "backend.intent.handlers.query_cashflow.resolve_style",
        AsyncMock(return_value=style),
    ):
        response = await QueryCashflowHandler().handle(intent, user, db)

    assert "Tiền vào:" in response


class TestIncomeForPeriodFromStreams:
    def test_monthly_fixed_income_uses_exact_amount_without_prorating(self):
        salary = _stream(Decimal("50000000"))
        salary.schedule_type = "monthly"
        rent = _stream(Decimal("10000000"))
        rent.schedule_type = "monthly"
        partial_month = TimeRange(
            start=date(2026, 5, 1), end=date(2026, 5, 15), label="this_month"
        )

        total = _income_for_period_from_streams(_user(), partial_month, [salary, rent])

        assert total == Decimal("60000000")

    def test_variable_non_monthly_income_keeps_existing_prorated_logic(self):
        bonus = _stream(Decimal("9000000"))
        bonus.schedule_type = "ad_hoc"
        ten_days = TimeRange(
            start=date(2026, 5, 1), end=date(2026, 5, 10), label="custom"
        )

        total = _income_for_period_from_streams(_user(), ten_days, [bonus])

        assert total == Decimal("3000000")


class TestStripLegacyPrefix:
    """``_strip_legacy_prefix`` removes the historical type prefix that
    ``rental_service`` baked into ``income_streams.name`` pre-PR #460."""

    def test_strips_legacy_thue_bds_prefix(self):
        assert _strip_legacy_prefix("Thuê BĐS — Nhà Mỹ Đình") == "Nhà Mỹ Đình"

    def test_strips_current_bds_cho_thue_prefix(self):
        assert _strip_legacy_prefix("BĐS cho thuê — Nhà Cầu Giấy") == "Nhà Cầu Giấy"

    def test_leaves_clean_name_untouched(self):
        assert _strip_legacy_prefix("Nhà Mỹ Đình") == "Nhà Mỹ Đình"

    def test_empty_string_is_safe(self):
        assert _strip_legacy_prefix("") == ""

    def test_non_matching_prefix_passes_through(self):
        # Defensive: handler must not eat similar-looking strings.
        assert _strip_legacy_prefix("Lương BĐS — abc") == "Lương BĐS — abc"


def _income_stream(stream_type: str, name: str, amount: Decimal) -> MagicMock:
    s = MagicMock()
    s.stream_type = stream_type
    s.name = name
    s.monthly_equivalent = amount
    return s


class TestTopIncomeSources:
    """``_top_income_sources`` composes the display string from
    ``income_types.yaml`` for auto-linked types so YAML edits propagate
    without touching DB rows."""

    def test_rental_renders_type_label_and_asset_name_from_yaml(self):
        stream = _income_stream("rental", "Nhà Mỹ Đình", Decimal("7_600_000"))
        result = _top_income_sources(
            [stream],
            time_range=_THIRTY_DAYS,
            limit=5,
        )
        assert len(result) == 1
        label, amount = result[0]
        # Auto-linked: prefix "BĐS cho thuê — " comes from YAML, not DB.
        assert label == "🏠 BĐS cho thuê — Nhà Mỹ Đình"
        assert amount == Decimal("7_600_000")

    def test_rental_with_legacy_prefix_is_normalised(self):
        # Pre-migration row still carries the historical prefix in DB.
        stream = _income_stream(
            "rental",
            "Thuê BĐS — Nhà Mỹ Đình",
            Decimal("7_600_000"),
        )
        result = _top_income_sources(
            [stream],
            time_range=_THIRTY_DAYS,
            limit=5,
        )
        label, _ = result[0]
        # The legacy prefix is stripped before YAML prefix is re-applied.
        assert label == "🏠 BĐS cho thuê — Nhà Mỹ Đình"
        assert "Thuê BĐS — " not in label

    def test_salary_keeps_user_supplied_name(self):
        stream = _income_stream(
            "salary",
            "Lương công ty ABC",
            Decimal("30_000_000"),
        )
        result = _top_income_sources(
            [stream],
            time_range=_THIRTY_DAYS,
            limit=5,
        )
        label, _ = result[0]
        # Non-auto-linked: user's raw name wins, type label is implicit.
        assert "Lương công ty ABC" in label
        assert label.startswith("💼")

    def test_rental_missing_asset_name_falls_back_to_type_label(self):
        stream = _income_stream("rental", "", Decimal("5_000_000"))
        result = _top_income_sources(
            [stream],
            time_range=_THIRTY_DAYS,
            limit=5,
        )
        label, _ = result[0]
        # Empty asset name: render just the type label, no trailing " — ".
        assert label == "🏠 BĐS cho thuê"
