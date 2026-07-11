"""Phase 4.5 / E4 / Issue #4.3 — tone-dial copy variants.

The tone dial (gentle/strict) reshapes only the emotionally-loaded copy: the
proactive empathy nudges and the feasibility NEEDS_REVISION verdict. Everything
here is pure — no DB, no clock — so we render the real ``tone_variants.yaml``
through the real formatters and assert on the text.

Coverage:

* ``resolve_tone`` collapses the nullable preference to gentle/strict.
* ``render_tone_variant`` renders 2 tones × 3 xưng hô (anh/chị/bạn), and
  returns ``None`` (legacy fallback) when the dial is dark or the block is
  absent.
* Persona floor — ``test_strict_never_humiliates`` sweeps every strict block
  against a shaming-word blocklist; strict is thẳng thắn, never sỉ nhục.
* The empathy engine and feasibility formatter thread the tone through, and
  fall back to legacy copy untouched when ``tone=None``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.bot.formatters import feasibility as feas_fmt
from backend.bot.formatters import tone as tone_fmt
from backend.bot.personality import empathy_engine
from backend.bot.personality.empathy_engine import EmpathyTrigger, render_message
from backend.schemas.goal import FeasibilityBand
from backend.services.decision import plan_feasibility_service

# Copy that must never appear in any tone (persona / positioning floor).
_BANNED_POSITIONING = ("Decision Engine", "GPS tài chính", "CFO")

# Words that shame, blame, or belittle. Strict = thẳng thắn, NEVER sỉ nhục.
# If new strict copy trips this, the copy is wrong, not the test.
_HUMILIATING = (
    "ngu",
    "ngốc",
    "lười",
    "vô dụng",
    "thất bại",
    "kém cỏi",
    "tệ hại",
    "đáng xấu hổ",
    "hoang phí",
    "phá của",
)

_ALL_SALUTATIONS = ("anh", "chị", "bạn")


# --------------------------------------------------------------------------
# resolve_tone
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pref,expected",
    [
        (None, "gentle"),
        ("", "gentle"),
        ("gentle", "gentle"),
        ("garbage", "gentle"),
        ("strict", "strict"),
    ],
)
def test_resolve_tone_only_exact_strict_is_strict(pref, expected):
    assert tone_fmt.resolve_tone(pref) == expected


# --------------------------------------------------------------------------
# render_tone_variant — presence, fallback, placeholders
# --------------------------------------------------------------------------


def test_dark_dial_returns_none_for_legacy_fallback():
    assert (
        tone_fmt.render_tone_variant(
            "empathy.large_transaction", None, salutation="anh", amount="5tr"
        )
        is None
    )


def test_absent_key_returns_none():
    assert (
        tone_fmt.render_tone_variant("empathy.does_not_exist", "gentle") is None
    )
    assert (
        tone_fmt.render_tone_variant("decision.no_such_block", "strict") is None
    )


@pytest.mark.parametrize("tone", ["gentle", "strict"])
@pytest.mark.parametrize("salutation", _ALL_SALUTATIONS)
def test_empathy_renders_two_tones_by_three_salutations(tone, salutation):
    text = tone_fmt.render_tone_variant(
        "empathy.large_transaction",
        tone,
        salutation=salutation,
        amount="12tr",
    )
    assert text is not None
    assert salutation in text
    assert "12tr" in text
    # No stray unfilled placeholders and no positioning leaks.
    assert "{" not in text and "}" not in text
    for banned in _BANNED_POSITIONING:
        assert banned not in text


@pytest.mark.parametrize("tone", ["gentle", "strict"])
@pytest.mark.parametrize("salutation", _ALL_SALUTATIONS)
def test_feasibility_variant_renders_two_tones_by_three_salutations(
    tone, salutation
):
    text = tone_fmt.render_tone_variant(
        "decision.feasibility_needs_revision",
        tone,
        salutation=salutation,
        actual="2tr",
    )
    assert text is not None
    assert "2tr" in text
    assert "{" not in text and "}" not in text


# --------------------------------------------------------------------------
# Persona floor
# --------------------------------------------------------------------------


def _walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from _walk_strings(item)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)


def _all_strict_strings() -> list[str]:
    copy = tone_fmt._tone_copy()
    out: list[str] = []
    for _key, block in _iter_variant_blocks(copy):
        strict = block.get("strict")
        if strict is not None:
            out.extend(_walk_strings(strict))
    return out


def _iter_variant_blocks(copy: dict):
    """Yield (dotted_key, block) for every leaf that has gentle/strict keys."""
    for section, entries in copy.items():
        if not isinstance(entries, dict):
            continue
        for name, block in entries.items():
            if isinstance(block, dict) and ("gentle" in block or "strict" in block):
                yield f"{section}.{name}", block


def test_strict_never_humiliates():
    strict_texts = _all_strict_strings()
    assert strict_texts, "expected at least one strict block to guard"
    for text in strict_texts:
        lowered = text.lower()
        for bad in _HUMILIATING:
            assert bad not in lowered, f"strict copy shames the user: {text!r}"
        for banned in _BANNED_POSITIONING:
            assert banned not in text


def test_every_block_has_both_tones():
    """A tone block that only ships one tone silently degrades to legacy for
    the other — force both to be authored together."""
    for key, block in _iter_variant_blocks(tone_fmt._tone_copy()):
        assert "gentle" in block, f"{key} missing gentle"
        assert "strict" in block, f"{key} missing strict"


# --------------------------------------------------------------------------
# Empathy engine wiring
# --------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, salutation="bạn", name="Minh", tone_preference=None):
        self.salutation = salutation
        self._name = name
        self.tone_preference = tone_preference

    def get_greeting_name(self):
        return self._name


def _large_tx_trigger():
    return EmpathyTrigger(
        name="large_transaction",
        priority=1,
        cooldown_days=1,
        context={"amount": "12tr"},
    )


def test_render_message_strict_uses_tone_variant():
    user = _FakeUser(salutation="anh")
    text = render_message(_large_tx_trigger(), user, tone="strict")
    assert "anh" in text
    assert "12tr" in text
    # The strict variant's signature phrasing, not the gentle legacy copy.
    assert "thẳng" in text.lower()


def test_render_message_none_tone_is_legacy(monkeypatch):
    """With tone=None the variant renderer must yield None, so the engine
    renders the legacy empathy copy — zero regression when the dial is dark."""
    seen = {}

    def _spy(key, tone, **k):
        seen["tone"] = tone
        return None  # mirror the real contract: tone=None → None

    monkeypatch.setattr(empathy_engine, "render_tone_variant", _spy)
    user = _FakeUser(salutation="chị")
    text = render_message(_large_tx_trigger(), user, tone=None)
    assert seen["tone"] is None
    # Legacy path produced real copy carrying the threaded context.
    assert "12tr" in text


def test_render_message_falls_back_when_no_tone_block():
    """A trigger with no tone block still renders via legacy copy."""
    trigger = EmpathyTrigger(
        name="user_silent_30_days",  # no block in tone_variants.yaml
        priority=5,
        cooldown_days=60,
        context={"days_silent": 42},
    )
    user = _FakeUser(salutation="bạn")
    text = render_message(trigger, user, tone="strict")
    assert text  # legacy empathy_messages.yaml copy


# --------------------------------------------------------------------------
# Feasibility formatter wiring
# --------------------------------------------------------------------------


def _needs_revision():
    result = plan_feasibility_service.assess(
        Decimal(0), Decimal(5_000_000_000), Decimal(2), Decimal(1_000_000)
    )
    assert result.band == FeasibilityBand.NEEDS_REVISION
    return result


def test_feasibility_strict_swaps_verdict_keeps_pivot():
    result = _needs_revision()
    text = feas_fmt.render_feasibility(
        result,
        target=Decimal(5_000_000_000),
        horizon_years=Decimal(2),
        tone="strict",
        salutation="chị",
    )
    assert "chị" in text
    assert "thẳng" in text.lower()
    # We still never end on a flat "no": the reachable pivot survives.
    assert "với tới được" in text


def test_feasibility_default_call_is_unchanged_legacy():
    """No tone args → byte-for-byte the pre-#4.3 legacy copy ("quá sức")."""
    result = _needs_revision()
    text = feas_fmt.render_feasibility(
        result, target=Decimal(5_000_000_000), horizon_years=Decimal(2)
    )
    assert "quá sức" in text
