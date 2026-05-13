"""Tests for the LLM-based classifier.

Stubs ``call_llm`` so the test suite never makes a real DeepSeek call.
What we exercise:
  - JSON parsing + IntentType normalization
  - Bad / non-JSON responses degrade to None
  - Unknown intent strings → IntentType.UNCLEAR
  - Cost-per-call estimate stays under the budget threshold
  - last_call_stats populated with token + latency info
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.classifier.llm_based import (
    LLM_CLASSIFIER_PROMPT,
    LLMClassifier,
)
from backend.intent.intents import CLASSIFIER_LLM, IntentType


def _stub_call_llm(response_text: str):
    """Patch ``backend.intent.classifier.llm_based.call_llm`` to return
    ``response_text`` exactly. Using a raw AsyncMock so we can also
    assert the call args.
    """
    return patch(
        "backend.intent.classifier.llm_based.call_llm",
        AsyncMock(return_value=response_text),
    )


class _NullSessionFactory:
    """Async-context-manager that yields None — emulates "no DB"
    so the classifier still runs without a real session."""

    def __call__(self):
        return self

    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def classifier() -> LLMClassifier:
    return LLMClassifier(db_factory=_NullSessionFactory())


@pytest.mark.asyncio
async def test_classify_returns_expected_intent_for_clean_json(classifier):
    json_payload = json.dumps({
        "intent": "query_net_worth",
        "confidence": 0.92,
        "parameters": {},
    })
    with _stub_call_llm(json_payload):
        result = await classifier.classify("tôi đang giàu cỡ nào")

    assert result is not None
    assert result.intent == IntentType.QUERY_NET_WORTH
    assert result.confidence == pytest.approx(0.92)
    assert result.classifier_used == CLASSIFIER_LLM


@pytest.mark.asyncio
async def test_classify_handles_english_query(classifier):
    json_payload = json.dumps({
        "intent": "query_portfolio",
        "confidence": 0.88,
        "parameters": {},
    })
    with _stub_call_llm(json_payload):
        result = await classifier.classify("show me my stocks")
    assert result.intent == IntentType.QUERY_PORTFOLIO


@pytest.mark.asyncio
async def test_classify_handles_oos(classifier):
    json_payload = json.dumps({
        "intent": "out_of_scope",
        "confidence": 0.95,
        "parameters": {},
    })
    with _stub_call_llm(json_payload):
        result = await classifier.classify("thời tiết hôm nay")
    assert result.intent == IntentType.OUT_OF_SCOPE


@pytest.mark.asyncio
async def test_classify_normalises_ticker_to_upper(classifier):
    json_payload = json.dumps({
        "intent": "query_market",
        "confidence": 0.9,
        "parameters": {"ticker": "vnm"},
    })
    with _stub_call_llm(json_payload):
        result = await classifier.classify("VNM giá")
    assert result.parameters["ticker"] == "VNM"


@pytest.mark.asyncio
async def test_classify_strips_code_fences(classifier):
    response = "```json\n" + json.dumps({
        "intent": "query_assets",
        "confidence": 0.91,
        "parameters": {},
    }) + "\n```"
    with _stub_call_llm(response):
        result = await classifier.classify("tài sản")
    assert result is not None
    assert result.intent == IntentType.QUERY_ASSETS


@pytest.mark.asyncio
async def test_unknown_intent_string_falls_back_to_unclear(classifier):
    json_payload = json.dumps({
        "intent": "totally_made_up",
        "confidence": 0.99,
        "parameters": {},
    })
    with _stub_call_llm(json_payload):
        result = await classifier.classify("???")
    assert result.intent == IntentType.UNCLEAR


@pytest.mark.asyncio
async def test_non_json_response_returns_none(classifier):
    with _stub_call_llm("hello there, definitely not JSON"):
        result = await classifier.classify("anything")
    assert result is None


@pytest.mark.asyncio
async def test_invalid_confidence_clamped(classifier):
    json_payload = json.dumps({
        "intent": "query_assets",
        "confidence": 5.0,  # impossible
        "parameters": {},
    })
    with _stub_call_llm(json_payload):
        result = await classifier.classify("anything")
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_call_returns_none_on_llm_error(classifier):
    from backend.services.llm_service import LLMError

    with patch(
        "backend.intent.classifier.llm_based.call_llm",
        AsyncMock(side_effect=LLMError("rate limit")),
    ):
        result = await classifier.classify("anything")
    assert result is None


@pytest.mark.asyncio
async def test_cost_per_call_within_budget(classifier):
    """Acceptance criterion: cost < $0.0005 per call. The estimate is
    based on prompt+response length so a synthetic short response is a
    fair lower-bound check (the prompt itself is the dominant cost)."""
    json_payload = json.dumps({
        "intent": "query_assets",
        "confidence": 0.9,
        "parameters": {},
    })
    with _stub_call_llm(json_payload):
        await classifier.classify("tài sản của tôi")

    stats = classifier.last_call_stats
    assert stats is not None
    assert stats.cost_usd < 0.0005, (
        f"LLM call cost {stats.cost_usd:.6f} exceeds budget"
    )
    assert stats.input_tokens > 0
    assert stats.output_tokens > 0


def test_prompt_includes_all_intents():
    """If we add a new IntentType, the prompt must mention it — else
    the LLM will never return the new intent."""
    for intent in IntentType:
        # Skip greeting/help/unclear which are meta — also covered
        # explicitly in the prompt body.
        if intent in (IntentType.UNCLEAR,):
            continue
        assert intent.value in LLM_CLASSIFIER_PROMPT, (
            f"Intent {intent.value} missing from LLM_CLASSIFIER_PROMPT"
        )
