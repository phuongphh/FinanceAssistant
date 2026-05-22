"""Unit tests for the Groq pricing branches added with the Tier 1 swap.

Covers:
  - ``estimate_call_cost_vnd(provider="groq", ...)`` — split input/output.
  - ``estimate_cost_usd(model="llama-...", ...)`` — Groq pricing route.
  - DeepSeek and Claude paths remain untouched.

These are pure functions (no DB, no network), so the assertions are
direct math against the published per-1M rates.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.agent.limits import (
    CLAUDE_SONNET_PRICE_INPUT_PER_M,
    CLAUDE_SONNET_PRICE_OUTPUT_PER_M,
    DEEPSEEK_PRICE_INPUT_PER_M,
    DEEPSEEK_PRICE_OUTPUT_PER_M,
    GROQ_PRICE_INPUT_PER_M,
    GROQ_PRICE_OUTPUT_PER_M,
    estimate_cost_usd,
)
from backend.services.cost.budget_service import (
    USD_VND_RATE,
    estimate_call_cost_vnd,
)


# ----- estimate_call_cost_vnd ---------------------------------------


def test_estimate_call_cost_vnd_groq_splits_input_output():
    # 1000 in + 500 out — Groq charges different rates.
    cost = estimate_call_cost_vnd(provider="groq", tokens_in=1000, tokens_out=500)
    expected_usd = (
        Decimal(1000) * (Decimal("0.59") / Decimal("1_000_000"))
        + Decimal(500) * (Decimal("0.79") / Decimal("1_000_000"))
    )
    expected_vnd = (expected_usd * USD_VND_RATE).quantize(Decimal("0.0001"))
    assert cost == expected_vnd


def test_estimate_call_cost_vnd_groq_zero_tokens_is_zero():
    assert estimate_call_cost_vnd(provider="groq") == Decimal("0.0000")


def test_estimate_call_cost_vnd_deepseek_path_unchanged():
    # DeepSeek uses a blended single rate; verify it still computes
    # against tokens_in + tokens_out and the existing rate.
    cost = estimate_call_cost_vnd(
        provider="deepseek", tokens_in=1000, tokens_out=500
    )
    expected_usd = Decimal(1500) * (Decimal("0.27") / Decimal("1_000_000"))
    expected_vnd = (expected_usd * USD_VND_RATE).quantize(Decimal("0.0001"))
    assert cost == expected_vnd


def test_estimate_call_cost_vnd_unknown_provider_returns_zero():
    assert estimate_call_cost_vnd(provider="bogus", tokens_in=999) == Decimal("0")


# ----- estimate_cost_usd --------------------------------------------


def test_estimate_cost_usd_llama_model_routes_to_groq_pricing():
    # 1M in + 1M out → exactly the per-M rates summed.
    cost = estimate_cost_usd(
        model="llama-3.3-70b-versatile",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    expected = GROQ_PRICE_INPUT_PER_M + GROQ_PRICE_OUTPUT_PER_M
    assert cost == pytest.approx(expected)


def test_estimate_cost_usd_groq_substring_also_matches():
    # The matcher accepts "groq" as a substring too, so a generic
    # "groq-llama" identifier still picks Groq rates.
    cost = estimate_cost_usd(
        model="groq-llama-3", input_tokens=500_000, output_tokens=0
    )
    assert cost == pytest.approx(GROQ_PRICE_INPUT_PER_M / 2)


def test_estimate_cost_usd_deepseek_prefix_unchanged():
    cost = estimate_cost_usd(
        model="deepseek-v4-flash",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    expected = DEEPSEEK_PRICE_INPUT_PER_M + DEEPSEEK_PRICE_OUTPUT_PER_M
    assert cost == pytest.approx(expected)


def test_estimate_cost_usd_claude_substring_unchanged():
    cost = estimate_cost_usd(
        model="claude-sonnet-4-5-20250929",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    expected = CLAUDE_SONNET_PRICE_INPUT_PER_M + CLAUDE_SONNET_PRICE_OUTPUT_PER_M
    assert cost == pytest.approx(expected)


def test_estimate_cost_usd_unknown_model_returns_zero():
    assert estimate_cost_usd(model="mystery", input_tokens=999, output_tokens=999) == 0.0
