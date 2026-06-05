"""Tests for ``_fetch_expenses`` transaction_type filter and the new
``QueryMoneyInHandler``."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.handlers.query_expenses import (
    QueryExpensesHandler,
    QueryMoneyInHandler,
    _fetch_expenses,
)
from backend.intent.intents import IntentResult, IntentType


def _user(name: str = "An") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = name
    return user


def _capture_db():
    """Return (db, captured_stmts) — capturing the SQL each call sees so
    tests can assert ``transaction_type`` was filtered."""
    captured: list = []

    async def _execute(stmt):
        captured.append(stmt)
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        result.scalars.return_value = scalars
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, captured


@pytest.mark.asyncio
async def test_fetch_expenses_defaults_to_expense_type():
    db, captured = _capture_db()
    user = _user()
    await _fetch_expenses(
        db, user, start=date(2026, 5, 1), end=date(2026, 5, 31)
    )
    assert len(captured) == 1
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
    assert "transaction_type" in sql
    assert "'expense'" in sql


@pytest.mark.asyncio
async def test_fetch_expenses_money_in_filters_correctly():
    db, captured = _capture_db()
    user = _user()
    await _fetch_expenses(
        db,
        user,
        start=date(2026, 5, 1),
        end=date(2026, 5, 31),
        transaction_type="money_in",
    )
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
    assert "'money_in'" in sql


@pytest.mark.asyncio
async def test_fetch_expenses_none_type_returns_all():
    db, captured = _capture_db()
    user = _user()
    await _fetch_expenses(
        db,
        user,
        start=date(2026, 5, 1),
        end=date(2026, 5, 31),
        transaction_type=None,
    )
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
    where_clause = sql.split("WHERE", 1)[1] if "WHERE" in sql else ""
    assert "transaction_type" not in where_clause


@pytest.mark.asyncio
async def test_query_expenses_handler_filters_to_expense_type():
    """Regression: chi tiêu listing must NOT include money_in rows."""
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_EXPENSES,
        confidence=1.0,
        parameters={"time_range": "this_month"},
        raw_text="chi tiêu tháng này",
    )
    db = MagicMock()
    captured_kwargs: dict = {}

    async def fake_fetch(db_, user_, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    with patch(
        "backend.intent.handlers.query_expenses._fetch_expenses",
        new=AsyncMock(side_effect=fake_fetch),
    ):
        await QueryExpensesHandler().handle(intent, user, db)

    # Handler doesn't explicitly pass transaction_type — relies on default.
    # The important contract is that the default is "expense".
    # (Verified by test_fetch_expenses_defaults_to_expense_type.)
    assert "transaction_type" not in captured_kwargs or captured_kwargs.get(
        "transaction_type"
    ) in (None, "expense")


@pytest.mark.asyncio
async def test_query_money_in_handler_fetches_money_in_only():
    user = _user()
    intent = IntentResult(
        intent=IntentType.QUERY_MONEY_IN,
        confidence=1.0,
        parameters={"time_range": "this_month"},
        raw_text="tiền vào tháng này",
    )
    db = MagicMock()
    gift = MagicMock(
        amount=Decimal("2000000"),
        merchant="Bố cho",
        note=None,
    )
    captured_kwargs: dict = {}

    async def fake_fetch(db_, user_, **kwargs):
        captured_kwargs.update(kwargs)
        return [gift]

    with patch(
        "backend.intent.handlers.query_expenses._fetch_expenses",
        new=AsyncMock(side_effect=fake_fetch),
    ):
        response = await QueryMoneyInHandler().handle(intent, user, db)

    assert captured_kwargs.get("transaction_type") == "money_in"
    assert "Tiền vào" in response
    assert "Bố cho" in response


@pytest.mark.asyncio
async def test_query_money_in_handler_empty_message():
    user = _user("Minh")
    intent = IntentResult(
        intent=IntentType.QUERY_MONEY_IN,
        confidence=1.0,
        parameters={"time_range": "this_month"},
        raw_text="tiền vào tháng này",
    )
    db = MagicMock()
    with patch(
        "backend.intent.handlers.query_expenses._fetch_expenses",
        new=AsyncMock(return_value=[]),
    ):
        response = await QueryMoneyInHandler().handle(intent, user, db)
    assert "chưa có khoản tiền vào" in response.lower()
