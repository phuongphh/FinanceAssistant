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
