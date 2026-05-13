"""Tests for IntentPipeline — fallback ordering and UNCLEAR floor."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from backend.intent.classifier.pipeline import (
    HIGH_CONFIDENCE_THRESHOLD,
    IntentPipeline,
)
from backend.intent.intents import (
    CLASSIFIER_LLM,
    CLASSIFIER_NONE,
    CLASSIFIER_RULE,
    IntentResult,
    IntentType,
)


def _stub_classifier(result: IntentResult | None) -> MagicMock:
    cls = MagicMock()
    cls.classify = MagicMock(return_value=result)
    return cls


@pytest.mark.asyncio
async def test_high_confidence_rule_short_circuits_llm():
    rule_match = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.95,
        classifier_used=CLASSIFIER_RULE,
    )
    llm = _stub_classifier(None)
    pipeline = IntentPipeline(
        rule_classifier=_stub_classifier(rule_match),
        llm_classifier=llm,
    )

    result = await pipeline.classify("tài sản của tôi")
    assert result is rule_match
    llm.classify.assert_not_called()


@pytest.mark.asyncio
async def test_low_confidence_rule_falls_through_to_llm():
    rule_match = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.6,
        classifier_used=CLASSIFIER_RULE,
    )
    llm_match = IntentResult(
        intent=IntentType.QUERY_PORTFOLIO,
        confidence=0.92,
        classifier_used=CLASSIFIER_LLM,
    )
    pipeline = IntentPipeline(
        rule_classifier=_stub_classifier(rule_match),
        llm_classifier=_stub_classifier(llm_match),
    )

    result = await pipeline.classify("tôi đang giàu cỡ nào")
    assert result is llm_match


@pytest.mark.asyncio
async def test_no_match_falls_back_to_unclear():
    pipeline = IntentPipeline(
        rule_classifier=_stub_classifier(None),
        llm_classifier=None,
    )
    result = await pipeline.classify("asdkfjh")
    assert result.intent == IntentType.UNCLEAR
    assert result.confidence == 0.0
    assert result.classifier_used == CLASSIFIER_NONE


@pytest.mark.asyncio
async def test_llm_returns_none_falls_back_to_low_confidence_rule():
    rule_match = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.6,
        classifier_used=CLASSIFIER_RULE,
    )
    pipeline = IntentPipeline(
        rule_classifier=_stub_classifier(rule_match),
        llm_classifier=_stub_classifier(None),
    )
    result = await pipeline.classify("tôi đang giàu cỡ nào")
    assert result is rule_match


@pytest.mark.asyncio
async def test_llm_exception_falls_back_to_rule():
    rule_match = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=0.6,
        classifier_used=CLASSIFIER_RULE,
    )
    failing = MagicMock()
    failing.classify = MagicMock(side_effect=RuntimeError("api down"))
    pipeline = IntentPipeline(
        rule_classifier=_stub_classifier(rule_match),
        llm_classifier=failing,
    )
    result = await pipeline.classify("anything")
    assert result is rule_match


def test_threshold_is_advertised_constant():
    # Other modules dispatch on this value — guard against silent drift.
    assert 0 < HIGH_CONFIDENCE_THRESHOLD <= 1
