"""Financial Twin read-intent handler."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.twin.services.twin_narrative_service import build_twin_narrative
from backend.twin.services.twin_query_service import get_twin_snapshot


class QueryTwinHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        snapshot = await get_twin_snapshot(db, user.id)
        if snapshot.projection is None or not snapshot.latest_cone:
            return "🔮 Mình chưa có dự phóng Twin cho bạn. Mở /menu → Bé Tiền tương lai để tạo bản đầu tiên nhé."
        point = max(snapshot.latest_cone, key=lambda p: int(p.get("year", 0)))
        narrative = await build_twin_narrative(
            db, user, snapshot.latest_cone, cone_age_days=snapshot.cone_age_days
        )
        return (
            "🔮 Bé Tiền tương lai\n\n"
            f"Năm {point.get('year')}, tài sản có thể nằm trong khoảng "
            f"{format_money_short(Decimal(str(point.get('p10', 0))))} — "
            f"{format_money_short(Decimal(str(point.get('p90', 0))))}.\n"
            f"Đường giữa P50: {format_money_short(Decimal(str(point.get('p50', 0))))}.\n\n"
            f"{narrative}\n\n"
            "Đây là mô phỏng xác suất, không phải dự đoán chắc chắn."
        )
