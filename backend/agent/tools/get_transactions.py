"""``get_transactions`` tool — filter / sort / limit on user expenses.

Wraps ``backend.services.expense_service.list_expenses``. The
underlying service supports month + category filters at SQL level;
date-range and amount-range filtering happens in Python because it's
a tiny dataset (≤200 rows post-limit) and keeps this layer thin.
"""
from __future__ import annotations

import uuid
from datetime import date as date_cls
from decimal import Decimal
from typing import Iterable, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.get_assets import _matches_numeric
from backend.agent.tools.schemas import (
    GetTransactionsInput,
    GetTransactionsOutput,
    TransactionFilter,
    TransactionItem,
)
from backend.models.expense import Expense
from backend.models.user import User

_DEFAULT_LIMIT = 50
# Hard cap pulled from DB before in-Python filtering so we don't
# silently drop rows that should match. 1k is generous for a
# personal-CFO use case (a single user with >1000 transactions in a
# month is an outlier we'd handle differently anyway).
_DB_FETCH_CAP = 1000


class GetTransactionsTool(Tool):
    @property
    def name(self) -> str:
        return "get_transactions"

    @property
    def description(self) -> str:
        return (
            "Retrieve the user's expense transactions with optional "
            "filtering and sorting. Use for queries about past spending.\n"
            "\n"
            "Examples:\n"
            "- 'chi tiêu tháng này' → filter={date_from: <month-start>, "
            "date_to: <today>}\n"
            "- 'chi cho ăn uống tuần này' → "
            "filter={category:'food', date_from:<week-start>, date_to:<today>}\n"
            "- 'giao dịch trên 1 triệu' → filter={amount:{gt:1000000}}\n"
            "- 'top 5 chi tiêu lớn nhất tháng này' → "
            "filter={date_from:..., date_to:...}, sort='amount_desc', limit=5\n"
            "- '10 giao dịch gần nhất' → sort='date_desc', limit=10"
        )

    @property
    def input_schema(self) -> Type:
        return GetTransactionsInput

    @property
    def output_schema(self) -> Type:
        return GetTransactionsOutput

    async def execute(
        self,
        input_data: GetTransactionsInput,
        user: User,
        db: AsyncSession,
    ) -> GetTransactionsOutput:
        rows = await self._fetch(db, user.id, input_data.filter)
        items = [self._to_item(r) for r in rows]
        items = list(self._apply_python_filters(items, input_data.filter))
        items = self._apply_sort(items, input_data.sort)
        if input_data.limit is not None:
            items = items[: input_data.limit]
        else:
            items = items[:_DEFAULT_LIMIT]

        total = sum((i.amount for i in items), start=Decimal(0))
        return GetTransactionsOutput(
            transactions=items, total_amount=total, count=len(items)
        )

    # ------------------------------------------------------------------

    async def _fetch(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        filt: TransactionFilter | None,
    ) -> list[Expense]:
        """Pre-filter via SQL where we can — category + date range.

        Going direct to a SELECT instead of ``list_expenses`` because
        the existing helper takes a ``month`` string but we want a
        free date-range. Both paths hit the same indexed columns so
        the cost is identical."""
        stmt = select(Expense).where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
        )
        if filt:
            if filt.category:
                stmt = stmt.where(Expense.category == filt.category.value)
            if filt.date_from:
                stmt = stmt.where(Expense.expense_date >= filt.date_from)
            if filt.date_to:
                stmt = stmt.where(Expense.expense_date <= filt.date_to)
        # Pre-sort newest-first so default ordering is sensible even
        # before ``_apply_sort`` runs. The sort cap (_DB_FETCH_CAP)
        # also makes the eventual top-N query cheap.
        stmt = stmt.order_by(Expense.expense_date.desc()).limit(_DB_FETCH_CAP)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    def _apply_python_filters(
        self, items: list[TransactionItem], filt: TransactionFilter | None
    ) -> Iterable[TransactionItem]:
        if not filt or not filt.amount:
            return items
        return [
            i for i in items if _matches_numeric(float(i.amount), filt.amount)
        ]

    def _apply_sort(
        self, items: list[TransactionItem], sort: str | None
    ) -> list[TransactionItem]:
        if sort is None or sort == "date_desc":
            return items  # already newest-first from SQL
        if sort == "date_asc":
            return sorted(items, key=lambda i: i.date)
        if sort == "amount_desc":
            return sorted(items, key=lambda i: i.amount, reverse=True)
        if sort == "amount_asc":
            return sorted(items, key=lambda i: i.amount)
        return items

    @staticmethod
    def _to_item(row: Expense) -> TransactionItem:
        return TransactionItem(
            date=row.expense_date if isinstance(row.expense_date, date_cls)
            else date_cls.today(),
            merchant=row.merchant,
            category=row.category,
            amount=Decimal(row.amount or 0),
            note=row.note,
        )
