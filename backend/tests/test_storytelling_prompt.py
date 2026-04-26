"""Tests for the storytelling extraction prompt + parser.

The LLM call is mocked — we test the parsing/validation layer with
30+ synthetic LLM responses covering the patterns from
``docs/issues/active/issue-75.md``:

- Simple single-transaction stories
- Multiple transactions in one story
- Vietnamese number suffixes (k, tr, triệu, tỷ)
- Split-bill scenarios (LLM should already do the math)
- Below-threshold filtering (defence-in-depth: LLM disobedience caught)
- Empty / no-transaction stories
- Ambiguous stories → needs_clarification
- Voice transcripts with typos / no diacritics
- Income-vs-expense disambiguation
- Garbage LLM output (non-JSON, wrong shape) — graceful degradation

Each test exercises ``parse_storytelling_response`` directly so we
don't need the LLM wire. ``test_extract_*`` tests then patch
``call_llm`` to verify the wrapper plumbs the threshold + user_id
correctly.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.personality.storytelling_prompt import (
    STORYTELLING_PROMPT,
    StorytellingResult,
    extract_transactions_from_story,
    parse_storytelling_response,
)


# ----------------------------------------------------------------------
# Prompt formatting — sanity checks
# ----------------------------------------------------------------------


class TestPromptTemplate:
    def test_threshold_is_substituted(self):
        prompt = STORYTELLING_PROMPT.format(threshold=200_000, story="hi")
        assert "200000" in prompt
        assert "{threshold}" not in prompt

    def test_story_is_substituted(self):
        prompt = STORYTELLING_PROMPT.format(threshold=100_000, story="ăn phở 800k")
        assert "ăn phở 800k" in prompt
        assert "{story}" not in prompt

    def test_prompt_mentions_categories(self):
        prompt = STORYTELLING_PROMPT.format(threshold=100_000, story="x")
        for cat in ("food", "transport", "shopping", "investment"):
            assert cat in prompt

    def test_prompt_documents_output_schema(self):
        prompt = STORYTELLING_PROMPT.format(threshold=100_000, story="x")
        for key in ("transactions", "needs_clarification", "ignored_small"):
            assert key in prompt


# ----------------------------------------------------------------------
# parse_storytelling_response — 30+ scenarios
# ----------------------------------------------------------------------


def _resp(txs=None, clarif=None, ignored=None) -> dict:
    """Helper to build a fake LLM response dict."""
    return {
        "transactions": txs or [],
        "needs_clarification": clarif or [],
        "ignored_small": ignored or [],
    }


class TestParseStorytellingResponse:
    # --- Simple cases (1-5) ---

    def test_simple_single_transaction(self):
        """'Tối qua ăn nhà hàng 800k'"""
        r = parse_storytelling_response(
            _resp(
                txs=[
                    {
                        "amount": 800_000,
                        "merchant": "Nhà hàng",
                        "category": "food",
                        "time_hint": "tối qua",
                        "confidence": 0.95,
                    }
                ]
            ),
            threshold=200_000,
        )
        assert len(r.transactions) == 1
        assert r.transactions[0]["amount"] == 800_000
        assert r.transactions[0]["category"] == "food"

    def test_million_amount_phone(self):
        """'mua điện thoại 15 triệu'"""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 15_000_000, "merchant": "Điện thoại", "category": "shopping"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["amount"] == 15_000_000
        assert r.transactions[0]["category"] == "shopping"

    def test_billion_amount_apartment(self):
        """'đặt cọc nhà 200 triệu'"""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 200_000_000, "merchant": "đặt cọc nhà", "category": "housing"}]),
            threshold=500_000,
        )
        assert r.transactions[0]["amount"] == 200_000_000

    def test_thousand_amount_rejected_below_threshold(self):
        """'ăn phở 50k' với threshold=200k → ignored_small."""
        r = parse_storytelling_response(
            _resp(
                ignored=[{"text": "ăn phở 50k", "amount": 50_000, "reason": "dưới threshold"}]
            ),
            threshold=200_000,
        )
        assert len(r.transactions) == 0
        assert len(r.ignored_small) == 1

    def test_split_bill_already_halved(self):
        """'ăn với bạn 400k chia đôi' → LLM emits 200k for the user."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 200_000, "merchant": "ăn với bạn", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["amount"] == 200_000

    # --- Multiple transactions (6-10) ---

    def test_multiple_transactions_same_story(self):
        """'Hôm qua ăn 500k + grab 300k + mua áo 1.5tr'"""
        r = parse_storytelling_response(
            _resp(
                txs=[
                    {"amount": 500_000, "merchant": "ăn", "category": "food"},
                    {"amount": 300_000, "merchant": "Grab", "category": "transport"},
                    {"amount": 1_500_000, "merchant": "áo", "category": "shopping"},
                ]
            ),
            threshold=200_000,
        )
        assert len(r.transactions) == 3
        assert r.transactions[0]["category"] == "food"
        assert r.transactions[1]["category"] == "transport"
        assert r.transactions[2]["category"] == "shopping"

    def test_mix_above_and_below_threshold(self):
        """LLM emits both — only above-threshold survives validation."""
        r = parse_storytelling_response(
            _resp(
                txs=[
                    {"amount": 800_000, "merchant": "ăn lớn", "category": "food"},
                    # Below threshold — will be filtered by validator
                    {"amount": 50_000, "merchant": "cà phê", "category": "food"},
                ],
                ignored=[
                    {"text": "cà phê 50k", "amount": 50_000}
                ],
            ),
            threshold=200_000,
        )
        # One survives (800k), the 50k drops in validation
        assert len(r.transactions) == 1
        assert r.transactions[0]["amount"] == 800_000

    def test_two_clarifications(self):
        r = parse_storytelling_response(
            _resp(
                clarif=[
                    {"text": "mua đồ", "reason": "không rõ"},
                    {"text": "đi chơi", "reason": "không rõ tiền"},
                ]
            ),
            threshold=200_000,
        )
        assert len(r.needs_clarification) == 2

    def test_all_three_buckets_populated(self):
        r = parse_storytelling_response(
            _resp(
                txs=[{"amount": 1_000_000, "merchant": "khách sạn", "category": "entertainment"}],
                clarif=[{"text": "mua sách", "reason": "không rõ"}],
                ignored=[{"text": "ăn phở 50k", "amount": 50_000}],
            ),
            threshold=200_000,
        )
        assert len(r.transactions) == 1
        assert len(r.needs_clarification) == 1
        assert len(r.ignored_small) == 1
        assert r.has_anything()

    def test_empty_story_no_transactions(self):
        """'Đi chơi với bạn vui lắm' → no expense extracted."""
        r = parse_storytelling_response(_resp(), threshold=200_000)
        assert r.transactions == []
        assert not r.has_anything()

    # --- Edge cases (11-20) ---

    def test_invalid_category_coerced_to_other(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 500_000, "merchant": "x", "category": "made_up_cat"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["category"] == "other"

    def test_missing_category_coerced_to_other(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 500_000, "merchant": "x"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["category"] == "other"

    def test_missing_merchant_gets_default(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 500_000, "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["merchant"] == "Chi tiêu"

    def test_zero_amount_dropped(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 0, "merchant": "x", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions == []

    def test_negative_amount_dropped(self):
        """Income disguised as expense — LLM should ignore but if it slips through, drop it."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": -500_000, "merchant": "lương", "category": "other"}]),
            threshold=200_000,
        )
        assert r.transactions == []

    def test_string_amount_parsed(self):
        """LLMs sometimes emit numbers as strings — be tolerant."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": "800000", "merchant": "x", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["amount"] == 800_000

    def test_float_amount_rounded(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 800000.4, "merchant": "x", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["amount"] == 800_000

    def test_garbage_amount_dropped(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": "lots", "merchant": "x", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions == []

    def test_confidence_clipped_to_0_1(self):
        r = parse_storytelling_response(
            _resp(
                txs=[
                    {"amount": 500_000, "merchant": "a", "category": "food", "confidence": 1.5},
                    {"amount": 500_000, "merchant": "b", "category": "food", "confidence": -0.3},
                ]
            ),
            threshold=200_000,
        )
        assert r.transactions[0]["confidence"] == 1.0
        assert r.transactions[1]["confidence"] == 0.0

    def test_confidence_default_when_missing(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 500_000, "merchant": "x", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["confidence"] == 0.7

    # --- Threshold defence-in-depth (21-25) ---

    def test_below_threshold_dropped_even_if_llm_emits(self):
        """LLM puts 100k tx in 'transactions' though threshold is 200k."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 100_000, "merchant": "x", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions == []

    def test_at_threshold_kept(self):
        """200k with threshold=200k → kept (>= comparison)."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 200_000, "merchant": "x", "category": "food"}]),
            threshold=200_000,
        )
        assert len(r.transactions) == 1

    def test_high_income_threshold(self):
        """User threshold=500k → 300k coffee dropped."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 300_000, "merchant": "starbucks", "category": "food"}]),
            threshold=500_000,
        )
        assert r.transactions == []

    def test_low_income_threshold(self):
        """User threshold=100k → 150k transport kept."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 150_000, "merchant": "Grab", "category": "transport"}]),
            threshold=100_000,
        )
        assert len(r.transactions) == 1

    def test_zero_threshold_keeps_all(self):
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 1_000, "merchant": "a", "category": "food"}]),
            threshold=0,
        )
        assert len(r.transactions) == 1

    # --- Bad LLM output (26-32) ---

    def test_non_json_string_returns_empty(self):
        r = parse_storytelling_response("not json at all", threshold=200_000)
        assert r.transactions == []
        assert "_error" in r.raw

    def test_empty_string_returns_empty(self):
        r = parse_storytelling_response("", threshold=200_000)
        assert r.transactions == []

    def test_json_fenced_code_block_parsed(self):
        """DeepSeek sometimes returns ```json ... ``` despite json mode."""
        text = '```json\n{"transactions": [{"amount": 500000, "merchant": "x", "category": "food"}]}\n```'
        r = parse_storytelling_response(text, threshold=200_000)
        assert len(r.transactions) == 1

    def test_dict_input_works(self):
        """parse() should accept already-parsed dicts as well as JSON strings."""
        r = parse_storytelling_response(
            {"transactions": [{"amount": 500_000, "merchant": "x", "category": "food"}]},
            threshold=200_000,
        )
        assert len(r.transactions) == 1

    def test_wrong_top_level_shape_returns_empty(self):
        """LLM returns a list instead of object."""
        r = parse_storytelling_response("[]", threshold=200_000)
        assert r.transactions == []

    def test_transactions_field_not_a_list(self):
        r = parse_storytelling_response(
            {"transactions": "not a list"}, threshold=200_000
        )
        assert r.transactions == []

    def test_non_dict_inside_transactions_skipped(self):
        r = parse_storytelling_response(
            {"transactions": ["string entry", {"amount": 500_000, "merchant": "x", "category": "food"}]},
            threshold=200_000,
        )
        assert len(r.transactions) == 1

    # --- Voice transcript style (33-36) ---

    def test_voice_no_diacritics(self):
        """Whisper sometimes drops Vietnamese diacritics — output still useful."""
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 800_000, "merchant": "nha hang ngon", "category": "food"}]),
            threshold=200_000,
        )
        assert r.transactions[0]["merchant"] == "nha hang ngon"

    def test_long_merchant_truncated(self):
        long = "a" * 500
        r = parse_storytelling_response(
            _resp(txs=[{"amount": 500_000, "merchant": long, "category": "food"}]),
            threshold=200_000,
        )
        assert len(r.transactions[0]["merchant"]) <= 200

    def test_time_hint_preserved_when_present(self):
        r = parse_storytelling_response(
            _resp(
                txs=[
                    {
                        "amount": 500_000,
                        "merchant": "x",
                        "category": "food",
                        "time_hint": "tối qua",
                    }
                ]
            ),
            threshold=200_000,
        )
        assert r.transactions[0]["time_hint"] == "tối qua"

    def test_context_preserved_when_present(self):
        r = parse_storytelling_response(
            _resp(
                txs=[
                    {
                        "amount": 1_500_000,
                        "merchant": "khách sạn",
                        "category": "entertainment",
                        "context": "đi nghỉ với gia đình",
                    }
                ]
            ),
            threshold=200_000,
        )
        assert r.transactions[0]["context"] == "đi nghỉ với gia đình"


