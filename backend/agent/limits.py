"""Hard caps for the Phase 3.7 agent stack.

Every constant here shapes a worst-case (cost, latency, runaway-loop)
scenario, so changes are review-worthy. We deliberately keep these
out of ``Settings`` (env vars) — environment drift on cost ceilings
is exactly the kind of bug that costs $100 to discover.

If you need to tune for a load test, set the override at the call
site explicitly and revert before merge."""
from __future__ import annotations

# ---- Per-query caps -------------------------------------------------

# Max tool invocations the Tier 3 reasoning agent may issue before
# we force a final answer. Five gives Claude room to "look up assets,
# look up market, look up trend, then synthesise" without enabling
# pathological loops.
MAX_TOOL_CALLS_PER_QUERY = 5

# Hard wall-clock cap on Tier 3 — wraps the entire multi-tool loop
# in ``asyncio.wait_for``. Tier 3 streams, so the user sees partial
# output before this fires; the cap exists for runaway scenarios.
QUERY_TIMEOUT_SECONDS = 30

# Tier 2 inherits the OpenAI client's 15 s timeout already; this
# constant is here so future call sites can wait_for the agent itself.
TIER2_TIMEOUT_SECONDS = 20

# ---- Per-user rate limits ------------------------------------------

# Tier 3 is expensive (~$0.005/call). 10/hour/user lets a focussed
# session run without abusing the credit; admins can opt specific
# users out via the allowlist (see ``RateLimiter.allow_unlimited``).
MAX_TIER3_QUERIES_PER_HOUR = 10

# Total queries (any tier) per user per hour. Catches buggy clients
# spamming the bot more than abusing tier 3 specifically.
MAX_TOTAL_QUERIES_PER_HOUR = 100

# ---- Daily cost monitoring -----------------------------------------

# Soft alert: log + (future) emit metric.
COST_ALERT_THRESHOLD_DAILY_USD = 5.0

# Hard kill-switch: refuse new agent calls for the rest of the day
# once we've burned this much. Returns a graceful "đợi 1 lát nhé"
# response to the user.
COST_HARD_LIMIT_DAILY_USD = 20.0


# ---- Pricing (USD per 1M tokens) -----------------------------------
# Mid-2026 list prices. If they drift far enough that the daily-cost
# math becomes inaccurate, update here — single source of truth.
DEEPSEEK_PRICE_INPUT_PER_M = 0.14
DEEPSEEK_PRICE_OUTPUT_PER_M = 0.28
CLAUDE_SONNET_PRICE_INPUT_PER_M = 3.0
CLAUDE_SONNET_PRICE_OUTPUT_PER_M = 15.0


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return the dollar cost of a single LLM call.

    ``model`` is matched as a prefix so "deepseek-chat" /
    "deepseek-reasoner" all map to the same pricing — Anthropic's
    versioned model IDs ("claude-sonnet-4-5-20250929") match the
    "claude-sonnet" prefix.
    """
    m = (model or "").lower()
    if m.startswith("deepseek"):
        return (
            input_tokens / 1_000_000 * DEEPSEEK_PRICE_INPUT_PER_M
            + output_tokens / 1_000_000 * DEEPSEEK_PRICE_OUTPUT_PER_M
        )
    if "sonnet" in m or "claude" in m:
        return (
            input_tokens / 1_000_000 * CLAUDE_SONNET_PRICE_INPUT_PER_M
            + output_tokens / 1_000_000 * CLAUDE_SONNET_PRICE_OUTPUT_PER_M
        )
    return 0.0
