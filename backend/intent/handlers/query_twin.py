"""Financial Twin read-intent handler."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.clarity import render_clarity_block
from backend.bot.formatters.money import format_money_short
from backend.intent.handlers.base import IntentHandler
from backend.intent.handlers.decision_flags import is_clarity_meter_enabled
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.services.decision import clarity_service
from backend.twin.services.twin_narrative_service import build_twin_narrative
from backend.twin.services.twin_query_service import get_twin_snapshot


class QueryTwinHandler(IntentHandler):
    async def handle(self, intent: IntentResult, user: User, db: AsyncSession) -> str:
        # Độ Nét meter (Phase 4.5, #3.2–3.4): gated at this handler edge so the
        # env read never reaches a service. Computed once and threaded into
        # every branch below — including the no-projection state, where knowing
        # the picture is blurry is exactly what makes the humble copy honest.
        clarity_line = ""
        if is_clarity_meter_enabled():
            result = await clarity_service.compute_clarity(db, user.id)
            clarity_line = "\n\n" + render_clarity_block(result)

        snapshot = await get_twin_snapshot(db, user.id)
        if snapshot.projection is None or not snapshot.latest_cone:
            return (
                "🔮 Mình chưa có dự phóng Twin cho bạn. Mở /menu → Bé Tiền "
                "tương lai để tạo bản đầu tiên nhé." + clarity_line
            )
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
            "Đây là mô phỏng xác suất, không phải dự đoán chắc chắn." + clarity_line
        )
