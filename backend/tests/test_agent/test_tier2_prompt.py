"""Tier-2 DB-Agent prompt — routing-guidance regression tests.

These lock the disambiguation that prevents "tổng chi tiêu tháng này"
from being steered to ``compute_metric`` (which has no total-expense
metric) and then escalating to Tier 3. The total of expense rows is
already produced by ``get_transactions.total_amount``, so summing
spending must route there — only derived metrics (average, ratio,
growth, portfolio PnL) belong to ``compute_metric``.
"""
from __future__ import annotations

from datetime import date

from backend.agent.tier2.prompts import build_db_agent_prompt


class TestTier2PromptRouting:
    def test_today_is_baked_in(self):
        prompt = build_db_agent_prompt(today=date(2026, 5, 26))
        assert "2026-05-26" in prompt

    def test_total_spending_routes_to_get_transactions(self):
        prompt = build_db_agent_prompt()
        # The worked example must steer "tổng chi tiêu tháng này" to the
        # transactions tool, not the metric tool.
        assert "Tổng chi tiêu tháng này" in prompt
        idx = prompt.index("Tổng chi tiêu tháng này")
        # Scope to this bullet only (up to the next "- " example).
        example = prompt[idx : prompt.index("\n-", idx)]
        assert "get_transactions" in example
        assert "compute_metric" not in example

    def test_rule_forbids_compute_metric_for_total_spending(self):
        prompt = build_db_agent_prompt()
        assert "KHÔNG dùng compute_metric để cộng tổng chi tiêu" in prompt

    def test_derived_metrics_still_route_to_compute_metric(self):
        prompt = build_db_agent_prompt()
        # The portfolio-PnL example stays on compute_metric.
        idx = prompt.index("Tổng lãi portfolio")
        following = prompt[idx : idx + 120]
        assert "compute_metric" in following
