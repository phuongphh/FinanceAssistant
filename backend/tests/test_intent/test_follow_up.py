"""Tests for the follow-up suggestion + callback layer (Story #128)."""
from __future__ import annotations

import pytest

from backend.config.categories import get_all_categories
from backend.intent.follow_up import (
    CALLBACK_PREFIX,
    MAX_SUGGESTIONS,
    FollowUp,
    build_category_picker_keyboard,
    build_inline_keyboard,
    get_follow_ups,
    is_category_picker_callback,
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
    assert any("Thêm tài sản" in label for label in labels)


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


def test_gold_market_follow_up_routes_portfolio_to_gold_assets():
    fus = get_follow_ups(
        IntentType.QUERY_MARKET,
        parameters={"category": "gold"},
        avoid_intent=IntentType.QUERY_MARKET,
    )

    assert fus[0].label == "💼 Portfolio của tôi"
    assert fus[0].intent == IntentType.QUERY_PORTFOLIO
    assert fus[0].parameters == {"asset_type": "gold"}

    parsed = parse_callback_data(fus[0].to_callback_data())
    assert parsed is not None
    assert parsed.intent == IntentType.QUERY_PORTFOLIO
    assert parsed.parameters == {"asset_type": "gold"}


def test_crypto_market_follow_up_routes_portfolio_to_crypto_assets():
    fus = get_follow_ups(
        IntentType.QUERY_MARKET,
        parameters={"category": "crypto"},
        avoid_intent=IntentType.QUERY_MARKET,
    )

    assert fus[0].label == "💼 Portfolio của tôi"
    assert fus[0].intent == IntentType.QUERY_PORTFOLIO
    assert fus[0].parameters == {"asset_type": "crypto"}


def test_stock_market_follow_up_routes_portfolio_to_stock_assets():
    fus = get_follow_ups(
        IntentType.QUERY_MARKET,
        parameters={"category": "stocks"},
        avoid_intent=IntentType.QUERY_MARKET,
    )

    assert fus[0].label == "💼 Portfolio của tôi"
    assert fus[0].intent == IntentType.QUERY_PORTFOLIO
    assert fus[0].parameters == {"asset_type": "stock"}


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


def test_assets_follow_up_month_vs_previous_routes_net_worth_with_param():
    fus = get_follow_ups(IntentType.QUERY_ASSETS)
    month_button = next(f for f in fus if f.label == "📈 So với tháng trước")
    assert month_button.intent == IntentType.QUERY_NET_WORTH
    assert month_button.parameters == {"time_range": "month_vs_previous"}


def test_hnw_ytd_follow_up_routes_net_worth_with_ytd_param():
    fus = get_follow_ups(IntentType.QUERY_ASSETS, wealth_level=WealthLevel.HIGH_NET_WORTH)
    ytd_button = next(f for f in fus if "YTD - Tài sản từ đầu năm đến nay" in f.label)
    assert ytd_button.intent == IntentType.QUERY_NET_WORTH
    assert ytd_button.parameters == {"time_range": "ytd"}

    parsed = parse_callback_data(ytd_button.to_callback_data())
    assert parsed is not None
    assert parsed.intent == IntentType.QUERY_NET_WORTH
    assert parsed.parameters == {"time_range": "ytd"}


@pytest.mark.parametrize("level", [
    None,
    WealthLevel.STARTER,
    WealthLevel.MASS_AFFLUENT,
    WealthLevel.HIGH_NET_WORTH,
    WealthLevel.VIP,
])
def test_assets_follow_up_has_ytd_button_for_all_wealth_levels(level):
    kwargs = {} if level is None else {"wealth_level": level}
    fus = get_follow_ups(IntentType.QUERY_ASSETS, **kwargs)
    ytd_button = next(f for f in fus if "YTD - Tài sản từ đầu năm đến nay" in f.label)
    assert ytd_button.intent == IntentType.QUERY_NET_WORTH
    assert ytd_button.parameters == {"time_range": "ytd"}


@pytest.mark.parametrize("level", [
    None,
    WealthLevel.STARTER,
    WealthLevel.MASS_AFFLUENT,
    WealthLevel.HIGH_NET_WORTH,
    WealthLevel.VIP,
])
def test_assets_follow_up_never_offers_plain_total_net_worth(level):
    """The "Tổng net worth" / "Net worth tổng" plain shortcut was removed —
    it duplicated the asset-list headline and confused users with a delta
    computed on a rolling-30-day baseline. The two delta-aware buttons
    (YTD and So với tháng trước) replace it across every wealth level."""
    kwargs = {} if level is None else {"wealth_level": level}
    fus = get_follow_ups(IntentType.QUERY_ASSETS, **kwargs)
    for fu in fus:
        # No bare net-worth headline button (i.e. QUERY_NET_WORTH with no
        # time_range parameter) should appear in the assets follow-ups.
        if fu.intent == IntentType.QUERY_NET_WORTH:
            assert fu.parameters and "time_range" in fu.parameters


@pytest.mark.parametrize("level", [
    None,
    WealthLevel.STARTER,
    WealthLevel.MASS_AFFLUENT,
    WealthLevel.HIGH_NET_WORTH,
    WealthLevel.VIP,
])
def test_month_vs_previous_view_shows_only_goals_cta(level):
    """The ⚖️ comparison surface keeps a single, focused next-step:
    "🎯 Mục tiêu của tôi". Trend / Portfolio buttons are suppressed so
    the user isn't pulled back into another net-worth view right after
    seeing the delta."""
    kwargs = {} if level is None else {"wealth_level": level}
    fus = get_follow_ups(
        IntentType.QUERY_NET_WORTH,
        parameters={"time_range": "month_vs_previous"},
        avoid_intent=IntentType.QUERY_NET_WORTH,
        **kwargs,
    )
    assert len(fus) == 1
    assert fus[0].intent == IntentType.QUERY_GOALS
    assert "Mục tiêu" in fus[0].label
    # No Portfolio button — explicit per UX requirement.
    assert all(f.intent != IntentType.QUERY_PORTFOLIO for f in fus)


def test_net_worth_follow_ups_unaffected_when_no_time_range():
    """Sanity: the override only kicks in for month_vs_previous —
    the default net-worth view still gets its rich pool."""
    fus = get_follow_ups(IntentType.QUERY_NET_WORTH)
    assert len(fus) > 1


@pytest.mark.parametrize("level", [
    WealthLevel.HIGH_NET_WORTH,
    WealthLevel.VIP,
])
def test_net_worth_view_no_longer_offers_portfolio_analytics_label(level):
    """The "💼 Portfolio analytics" shortcut was removed across HNW/VIP.
    It routed to the same QUERY_PORTFOLIO surface as the base
    "💼 Portfolio của tôi" button, so it duplicated the entry-point."""
    fus = get_follow_ups(IntentType.QUERY_NET_WORTH, wealth_level=level)
    for fu in fus:
        assert "Portfolio analytics" not in fu.label


# ---------------------------------------------------------------------------
# Category picker (Story: "Theo loại" → choose category → filtered report)
# ---------------------------------------------------------------------------


def test_category_picker_keyboard_has_all_13_categories():
    kb = build_category_picker_keyboard()
    assert "inline_keyboard" in kb
    flat = [btn for row in kb["inline_keyboard"] for btn in row]
    cats = get_all_categories()
    assert len(flat) == len(cats)
    # Every category label (emoji + name) appears once.
    labels = {btn["text"] for btn in flat}
    for cat in cats:
        assert f"{cat.emoji} {cat.name_vi}" in labels


def test_category_picker_uses_two_column_layout():
    kb = build_category_picker_keyboard()
    rows = kb["inline_keyboard"]
    # All but possibly the last row carry two buttons.
    for row in rows[:-1]:
        assert len(row) == 2
    assert 1 <= len(rows[-1]) <= 2


def test_category_picker_preserves_time_range():
    kb = build_category_picker_keyboard(time_range="this_week")
    flat = [btn for row in kb["inline_keyboard"] for btn in row]
    for btn in flat:
        parsed = parse_callback_data(btn["callback_data"])
        assert parsed is not None
        assert parsed.intent == IntentType.QUERY_EXPENSES_BY_CATEGORY
        assert parsed.parameters is not None
        assert parsed.parameters.get("time_range") == "this_week"
        assert "category" in parsed.parameters


def test_category_picker_omits_time_range_when_none():
    kb = build_category_picker_keyboard()
    flat = [btn for row in kb["inline_keyboard"] for btn in row]
    for btn in flat:
        parsed = parse_callback_data(btn["callback_data"])
        assert parsed is not None
        params = parsed.parameters or {}
        assert "time_range" not in params
        assert "category" in params


@pytest.mark.parametrize("time_range", [None, "this_week", "this_month", "last_month"])
def test_category_picker_button_callback_under_64_bytes(time_range):
    """Every picker button payload must fit Telegram's 64-byte cap for the
    time_range values an expense report actually uses."""
    kb = build_category_picker_keyboard(time_range=time_range)
    flat = [btn for row in kb["inline_keyboard"] for btn in row]
    for btn in flat:
        assert len(btn["callback_data"].encode()) <= 64


def test_is_category_picker_callback_true_when_no_category():
    parsed = FollowUp(label="", intent=IntentType.QUERY_EXPENSES_BY_CATEGORY)
    assert is_category_picker_callback(parsed) is True


def test_is_category_picker_callback_true_when_only_time_range():
    parsed = FollowUp(
        label="",
        intent=IntentType.QUERY_EXPENSES_BY_CATEGORY,
        parameters={"time_range": "this_week"},
    )
    assert is_category_picker_callback(parsed) is True


def test_is_category_picker_callback_false_when_category_set():
    parsed = FollowUp(
        label="",
        intent=IntentType.QUERY_EXPENSES_BY_CATEGORY,
        parameters={"category": "transport"},
    )
    assert is_category_picker_callback(parsed) is False


def test_is_category_picker_callback_false_for_other_intents():
    parsed = FollowUp(label="", intent=IntentType.QUERY_EXPENSES)
    assert is_category_picker_callback(parsed) is False
    assert is_category_picker_callback(None) is False


def test_query_expenses_follow_up_has_theo_loai_button():
    fus = get_follow_ups(IntentType.QUERY_EXPENSES)
    labels = [fu.label for fu in fus]
    assert any("Theo loại" in label for label in labels)


def test_query_expenses_follow_up_propagates_time_range_to_picker():
    """When the parent report is "tuần này", the picker button must carry
    that time_range so the wizard preserves the period."""
    fus = get_follow_ups(
        IntentType.QUERY_EXPENSES, parameters={"time_range": "this_week"}
    )
    picker = next(f for f in fus if "Theo loại" in f.label)
    assert picker.intent == IntentType.QUERY_EXPENSES_BY_CATEGORY
    assert picker.parameters == {"time_range": "this_week"}
    # And the picker button itself stays in picker mode (no category).
    assert is_category_picker_callback(picker) is True


def test_query_expenses_picker_has_no_params_when_no_time_range():
    fus = get_follow_ups(IntentType.QUERY_EXPENSES)
    picker = next(f for f in fus if "Theo loại" in f.label)
    assert picker.parameters is None


def test_query_expenses_by_category_injects_loai_khac_with_time_range():
    fus = get_follow_ups(
        IntentType.QUERY_EXPENSES_BY_CATEGORY,
        parameters={"time_range": "this_week", "category": "food"},
    )
    loai_khac = next(f for f in fus if "Loại khác" in f.label)
    assert loai_khac.intent == IntentType.QUERY_EXPENSES_BY_CATEGORY
    assert loai_khac.parameters == {"time_range": "this_week"}
    # "Loại khác" is itself a picker (no category) so tapping it re-shows
    # the picker keyboard for the same period.
    assert is_category_picker_callback(loai_khac) is True


@pytest.mark.parametrize(
    "category_code",
    [c.code for c in get_all_categories()],
)
def test_category_picker_button_round_trip_for_every_category(category_code):
    """Every category button decodes back to the exact same category +
    time_range — guards against subtle base64/JSON drift."""
    kb = build_category_picker_keyboard(time_range="this_month")
    flat = [btn for row in kb["inline_keyboard"] for btn in row]
    # Find the button matching this category.
    match = None
    for btn in flat:
        parsed = parse_callback_data(btn["callback_data"])
        if parsed and (parsed.parameters or {}).get("category") == category_code:
            match = parsed
            break
    assert match is not None, f"Category {category_code} missing from picker"
    assert match.intent == IntentType.QUERY_EXPENSES_BY_CATEGORY
    assert match.parameters == {"category": category_code, "time_range": "this_month"}


@pytest.mark.parametrize("level", [
    None,
    WealthLevel.STARTER,
    WealthLevel.MASS_AFFLUENT,
    WealthLevel.HIGH_NET_WORTH,
    WealthLevel.VIP,
])
def test_month_vs_previous_view_excludes_portfolio_analytics(level):
    """The month_vs_previous comparison surface must not surface any
    portfolio button (analytics label or otherwise). It's a focused,
    single-CTA view that hands off to goals."""
    kwargs = {} if level is None else {"wealth_level": level}
    fus = get_follow_ups(
        IntentType.QUERY_NET_WORTH,
        parameters={"time_range": "month_vs_previous"},
        avoid_intent=IntentType.QUERY_NET_WORTH,
        **kwargs,
    )
    for fu in fus:
        assert fu.intent != IntentType.QUERY_PORTFOLIO
        assert "Portfolio" not in fu.label
