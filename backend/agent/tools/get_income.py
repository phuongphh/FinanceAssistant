"""``get_income`` tool — Phase 3.8 Epic 2 (Story P3.8-S6).

Wraps ``backend.wealth.services.income_service`` so the LLM can
answer questions about the user's income:

- "thu nhập của tôi"
- "thu nhập thụ động"        (filter is_passive=true)
- "thu nhập chủ động"        (filter is_passive=false)
- "thu nhập từ thuê BĐS"     (filter stream_type=rental)
- "lương tháng này của tôi"  (filter stream_type=salary)

Output shape mirrors ``GetAssetsOutput`` for consistency: a list of
items + headline aggregates so the formatter can render either a
detailed list or a one-liner without a second tool call.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Type

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.tools.base import Tool
from backend.agent.tools.schemas import (
    GetIncomeInput,
    GetIncomeOutput,
    IncomeStreamItem,
)
from backend.models.user import User
from backend.wealth.services import income_service


class GetIncomeTool(Tool):
    @property
    def name(self) -> str:
        return "get_income"

    @property
    def description(self) -> str:
        return (
            "Retrieve the user's income streams with optional filtering. "
            "Use this for ANY query about how much the user earns, what "
            "their income sources are, or active/passive split.\n"
            "\n"
            "Examples (Vietnamese query → tool call):\n"
            "- 'thu nhập của tôi' → no filter\n"
            "- 'thu nhập thụ động của tôi' → is_passive=true\n"
            "- 'thu nhập chủ động' → is_passive=false\n"
            "- 'thu nhập từ thuê BĐS' → stream_type='rental'\n"
            "- 'lương của tôi' → stream_type='salary'\n"
            "- 'cổ tức năm nay' → stream_type='dividend'\n"
            "- 'lãi tiết kiệm tháng này' → stream_type='interest'\n"
            "\n"
            "Output ``monthly_equivalent`` already normalises quarterly/"
            "annual streams to a monthly figure, so the user-facing "
            "answer can sum them without redoing the math."
        )

    @property
    def input_schema(self) -> Type[BaseModel]:
        return GetIncomeInput

    @property
    def output_schema(self) -> Type[BaseModel]:
        return GetIncomeOutput

    async def execute(
        self,
        input_data: GetIncomeInput,
        user: User,
        db: AsyncSession,
    ) -> GetIncomeOutput:
        # Filter at the DB layer — the partial index on
        # (user_id, stream_type, is_active) means this is a single
        # index scan even with both filters set.
        stream_type = (
            input_data.stream_type.value
            if input_data.stream_type is not None
            else None
        )
        streams = await income_service.get_active_streams(
            db, user.id,
            stream_type=stream_type,
            is_passive=input_data.is_passive,
            include_inactive=input_data.include_inactive,
        )

        items = [self._to_item(s) for s in streams]
        total_monthly = sum(
            (i.monthly_equivalent for i in items), Decimal(0)
        )
        active_income = sum(
            (i.monthly_equivalent for i in items if not i.is_passive),
            Decimal(0),
        )
        passive_income = sum(
            (i.monthly_equivalent for i in items if i.is_passive),
            Decimal(0),
        )
        passive_ratio: float | None
        if total_monthly <= 0:
            passive_ratio = None
        else:
            passive_ratio = float(passive_income / total_monthly * Decimal(100))

        return GetIncomeOutput(
            streams=items,
            total_monthly=total_monthly,
            active_income=active_income,
            passive_income=passive_income,
            passive_ratio=passive_ratio,
            count=len(items),
        )

    @staticmethod
    def _to_item(stream) -> IncomeStreamItem:
        return IncomeStreamItem(
            name=stream.name,
            stream_type=stream.stream_type,
            is_passive=stream.is_passive,
            amount=Decimal(stream.amount or 0),
            currency=stream.currency or "VND",
            schedule_type=stream.schedule_type,
            monthly_equivalent=stream.monthly_equivalent,
            is_active=stream.is_active,
            schedule_day=stream.schedule_day,
            schedule_month=stream.schedule_month,
        )
