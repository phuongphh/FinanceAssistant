"""Tier 3 system prompt — Vietnamese-only enforcement (issue #927).

The prompt is the last line of defence after tool output sanitisation.
If it tells the LLM in English to "be friendly", the LLM mirrors the
English. These tests assert:

1. ``_LEVEL_FOCUS`` text for every wealth level is Vietnamese-only
   (no English finance jargon).
2. ``build_reasoning_prompt`` injects the explicit
   ``_VIETNAMESE_OUTPUT_RULE`` so the LLM knows to translate / drop
   English DB codes that bleed through from tools.
3. The translation table for the most common jargon items
   (``NW``, ``passive income``, ``cashflow``, ``allocate``,
   ``rebalance``, ``DCA``, ``saving rate``, ``emergency fund``,
   ``rental``) is present.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.agent.tier3.prompts import (
    DISCLAIMER,
    _LEVEL_FOCUS,
    _VIETNAMESE_OUTPUT_RULE,
    build_reasoning_prompt,
    build_static_prefix,
    build_user_context_block,
)
from backend.wealth.ladder import WealthLevel


_FORBIDDEN_JARGON = [
    "NW",
    "net worth",
    "passive income",
    "active income",
    "cashflow",
    "allocate",
    "allocation",
    "rebalance",
    "saving rate",
    "emergency fund",
    "family-office",
    "trustee",
    "DCA",
    # English DB codes that must never appear in the focus text.
    "rental",
    "real_estate",
    "real estate",
]


@pytest.mark.parametrize("level", list(WealthLevel))
def test_level_focus_is_vietnamese_only(level: WealthLevel):
    text = _LEVEL_FOCUS[level]
    for token in _FORBIDDEN_JARGON:
        assert token.lower() not in text.lower(), (
            f"Forbidden English token {token!r} found in "
            f"_LEVEL_FOCUS[{level.name}]: {text!r}"
        )


def _build(level: WealthLevel = WealthLevel.MASS_AFFLUENT) -> str:
    return build_reasoning_prompt(
        user_name="Phương",
        wealth_level=level,
        net_worth=Decimal("5_000_000_000"),
        tool_descriptions="(tools elided)",
        today=date(2026, 6, 2),
    )


class TestVietnameseOutputRule:
    def test_rule_constant_demands_100_percent_vietnamese(self):
        assert "100% bằng tiếng Việt" in _VIETNAMESE_OUTPUT_RULE

    def test_rule_lists_label_field_convention(self):
        # The tool schema enrichment is useless if the prompt doesn't
        # tell the LLM to prefer the *_label fields.
        assert "category_label" in _VIETNAMESE_OUTPUT_RULE
        assert "stream_type_label" in _VIETNAMESE_OUTPUT_RULE
        assert "asset_type_label" in _VIETNAMESE_OUTPUT_RULE

    def test_rule_bans_english_db_codes(self):
        for code in ("food", "transport", "rental", "salary", "stock"):
            assert code in _VIETNAMESE_OUTPUT_RULE, (
                f"DB code {code!r} should be listed as banned in the rule"
            )

    def test_translation_table_present(self):
        for vn in (
            "tổng tài sản",
            "thu nhập thụ động",
            "dòng tiền",
            "tái cân bằng",
            "tỷ lệ tiết kiệm",
            "quỹ dự phòng",
            "đầu tư đều đặn định kỳ",
        ):
            assert vn in _VIETNAMESE_OUTPUT_RULE


class TestBuildReasoningPrompt:
    def test_includes_vietnamese_output_rule(self):
        prompt = _build()
        assert _VIETNAMESE_OUTPUT_RULE in prompt

    def test_includes_disclaimer_text(self):
        prompt = _build()
        assert DISCLAIMER.strip("_").strip() in prompt

    def test_renders_today_for_every_level(self):
        # Defensive: every level must produce a valid prompt with the
        # date pinned (no template error / KeyError).
        for level in WealthLevel:
            prompt = build_reasoning_prompt(
                user_name="Tester",
                wealth_level=level,
                net_worth=Decimal("1_000_000_000"),
                tool_descriptions="",
                today=date(2026, 6, 2),
            )
            assert "2026-06-02" in prompt
            assert _VIETNAMESE_OUTPUT_RULE in prompt


class TestCacheSplit:
    """The prefix/user split is what makes prompt caching pay off.

    Anthropic matches the cache on a byte-exact prefix, so a single
    per-user value leaking into ``build_static_prefix`` drops the hit
    rate to zero — silently, with no error anywhere. These tests are the
    only thing that would catch that.
    """

    def test_static_prefix_holds_nothing_user_specific(self):
        prefix = build_static_prefix(
            tool_descriptions="(tools elided)", today=date(2026, 6, 2)
        )
        assert "Phương" not in prefix
        # The tone rule points forward at "CONTEXT USER bên dưới", which
        # is cache-stable prose. What must not be here is the block
        # itself — its header carries a colon.
        assert "CONTEXT USER:" not in prefix
        # Net worth is rendered with thousands separators; the digits of
        # the test figure must not appear in any form.
        assert "5,000,000,000" not in prefix
        for level in WealthLevel:
            assert _LEVEL_FOCUS[level] not in prefix

    def test_static_prefix_is_byte_stable_for_two_different_users(self):
        a = build_static_prefix(
            tool_descriptions="(tools elided)", today=date(2026, 6, 2)
        )
        b = build_static_prefix(
            tool_descriptions="(tools elided)", today=date(2026, 6, 2)
        )
        assert a == b

    def test_user_block_carries_every_per_user_value(self):
        block = build_user_context_block(
            user_name="Phương",
            wealth_level=WealthLevel.MASS_AFFLUENT,
            net_worth=Decimal("5_000_000_000"),
        )
        assert "Phương" in block
        assert WealthLevel.MASS_AFFLUENT.value in block
        assert "5,000,000,000" in block
        assert _LEVEL_FOCUS[WealthLevel.MASS_AFFLUENT] in block

    def test_full_prompt_is_the_two_halves_in_order(self):
        # The agent sends these as two system blocks. Concatenation
        # order here must match, or the single-string view tests assert
        # against something production never sends.
        static = build_static_prefix(
            tool_descriptions="(tools elided)", today=date(2026, 6, 2)
        )
        user_block = build_user_context_block(
            user_name="Phương",
            wealth_level=WealthLevel.MASS_AFFLUENT,
            net_worth=Decimal("5_000_000_000"),
        )
        assert _build() == f"{static}\n\n{user_block}"

    def test_user_block_comes_last(self):
        prompt = _build()
        assert prompt.index("CONTEXT USER") > prompt.index("QUY TẮC HARD")
        assert prompt.rstrip().endswith(
            _LEVEL_FOCUS[WealthLevel.MASS_AFFLUENT]
        )
