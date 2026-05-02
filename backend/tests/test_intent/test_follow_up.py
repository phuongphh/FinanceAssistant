"""Tests for the follow-up suggestion + callback layer (Story #128)."""
from __future__ import annotations

import pytest

from backend.intent.follow_up import (
    CALLBACK_PREFIX,
    MAX_SUGGESTIONS,
    FollowUp,
    build_inline_keyboard,
    get_follow_ups,
    parse_callback_data,
)
from backend.intent.intents import IntentType
from backend.wealth.ladder import WealthLevel


@pytest.mark.parametrize(
    "intent",
    [
        IntentType.QUERY_ASSETS,
        IntentType.QUERY_NET_WORTH,
        IntentType.QUERY_PORTFOLIO,
        IntentType.QUERY_EXPENSES,
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        IntentType.QUERY_INCOME,
        IntentType.QUERY_CASHFLOW,
        IntentType.QUERY_MARKET,
        IntentType.QUERY_GOALS,
        IntentType.QUERY_GOAL_PROGRESS,
    ],
)
def test_every_read_intent_has_at_least_three_suggestions(intent):
    """Acceptance: ≥3 suggestions per read intent (clipped at MAX)."""
    fus = get_follow_ups(intent)
    assert len(fus) >= 3 or len(fus) == MAX_SUGGESTIONS


def test_follow_ups_capped_at_three():
    fus = get_follow_ups(IntentType.QUERY_ASSETS)
    assert len(fus) <= MAX_SUGGESTIONS


def test_avoid_intent_filters_self_navigation():
    """avoid_intent drops suggestions that point back at the same intent."""
    fus = get_follow_ups(
        IntentType.QUERY_ASSETS, avoid_intent=IntentType.QUERY_ASSETS
    )
    for fu in fus:
        assert fu.intent != IntentType.QUERY_ASSETS


def test_starter_sees_beginner_overrides():
    """Starter gets the 'add asset' onboarding-style suggestions."""
    fus = get_follow_ups(
        IntentType.QUERY_ASSETS, wealth_level=WealthLevel.STARTER
    )
    labels = [fu.label for fu in fus]
    # Starter pool includes "Thêm tài sản" — beginner cue.
    assert any("Thêm tài sản" in l for l in labels)


def test_hnw_sees_advanced_overrides():
    """HNW gets analytics-first suggestions."""
    fus = get_follow_ups(
        IntentType.QUERY_NET_WORTH, wealth_level=WealthLevel.HIGH_NET_WORTH
    )
    labels = " ".join(fu.label for fu in fus).lower()
    assert "trend" in labels or "phân bổ" in labels


def test_callback_round_trips_intent_and_params():
    fu = FollowUp(
        label="🏠 BĐS",
        intent=IntentType.QUERY_ASSETS,
        parameters={"asset_type": "real_estate"},
    )
    encoded = fu.to_callback_data()
    assert encoded.startswith(CALLBACK_PREFIX)

    parsed = parse_callback_data(encoded)
    assert parsed is not None
    assert parsed.intent == IntentType.QUERY_ASSETS
    assert parsed.parameters == {"asset_type": "real_estate"}


def test_callback_handles_no_parameters():
    fu = FollowUp(label="Net worth", intent=IntentType.QUERY_NET_WORTH)
    encoded = fu.to_callback_data()
    parsed = parse_callback_data(encoded)
    assert parsed is not None
    assert parsed.intent == IntentType.QUERY_NET_WORTH
    assert parsed.parameters is None


def test_parse_returns_none_for_bad_payload():
    assert parse_callback_data("totally not a payload") is None
    assert parse_callback_data(f"{CALLBACK_PREFIX}!!!notbase64") is None


def test_callback_data_under_telegram_64_byte_limit():
    """Telegram caps callback_data at 64 bytes."""
    for fu in get_follow_ups(IntentType.QUERY_ASSETS):
        assert len(fu.to_callback_data().encode()) <= 64


def test_inline_keyboard_one_button_per_row():
    fus = get_follow_ups(IntentType.QUERY_NET_WORTH)
    kb = build_inline_keyboard(fus)
    assert kb is not None
    assert "inline_keyboard" in kb
    # One button per row — vertical stack.
    for row in kb["inline_keyboard"]:
        assert len(row) == 1


def test_empty_follow_ups_returns_none_keyboard():
    assert build_inline_keyboard([]) is None
