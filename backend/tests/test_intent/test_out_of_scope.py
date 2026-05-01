"""Tests for the OOS bucket detector + handler."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.intent.handlers.out_of_scope import OutOfScopeHandler, detect_bucket
from backend.intent.intents import IntentResult, IntentType


@pytest.mark.parametrize(
    "text,expected",
    [
        ("thời tiết hôm nay thế nào", "weather"),
        ("trời mưa không", "weather"),
        ("kể chuyện cười đi", "entertainment"),
        ("hát cho tôi nghe", "entertainment"),
        ("AAPL giá bao nhiêu", "us_market"),
        ("thị trường Mỹ hôm nay", "us_market"),
        ("co phieu Mỹ tăng không", "us_market"),
        ("tôi có nên kết hôn không", "personal_advice"),
        ("ly hôn có nên không", "personal_advice"),
        ("thủ đô của Pháp", "general_knowledge"),
        ("ai là tổng thống Mỹ", "general_knowledge"),
        ("hôm nay là thứ mấy", "general"),  # default
    ],
)
def test_detect_bucket_routes_correctly(text, expected):
    assert detect_bucket(text) == expected


@pytest.mark.asyncio
async def test_handler_returns_bucket_specific_response():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "An"
    db = MagicMock()

    intent = IntentResult(
        intent=IntentType.OUT_OF_SCOPE,
        confidence=0.9,
        raw_text="thời tiết hôm nay thế nào",
    )
    response = await OutOfScopeHandler().handle(intent, user, db)
    # Weather bucket should mention weather + pivot to finance.
    assert "An" in response
    assert "tài chính" in response.lower() or "tài sản" in response.lower()


@pytest.mark.asyncio
async def test_handler_falls_back_to_general():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "An"
    db = MagicMock()

    intent = IntentResult(
        intent=IntentType.OUT_OF_SCOPE,
        confidence=0.9,
        raw_text="câu hỏi không liên quan gì cả",
    )
    response = await OutOfScopeHandler().handle(intent, user, db)
    assert "An" in response


@pytest.mark.asyncio
async def test_handler_logs_oos_analytics():
    """The OOS handler should fire ``intent_oos_declined`` for each
    decline so the admin metrics endpoint can graph categories."""
    from backend import analytics

    user = MagicMock()
    user.id = uuid.uuid4()
    user.display_name = "An"
    db = MagicMock()
    intent = IntentResult(
        intent=IntentType.OUT_OF_SCOPE,
        confidence=0.9,
        raw_text="thời tiết hôm nay",
    )

    captured: list[tuple] = []

    def _capture(event_type, user_id=None, properties=None):
        captured.append((event_type, properties))

    original = analytics.track
    analytics.track = _capture
    try:
        await OutOfScopeHandler().handle(intent, user, db)
    finally:
        analytics.track = original

    assert any(evt[0] == "intent_oos_declined" for evt in captured)
    declined = next(p for evt, p in captured if evt == "intent_oos_declined")
    assert declined["oos_category"] == "weather"
