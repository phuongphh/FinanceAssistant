"""Feature-click tracking for the Phase 4.2.5 admin dashboard.

Callers use ``record_feature_event`` in fire-and-forget mode. The service is
best-effort and never raises into user flows, matching ``backend.analytics``.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from backend.analytics import sanitize_properties
from backend.database import get_session_factory
from backend.models.feature_event import FeatureEvent

logger = logging.getLogger(__name__)

FEATURE_CATALOG: dict[str, str] = {
    "total_assets": "Tổng tài sản",
    "wealth_dashboard": "Dashboard tài sản",
    "wealth_trend": "Xu hướng tài sản",
    "morning_briefing": "Briefing sáng",
    "briefing_story": "Story trong briefing",
    "briefing_add_asset": "Thêm tài sản từ briefing",
    "briefing_settings": "Cài đặt briefing",
    "miniapp": "Mini App",
    "transaction": "Ghi chi tiêu",
    "transaction_category": "Đổi danh mục",
    "transaction_delete": "Xóa giao dịch",
    "receipt_ocr": "OCR hóa đơn",
    "voice_query": "Voice query",
    "goal": "Mục tiêu",
    "life_event": "Life event simulator",
    "cashflow": "Cashflow",
    "onboarding": "Onboarding",
    "storytelling": "Storytelling",
}

# Existing event stream → standardized feature keys. This mirrors many more
# than eight bot/Mini App handlers without touching each handler and keeps the
# mapping auditable in one catalog.
EVENT_TO_FEATURE_KEY: dict[str, str] = {
    "wealth_dashboard_viewed": "wealth_dashboard",
    "wealth_trend_viewed": "wealth_trend",
    "morning_briefing_opened": "morning_briefing",
    "briefing_dashboard_clicked": "wealth_dashboard",
    "briefing_story_clicked": "briefing_story",
    "briefing_add_asset_clicked": "briefing_add_asset",
    "briefing_settings_clicked": "briefing_settings",
    "miniapp_opened": "miniapp",
    "miniapp_loaded": "miniapp",
    "transaction_created": "transaction",
    "category_changed": "transaction_category",
    "transaction_deleted": "transaction_delete",
    "goal_wizard_opened": "goal",
    "goal_created": "goal",
    "life_event_wizard_opened": "life_event",
    "life_event_created": "life_event",
    "cashflow_tab_opened": "cashflow",
    "onboarding_v2_started": "onboarding",
    "storytelling_opened_direct": "storytelling",
}

_pending: set[asyncio.Task] = set()


def feature_name(feature_key: str) -> str:
    return FEATURE_CATALOG.get(feature_key, feature_key.replace("_", " ").title())


def feature_key_for_event(event_type: str, properties: dict[str, Any] | None = None) -> str | None:
    if event_type in EVENT_TO_FEATURE_KEY:
        return EVENT_TO_FEATURE_KEY[event_type]
    lowered = event_type.lower()
    if lowered.startswith("photo_receipt") or lowered.startswith("receipt_"):
        return "receipt_ocr"
    if lowered.startswith("voice_"):
        return "voice_query"
    if lowered.startswith("goal_"):
        return "goal"
    if lowered.startswith("life_event_"):
        return "life_event"
    if lowered.startswith("cashflow_"):
        return "cashflow"
    if lowered.startswith("onboarding_"):
        return "onboarding"
    if lowered.startswith("storytelling_"):
        return "storytelling"
    if properties and properties.get("feature_key") in FEATURE_CATALOG:
        return str(properties["feature_key"])
    return None


def record_feature_event(
    feature_key: str,
    *,
    user_id: uuid.UUID | None = None,
    tenant_id: int = 1,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a feature interaction asynchronously, swallowing failures."""
    clean_metadata = sanitize_properties(metadata)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(_persist(feature_key, user_id=user_id, tenant_id=tenant_id, metadata=clean_metadata))
        except Exception:
            logger.debug("feature event sync-write failed for %s", feature_key, exc_info=True)
        return

    task = loop.create_task(_persist(feature_key, user_id=user_id, tenant_id=tenant_id, metadata=clean_metadata))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _persist(
    feature_key: str,
    *,
    user_id: uuid.UUID | None,
    tenant_id: int,
    metadata: dict[str, Any],
) -> None:
    try:
        session_factory = get_session_factory()
    except Exception:
        logger.debug("feature events: no session factory available", exc_info=True)
        return

    try:
        async with session_factory() as session:
            session.add(
                FeatureEvent(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    feature_key=feature_key,
                    metadata_=metadata or None,
                )
            )
            await session.commit()
    except Exception:
        logger.warning("feature events: failed to persist %s", feature_key, exc_info=True)


async def flush_pending(timeout: float = 5.0) -> None:
    if _pending:
        await asyncio.wait(list(_pending), timeout=timeout)
