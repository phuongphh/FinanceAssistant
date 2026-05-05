"""GetTransactionsTool tests — filter / sort / amount-range / limit."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.tools.get_transactions import GetTransactionsTool
from backend.agent.tools.schemas import (
    GetTransactionsInput,
    NumericFilter,
    TransactionFilter,
)
from backend.models.expense import Expense


def _expense(*, day, amount, category="food", merchant="X") -> Expense:
    return Expense(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        amount=Decimal(amount),
        currency="VND",
        merchant=merchant,
        category=category,
        source="manual",
        expense_date=day,
        month_key=day.strftime("%Y-%m"),
        note=None,
        raw_data=None,
        needs_review=False,
        gmail_message_id=None,
    )


def _mock_db(rows: list[Expense]) -> MagicMock:
    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    return db


def _user():
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


@pytest.mark.asyncio
class TestGetTransactions:
    async def test_basic_listing_default_sort(self):
        rows = [
            _expense(day=date(2026, 5, 1), amount=50_000),
            _expense(day=date(2026, 5, 3), amount=30_000),
            _expense(day=date(2026, 5, 2), amount=80_000),
        ]
        # Pre-ordered as SQL would (date desc).
        rows_sorted = sorted(rows, key=lambda r: r.expense_date, reverse=True)
        tool = GetTransactionsTool()
        out = await tool.execute(
            GetTransactionsInput(),
            _user(),
            _mock_db(rows_sorted),
        )
        assert out.count == 3
        # date_desc default ⇒ rows ordered 5/3, 5/2, 5/1.
        assert [t.date for t in out.transactions] == [
            date(2026, 5, 3),
            date(2026, 5, 2),
            date(2026, 5, 1),
        ]
        assert [t.amount for t in out.transactions] == [
            Decimal(30_000),
            Decimal(80_000),
            Decimal(50_000),
        ]

    async def test_amount_filter_applied_after_db(self):
        rows = [
            _expense(day=date(2026, 5, 3), amount=2_000_000),
            _expense(day=date(2026, 5, 2), amount=500_000),
            _expense(day=date(2026, 5, 1), amount=1_500_000),
        ]
        tool = GetTransactionsTool()
        out = await tool.execute(
            GetTransactionsInput(
                filter=TransactionFilter(amount=NumericFilter(gt=1_000_000))
            ),
            _user(),
            _mock_db(rows),
        )
        amounts = [int(t.amount) for t in out.transactions]
        assert amounts == [2_000_000, 1_500_000]

    async def test_amount_desc_sort(self):
        rows = [
            _expense(day=date(2026, 5, 1), amount=100_000),
            _expense(day=date(2026, 5, 2), amount=900_000),
            _expense(day=date(2026, 5, 3), amount=300_000),
        ]
        tool = GetTransactionsTool()
        out = await tool.execute(
            GetTransactionsInput(sort="amount_desc", limit=2),
            _user(),
            _mock_db(rows),
        )
        assert [int(t.amount) for t in out.transactions] == [900_000, 300_000]

    async def test_total_amount_aggregates(self):
        rows = [
            _expense(day=date(2026, 5, 1), amount=100_000),
            _expense(day=date(2026, 5, 2), amount=200_000),
        ]
        tool = GetTransactionsTool()
        out = await tool.execute(
            GetTransactionsInput(),
            _user(),
            _mock_db(rows),
        )
        assert out.total_amount == Decimal(300_000)
