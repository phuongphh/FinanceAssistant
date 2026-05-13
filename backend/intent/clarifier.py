"""Clarification + confirmation message builder.

Loads ``content/clarification_messages.yaml`` once and exposes:

  - ``build_clarification(intent, user, **params)`` — for low-confidence
    queries; picks the right template bucket and renders it.
  - ``build_confirmation(intent_result, user)`` — for medium-confidence
    write intents; renders the confirm template with action details.

The dispatcher uses both. State persistence (pending_action,
awaiting_clarification) lives in ``pending_action_store.py`` because
it touches the DB.
"""
from __future__ import annotations

import logging
import random
from functools import lru_cache
from pathlib import Path

import yaml

from backend.intent.intents import IntentResult, IntentType
from backend.models.user import User

logger = logging.getLogger(__name__)

_CLARIFY_PATH = (
    Path(__file__).resolve().parents[2]
    / "content"
    / "clarification_messages.yaml"
)


@lru_cache(maxsize=1)
def _load() -> dict[str, list[str]]:
    if not _CLARIFY_PATH.exists():
        logger.warning("Clarification YAML missing at %s", _CLARIFY_PATH)
        return {}
    with _CLARIFY_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {k: list(v) for k, v in data.items() if isinstance(v, list)}


# Map intent → clarification YAML key. ``query_*`` intents share keys
# with ``query_*_by_category`` because the disambiguation surface is
# the same (asset type / time range / etc).
_INTENT_TO_CLARIFY_KEY = {
    IntentType.QUERY_ASSETS: "low_confidence_assets",
    IntentType.QUERY_NET_WORTH: "low_confidence_assets",
    IntentType.QUERY_PORTFOLIO: "low_confidence_assets",
    IntentType.QUERY_EXPENSES: "low_confidence_expenses",
    IntentType.QUERY_EXPENSES_BY_CATEGORY: "low_confidence_expenses",
    IntentType.QUERY_CASHFLOW: "low_confidence_expenses",
    IntentType.QUERY_INCOME: "low_confidence_expenses",
    IntentType.QUERY_MARKET: "low_confidence_market",
    IntentType.QUERY_GOALS: "low_confidence_goals",
    IntentType.QUERY_GOAL_PROGRESS: "low_confidence_goals",
    IntentType.ACTION_RECORD_SAVING: "low_confidence_action",
    IntentType.ACTION_QUICK_TRANSACTION: "low_confidence_action",
}


def build_clarification(
    intent: IntentType,
    user: User,
    **placeholders,
) -> str:
    """Render the clarification template for the given intent.

    Always returns a string — falls back to a generic prompt when the
    YAML key is missing so the user never sees a stack trace.
    """
    key = _INTENT_TO_CLARIFY_KEY.get(intent)
    templates = _load().get(key, []) if key else []
    if not templates:
        name = user.display_name or "bạn"
        return (
            f"Mình chưa hiểu lắm {name} ơi 🤔\n\n"
            "Bạn nói rõ hơn giúp mình nhé."
        )

    template = random.choice(templates)
    name = user.display_name or "bạn"
    return template.format(name=name, **placeholders)


def build_amount_confirmation(amount: int, user: User) -> str:
    templates = _load().get("ambiguous_amount", [])
    name = user.display_name or "bạn"
    formatted = f"{amount:,}"
    if templates:
        return random.choice(templates).format(name=name, amount=formatted)
    return f"Số tiền là {formatted}đ đúng không {name}?"


def build_action_confirmation(intent_result: IntentResult, user: User) -> str:
    """Render the confirm-before-write message for an action intent."""
    name = user.display_name or "bạn"
    params = intent_result.parameters or {}

    if intent_result.intent == IntentType.ACTION_RECORD_SAVING:
        amount = params.get("amount", 0)
        formatted = f"{int(amount):,}" if amount else "?"
        templates = _load().get("confirmation_action_record_saving", [])
        if templates:
            return random.choice(templates).format(
                name=name, amount=formatted
            )
        return (
            f"Mình hiểu bạn muốn ghi tiết kiệm {formatted}đ — đúng không {name}?"
        )

    if intent_result.intent == IntentType.ACTION_QUICK_TRANSACTION:
        amount = params.get("amount", 0)
        merchant = params.get("merchant") or "giao dịch"
        formatted = f"{int(amount):,}" if amount else "?"
        templates = _load().get("confirmation_action_quick_transaction", [])
        if templates:
            return random.choice(templates).format(
                name=name, amount=formatted, merchant=merchant
            )
        return (
            f"Mình hiểu bạn muốn ghi {formatted}đ cho {merchant} — đúng chưa {name}?"
        )

    # Fallback for any future write intent — generic confirm.
    return (
        f"Mình sẽ thực hiện *{intent_result.intent.value}* — xác nhận giúp mình {name}?"
    )


def build_awaiting_response(user: User) -> str:
    templates = _load().get("awaiting_response", [])
    name = user.display_name or "bạn"
    if templates:
        return random.choice(templates).format(name=name)
    return f"Mình đang đợi câu trả lời {name} ơi 🌱 — tap option ở trên hoặc /huy."


__all__ = [
    "build_action_confirmation",
    "build_amount_confirmation",
    "build_awaiting_response",
    "build_clarification",
]
