"""Tests for the advisory handler (Story #127)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.handlers.advisory import (
    ADVISORY_RATE_LIMIT_PER_DAY,
    AdvisoryHandler,
    DISCLAIMER,
)
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
    return db


def _stub_context():
    """Return patches that make the context builder return canned data —
    so tests don't need to mock 5 separate DB queries."""
    return [
        patch(
            "backend.intent.handlers.advisory.resolve_style",
            AsyncMock(
                return_value=MagicMock(
                    level=MagicMock(value="young_prof"),
                    net_worth=Decimal("100000000"),
                )
            ),
        ),
        patch(
            "backend.intent.handlers.advisory._format_breakdown",
            AsyncMock(return_value="cash: 100tr"),
        ),
        patch(
            "backend.intent.handlers.advisory._format_income",
            AsyncMock(return_value="20tr/tháng"),
        ),
        patch(
            "backend.intent.handlers.advisory._format_goals",
            AsyncMock(return_value="Mua xe (50tr/500tr)"),
        ),
        patch(
            "backend.intent.handlers.advisory._format_recent_spend",
            AsyncMock(return_value="ăn: 3tr"),
        ),
        patch(
            "backend.intent.handlers.advisory._advisory_calls_in_last_24h",
            AsyncMock(return_value=0),
        ),
    ]


@pytest.mark.asyncio
async def test_response_includes_legal_disclaimer():
    """Acceptance: disclaimer in 100% of responses."""
    user = _user()
    intent = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=0.9,
        raw_text="làm thế nào để đầu tư tiếp",
    )
    with patch(
        "backend.intent.handlers.advisory.call_llm",
        AsyncMock(return_value="Bạn có thể chia 30% vào quỹ ETF..."),
    ):
        with _patches(_stub_context()):
            response = await AdvisoryHandler().handle(intent, user, _fake_db())

    assert DISCLAIMER in response


@pytest.mark.asyncio
async def test_response_strips_duplicate_disclaimer_from_llm():
    """If the LLM ignores the prompt and adds its own disclaimer, we
    still emit only one — the canonical one we control."""
    user = _user()
    intent = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=0.9,
        raw_text="có nên mua VNM không",
    )
    llm_response = (
        "Mình nghĩ bạn nên cân nhắc đa dạng hóa.\n"
        "_Đây không phải lời khuyên đầu tư._"  # would be a duplicate
    )
    with patch(
        "backend.intent.handlers.advisory.call_llm",
        AsyncMock(return_value=llm_response),
    ):
        with _patches(_stub_context()):
            response = await AdvisoryHandler().handle(intent, user, _fake_db())

    assert response.count("không phải lời khuyên đầu tư") == 1


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold():
    user = _user("Bình")
    intent = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=0.9,
        raw_text="nên đầu tư gì",
    )

    # Patch the rate-limit helper to report user already at the cap.
    with patch(
        "backend.intent.handlers.advisory._advisory_calls_in_last_24h",
        AsyncMock(return_value=ADVISORY_RATE_LIMIT_PER_DAY),
    ), patch(
        "backend.intent.handlers.advisory.call_llm",
        AsyncMock(return_value="should not be called"),
    ) as mock_llm:
        response = await AdvisoryHandler().handle(intent, user, _fake_db())

    assert "Bình" in response
    assert "đến mai" in response.lower() or "mai" in response.lower()
    assert DISCLAIMER in response
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_llm_error_returns_friendly_message_with_disclaimer():
    user = _user()
    intent = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=0.9,
        raw_text="đầu tư crypto được không",
    )
    from backend.services.llm_service import LLMError

    with patch(
        "backend.intent.handlers.advisory.call_llm",
        AsyncMock(side_effect=LLMError("rate limit")),
    ):
        with _patches(_stub_context()):
            response = await AdvisoryHandler().handle(intent, user, _fake_db())

    assert "thử lại" in response.lower() or "nghĩ chưa ra" in response.lower()
    assert DISCLAIMER in response


@pytest.mark.asyncio
async def test_advisory_emits_response_event_on_success():
    """The rate limiter reads the events table — the handler must
    emit ``advisory_response_sent`` when it actually succeeds."""
    from backend import analytics

    captured: list[tuple] = []

    def _capture(event_type, user_id=None, properties=None):
        captured.append((event_type, properties))

    user = _user()
    intent = IntentResult(
        intent=IntentType.ADVISORY,
        confidence=0.9,
        raw_text="nên đầu tư gì",
    )
    original = analytics.track
    analytics.track = _capture
    try:
        with patch(
            "backend.intent.handlers.advisory.call_llm",
            AsyncMock(return_value="Một số option..."),
        ):
            with _patches(_stub_context()):
                await AdvisoryHandler().handle(intent, user, _fake_db())
    finally:
        analytics.track = original

    events = [evt[0] for evt in captured]
    assert "advisory_response_sent" in events


def test_disclaimer_text_signals_non_professional():
    """Acceptance: disclaimer must say 'không phải' something."""
    assert "không phải" in DISCLAIMER.lower()


def _patches(patch_list):
    """Helper — apply a list of patches as a single context manager."""
    from contextlib import ExitStack

    class _Stack:
        def __enter__(self_):
            self_.stack = ExitStack().__enter__()
            for p in patch_list:
                self_.stack.enter_context(p)
            return self_.stack

        def __exit__(self_, *exc):
            return self_.stack.__exit__(*exc)

    return _Stack()