# ----------------------------------------------------------------------
# extract_transactions_from_story — wrapper integration
# ----------------------------------------------------------------------


class TestExtractTransactionsFromStory:
    @pytest.mark.asyncio
    async def test_empty_story_short_circuits(self):
        """No LLM call when story is empty."""
        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm"
        ) as call_mock:
            r = await extract_transactions_from_story("", threshold=200_000)
        assert r.transactions == []
        call_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_story_short_circuits(self):
        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm"
        ) as call_mock:
            r = await extract_transactions_from_story("   \n  ", threshold=200_000)
        assert r.transactions == []
        call_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_threshold_passed_to_prompt(self):
        captured = {}

        async def fake_call(prompt, **kwargs):
            captured["prompt"] = prompt
            return '{"transactions": [], "needs_clarification": [], "ignored_small": []}'

        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm",
            new=AsyncMock(side_effect=fake_call),
        ):
            await extract_transactions_from_story("ăn 500k", threshold=300_000)

        assert "300000" in captured["prompt"]
        assert "ăn 500k" in captured["prompt"]

    @pytest.mark.asyncio
    async def test_user_id_propagated_to_call_llm(self):
        user_id = uuid.uuid4()
        db = MagicMock()
        called_with = {}

        async def fake_call(prompt, **kwargs):
            called_with.update(kwargs)
            return '{"transactions": []}'

        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm",
            new=AsyncMock(side_effect=fake_call),
        ):
            await extract_transactions_from_story(
                "ăn 500k", threshold=200_000, db=db, user_id=user_id
            )

        assert called_with["user_id"] == user_id
        assert called_with["task_type"] == "storytelling_extract"
        assert called_with["use_cache"] is True

    @pytest.mark.asyncio
    async def test_cache_disabled_when_no_db(self):
        called_with = {}

        async def fake_call(prompt, **kwargs):
            called_with.update(kwargs)
            return '{"transactions": []}'

        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm",
            new=AsyncMock(side_effect=fake_call),
        ):
            await extract_transactions_from_story("ăn 500k", threshold=200_000)

        assert called_with["use_cache"] is False
        assert called_with.get("db") is None

    @pytest.mark.asyncio
    async def test_llm_error_returns_empty_result(self):
        from backend.services.llm_service import LLMError

        async def fake_call(prompt, **kwargs):
            raise LLMError("api down")

        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm",
            new=AsyncMock(side_effect=fake_call),
        ):
            r = await extract_transactions_from_story("ăn 500k", threshold=200_000)

        assert isinstance(r, StorytellingResult)
        assert r.transactions == []

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_empty_result(self):
        async def fake_call(prompt, **kwargs):
            raise RuntimeError("boom")

        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm",
            new=AsyncMock(side_effect=fake_call),
        ):
            r = await extract_transactions_from_story("ăn 500k", threshold=200_000)

        assert isinstance(r, StorytellingResult)
        assert r.transactions == []

    @pytest.mark.asyncio
    async def test_full_round_trip_with_valid_response(self):
        async def fake_call(prompt, **kwargs):
            return (
                '{"transactions": [{"amount": 800000, "merchant": "Nhà hàng", '
                '"category": "food", "confidence": 0.9}], '
                '"needs_clarification": [], "ignored_small": []}'
            )

        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm",
            new=AsyncMock(side_effect=fake_call),
        ):
            r = await extract_transactions_from_story(
                "tối qua ăn nhà hàng 800k", threshold=200_000
            )

        assert len(r.transactions) == 1
        assert r.transactions[0]["amount"] == 800_000
        assert r.transactions[0]["category"] == "food"

    @pytest.mark.asyncio
    async def test_negative_threshold_clamped_to_zero(self):
        captured = {}

        async def fake_call(prompt, **kwargs):
            captured["prompt"] = prompt
            return '{"transactions": []}'

        with patch(
            "backend.bot.personality.storytelling_prompt.call_llm",
            new=AsyncMock(side_effect=fake_call),
        ):
            await extract_transactions_from_story("ăn 500k", threshold=-100)

        # Should appear as 0 in the prompt, not -100
        assert "User threshold: 0 VND" in captured["prompt"]
