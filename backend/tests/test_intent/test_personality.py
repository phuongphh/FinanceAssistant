"""Tests for the Bé Tiền personality wrapper (Story #125)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.bot.personality import query_voice
from backend.bot.personality.query_voice import (
    FORBIDDEN_PHRASES,
    add_personality,
    assert_no_forbidden_phrases,
    get_suggestions_for_intent,
)
from backend.intent.intents import IntentType


def _user(name: str = "An") -> MagicMock:
    user = MagicMock()
    user.display_name = name
    return user


# ---------------------- variation ----------------------


def test_same_query_produces_three_or_more_distinct_openings():
    """Acceptance: 5 calls → 3+ different openings."""
    base = "💎 Tài sản hiện tại của An: 100tr"
    user = _user("An")
    seen: set[str] = set()
    # Use varied seeds to simulate real usage; deterministic per seed
    # so the test stays stable.
    for seed in range(15):
        out = add_personality(base, user, IntentType.QUERY_ASSETS, rng_seed=seed)
        opening = out.split("\n", 1)[0]
        seen.add(opening)
    assert len(seen) >= 3, f"only {len(seen)} distinct openings: {seen}"


def test_personality_never_emits_forbidden_phrases():
    """Run a wide sweep; no banned generic-AI phrases ever appear."""
    base = "Some response text"
    user = _user("An")
    for seed in range(50):
        out = add_personality(base, user, IntentType.QUERY_ASSETS, rng_seed=seed)
        assert_no_forbidden_phrases(out)


def test_assert_no_forbidden_phrases_raises_on_match():
    """The helper itself flags banned phrases — sanity check the guard."""
    with pytest.raises(AssertionError):
        assert_no_forbidden_phrases("Here are your assets:")


# ---------------------- composition ----------------------


def test_greeting_uses_user_display_name():
    """When the random roll lands on a name-bearing greeting, the
    user's name appears at the head of the response."""
    user = _user("Hùng")
    base = "📊 Net worth: 500tr"
    found_name_greeting = False
    for seed in range(80):
        out = add_personality(
            base, user, IntentType.QUERY_NET_WORTH, rng_seed=seed
        )
        head = out.split("\n", 1)[0]
        if "Hùng" in head:
            found_name_greeting = True
            break
    assert found_name_greeting, "No seed produced a name-bearing greeting"


def test_falls_back_to_default_pronoun_when_name_missing():
    user = _user(None)
    user.display_name = ""
    out = add_personality(
        "Some text", user, IntentType.QUERY_ASSETS, rng_seed=2
    )
    # No name available — wrapper either skipped greeting or used
    # "bạn" placeholder. Either way it must not insert "None" or "".
    assert "None" not in out
    assert "{name}" not in out


def test_empty_response_returned_unchanged():
    user = _user()
    assert add_personality("", user, IntentType.QUERY_ASSETS, rng_seed=0) == ""


def test_suggestion_appended_when_roll_lands_there():
    """Force a seed that hits suggestion only — no greeting, has tail."""
    user = _user("An")
    base = "Original response."
    # rng_seed=42 must hit the >0.30 / <0.50 band to skip greeting
    # but include suggestion. Iterate to find one for stability.
    for seed in range(100):
        out = add_personality(
            base, user, IntentType.QUERY_ASSETS, rng_seed=seed
        )
        if (
            out.startswith(base)
            and len(out) > len(base)
            and "\n\n" in out
        ):
            tail = out[len(base):].lstrip("\n")
            assert tail  # non-empty suggestion
            return
    pytest.fail("Could not find a seed that adds suggestion only")


# ---------------------- suggestion catalogue ----------------------


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
def test_every_read_intent_has_at_least_one_suggestion(intent):
    suggestions = get_suggestions_for_intent(intent)
    assert suggestions
    # All suggestions are non-empty strings.
    for s in suggestions:
        assert isinstance(s, str) and s.strip()


def test_query_assets_has_5plus_suggestions():
    """Acceptance criterion: 5+ variations per intent for read intents."""
    suggestions = get_suggestions_for_intent(IntentType.QUERY_ASSETS)
    assert len(suggestions) >= 5


# ---------------------- forbidden phrase catalogue ----------------------


def test_forbidden_phrases_are_lowercased():
    """The matcher lowercases input before substring search; the
    catalogue must therefore be lowercase to actually trigger."""
    for phrase in FORBIDDEN_PHRASES:
        assert phrase == phrase.lower(), f"{phrase!r} not lowercased"
