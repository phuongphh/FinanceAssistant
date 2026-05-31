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
# Mid-2026 list prices. SINGLE SOURCE OF TRUTH for token pricing across
# the whole codebase. Both the global daily kill-switch
# (``estimate_cost_usd`` below) and the per-user monthly budget
# (``budget_service.estimate_call_cost_vnd``, which imports these same
# numbers) derive from these constants, so the USD and VND ledgers can
# never quote different rates for the same provider. The intent-layer
# Tier 1 analytics cost (``classifier/llm_based.py``) also calls
# ``estimate_cost_usd`` rather than redeclaring rates. If a vendor
# changes their rate card, edit ONLY here.
DEEPSEEK_PRICE_INPUT_PER_M = 0.14
DEEPSEEK_PRICE_OUTPUT_PER_M = 0.28
GROQ_PRICE_INPUT_PER_M = 0.59
GROQ_PRICE_OUTPUT_PER_M = 0.79
CLAUDE_SONNET_PRICE_INPUT_PER_M = 3.0
CLAUDE_SONNET_PRICE_OUTPUT_PER_M = 15.0

# Canonical pricing table keyed by model family. ``estimate_cost_usd``
# resolves a model string to one of these keys; ``PROVIDER_TO_PRICING_KEY``
# maps the provider labels used by ``budget_service`` onto the same keys.
MODEL_PRICING_USD_PER_M: dict[str, tuple[float, float]] = {
    "deepseek": (DEEPSEEK_PRICE_INPUT_PER_M, DEEPSEEK_PRICE_OUTPUT_PER_M),
    "groq": (GROQ_PRICE_INPUT_PER_M, GROQ_PRICE_OUTPUT_PER_M),
    "sonnet": (CLAUDE_SONNET_PRICE_INPUT_PER_M, CLAUDE_SONNET_PRICE_OUTPUT_PER_M),
}


def resolve_pricing_key(model: str) -> str | None:
    """Map a model string to a ``MODEL_PRICING_USD_PER_M`` key.

    ``deepseek-v4-flash`` / ``deepseek-reasoner`` match by prefix; Groq's
    Llama family matches the ``llama``/``groq`` substring; Anthropic's
    versioned IDs (``claude-sonnet-4-6``, ``claude-sonnet-4-5-20250929``)
    match the ``claude``/``sonnet`` substring — 4.5 and 4.6 share the
    same $3/$15 list price. Unknown models return ``None``.
    """
    m = (model or "").lower()
    if m.startswith("deepseek"):
        return "deepseek"
    if "llama" in m or "groq" in m:
        return "groq"
    if "sonnet" in m or "claude" in m:
        return "sonnet"
    return None


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return the dollar cost of a single LLM call.

    Rates come from :data:`MODEL_PRICING_USD_PER_M`. Unknown models
    return ``0.0`` so a typo can never over-bill the kill-switch.
    """
    key = resolve_pricing_key(model)
    if key is None:
        return 0.0
    input_per_m, output_per_m = MODEL_PRICING_USD_PER_M[key]
    return (
        input_tokens / 1_000_000 * input_per_m
        + output_tokens / 1_000_000 * output_per_m
    )
