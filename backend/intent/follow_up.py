"""Follow-up suggestions as inline keyboard buttons.

Phase 3.5 — Story #128. Each executed read-intent response gets up to
3 inline buttons that pre-fill the next likely question. Buttons emit
``followup:<intent>:<encoded-params>`` callbacks so the worker can
re-route to the same intent flow without re-classifying the user's text.

Wealth-aware
------------
Starter sees beginner suggestions ("Cách thêm tài sản"); HNW sees
advanced ones ("YTD return", "phân bổ chi tiết"). The picker takes
``WealthLevel`` and selects from a per-level pool, falling back to the
shared pool when a level has no specific suggestion.

Dedup
-----
``avoid_intent`` lets callers exclude the intent the user JUST asked
about — no point offering "view your assets" when they just saw their
assets.
"""
from __future__ import annotations

import json
import logging
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass

from backend.intent.intents import IntentType
from backend.wealth.ladder import WealthLevel

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 3
CALLBACK_PREFIX = "followup:"


# Short codes for intents — cuts bytes off every callback payload. The
# Telegram limit is 64 bytes; the long form ``query_expenses_by_category``
# alone burns 26 bytes before we even encode parameters.
_INTENT_TO_CODE: dict[IntentType, str] = {
    IntentType.QUERY_ASSETS: "qa",
    IntentType.QUERY_NET_WORTH: "qn",
    IntentType.QUERY_PORTFOLIO: "qp",
    IntentType.QUERY_EXPENSES: "qe",
    IntentType.QUERY_EXPENSES_BY_CATEGORY: "qc",
    IntentType.QUERY_INCOME: "qi",
    IntentType.QUERY_CASHFLOW: "qf",
    IntentType.QUERY_MARKET: "qm",
    IntentType.QUERY_GOALS: "qg",
    IntentType.QUERY_GOAL_PROGRESS: "qx",
    IntentType.ADVISORY: "ad",
    IntentType.PLANNING: "pl",
    IntentType.HELP: "hl",
    IntentType.GREETING: "gr",
}
_CODE_TO_INTENT: dict[str, IntentType] = {v: k for k, v in _INTENT_TO_CODE.items()}


@dataclass(frozen=True)
class FollowUp:
    """One follow-up suggestion — label + the intent it triggers."""
    label: str
    intent: IntentType
    parameters: dict | None = None

    def to_callback_data(self) -> str:
        """Compact, URL-safe encoded callback.

        Telegram caps callback_data at 64 bytes so we keep the payload
        short: 2-char intent code + base64-encoded JSON of parameters
        (omitted when empty). For most follow-ups the result is well
        under 30 bytes; the 64-byte ceiling only matters for params
        with long string values.
        """
        code = _INTENT_TO_CODE.get(self.intent, self.intent.value[:8])
        if not self.parameters:
            return f"{CALLBACK_PREFIX}{code}"
        encoded = urlsafe_b64encode(
            json.dumps(self.parameters, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        return f"{CALLBACK_PREFIX}{code}.{encoded}"


# Per-intent suggestion pool. Order matters — earlier entries are
# preferred when MAX_SUGGESTIONS clips the list. Each entry can target
# ANY intent (not necessarily the same one as the parent), which is
# how cross-navigation works ("after seeing assets, suggest net worth").
_BASE_SUGGESTIONS: dict[IntentType, tuple[FollowUp, ...]] = {
    IntentType.QUERY_ASSETS: (
        FollowUp("📈 So với tháng trước", IntentType.QUERY_NET_WORTH),
        FollowUp("🏠 Chỉ BĐS", IntentType.QUERY_ASSETS, {"asset_type": "real_estate"}),
        FollowUp("💎 Tổng net worth", IntentType.QUERY_NET_WORTH),
        FollowUp("📈 Cổ phiếu", IntentType.QUERY_PORTFOLIO),
    ),
    IntentType.QUERY_NET_WORTH: (
        FollowUp("📊 Phân bổ chi tiết", IntentType.QUERY_ASSETS),
        FollowUp("📈 Trend 6 tháng", IntentType.QUERY_NET_WORTH, {"trend_days": 180}),
        FollowUp("🎯 Mục tiêu của tôi", IntentType.QUERY_GOALS),
    ),
    IntentType.QUERY_PORTFOLIO: (
        FollowUp("💼 Net worth tổng", IntentType.QUERY_NET_WORTH),
        FollowUp("📊 Xem mã khác", IntentType.QUERY_MARKET),
        FollowUp("📊 Tài sản chi tiết", IntentType.QUERY_ASSETS),
    ),
    IntentType.QUERY_EXPENSES: (
        FollowUp("📅 Tuần này", IntentType.QUERY_EXPENSES, {"time_range": "this_week"}),
        FollowUp("🍕 Theo loại", IntentType.QUERY_EXPENSES_BY_CATEGORY),
        FollowUp("📊 So sánh tháng trước", IntentType.QUERY_EXPENSES, {"time_range": "last_month"}),
    ),
    IntentType.QUERY_EXPENSES_BY_CATEGORY: (
        FollowUp("📅 Tháng trước", IntentType.QUERY_EXPENSES, {"time_range": "last_month"}),
        FollowUp("📊 Tổng chi tiêu", IntentType.QUERY_EXPENSES),
        FollowUp("🍕 Loại khác", IntentType.QUERY_EXPENSES_BY_CATEGORY),
    ),
    IntentType.QUERY_INCOME: (
        FollowUp("💸 Cashflow tháng này", IntentType.QUERY_CASHFLOW),
        FollowUp("📊 Chi tiêu tháng này", IntentType.QUERY_EXPENSES),
        FollowUp("🎯 Mục tiêu", IntentType.QUERY_GOALS),
    ),
    IntentType.QUERY_CASHFLOW: (
        FollowUp("💸 Chi tiêu chi tiết", IntentType.QUERY_EXPENSES),
        FollowUp("💼 Thu nhập", IntentType.QUERY_INCOME),
        FollowUp("🎯 Mục tiêu", IntentType.QUERY_GOALS),
    ),
    IntentType.QUERY_MARKET: (
        FollowUp("💼 Portfolio của tôi", IntentType.QUERY_PORTFOLIO),
        FollowUp("📊 Net worth tổng", IntentType.QUERY_NET_WORTH),
        FollowUp("💎 Tài sản chi tiết", IntentType.QUERY_ASSETS),
    ),
    IntentType.QUERY_GOALS: (
        FollowUp("📊 Net worth", IntentType.QUERY_NET_WORTH),
        FollowUp("💼 Thu nhập", IntentType.QUERY_INCOME),
        FollowUp("💸 Chi tiêu tháng", IntentType.QUERY_EXPENSES),
    ),
    IntentType.QUERY_GOAL_PROGRESS: (
        FollowUp("📋 Tất cả mục tiêu", IntentType.QUERY_GOALS),
        FollowUp("💼 Thu nhập", IntentType.QUERY_INCOME),
        FollowUp("💸 Cashflow tháng", IntentType.QUERY_CASHFLOW),
    ),
}


# Wealth-level overrides — Starter gets gentler "how do I add" prompts,
# HNW gets analytics-first prompts. Missing entries fall back to base.
_LEVEL_OVERRIDES: dict[
    tuple[IntentType, WealthLevel], tuple[FollowUp, ...]
] = {
    (IntentType.QUERY_ASSETS, WealthLevel.STARTER): (
        FollowUp("➕ Thêm tài sản", IntentType.HELP),
        FollowUp("💎 Net worth tổng", IntentType.QUERY_NET_WORTH),
        FollowUp("🎯 Đặt mục tiêu", IntentType.QUERY_GOALS),
    ),
    (IntentType.QUERY_NET_WORTH, WealthLevel.STARTER): (
        FollowUp("➕ Thêm tài sản", IntentType.HELP),
        FollowUp("🎯 Mục tiêu", IntentType.QUERY_GOALS),
    ),
    (IntentType.QUERY_ASSETS, WealthLevel.HIGH_NET_WORTH): (
        FollowUp("📊 Phân bổ chi tiết", IntentType.QUERY_NET_WORTH),
        FollowUp("📈 YTD return", IntentType.QUERY_PORTFOLIO),
        FollowUp("💼 Portfolio detail", IntentType.QUERY_PORTFOLIO),
    ),
    (IntentType.QUERY_NET_WORTH, WealthLevel.HIGH_NET_WORTH): (
        FollowUp("📈 Trend 6 tháng", IntentType.QUERY_NET_WORTH, {"trend_days": 180}),
        FollowUp("📊 Phân bổ chi tiết", IntentType.QUERY_ASSETS),
        FollowUp("💼 Portfolio analytics", IntentType.QUERY_PORTFOLIO),
    ),
}


def get_follow_ups(
    intent: IntentType,
    *,
    wealth_level: WealthLevel | None = None,
    avoid_intent: IntentType | None = None,
) -> list[FollowUp]:
    """Pick up to ``MAX_SUGGESTIONS`` relevant suggestions.

    Wealth-level overrides take precedence; the base pool fills the
    rest if the override list is shorter than the cap. ``avoid_intent``
    drops suggestions that point back at the just-asked intent — the
    user already has that answer on screen.
    """
    pool: list[FollowUp] = []
    if wealth_level is not None:
        override = _LEVEL_OVERRIDES.get((intent, wealth_level))
        if override:
            pool.extend(override)
    pool.extend(_BASE_SUGGESTIONS.get(intent, ()))

    seen: set[tuple[IntentType, str]] = set()
    out: list[FollowUp] = []
    for fu in pool:
        if avoid_intent is not None and fu.intent == avoid_intent:
            continue
        key = (fu.intent, json.dumps(fu.parameters or {}, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        out.append(fu)
        if len(out) >= MAX_SUGGESTIONS:
            break
    return out


def build_inline_keyboard(follow_ups: list[FollowUp]) -> dict | None:
    """Telegram inline-keyboard payload — one button per row so labels
    don't truncate on narrow screens."""
    if not follow_ups:
        return None
    return {
        "inline_keyboard": [
            [
                {
                    "text": fu.label,
                    "callback_data": fu.to_callback_data(),
                }
            ]
            for fu in follow_ups
        ]
    }


def parse_callback_data(callback_data: str) -> FollowUp | None:
    """Reverse of ``FollowUp.to_callback_data``.

    Format: ``followup:<code>`` (no params) or ``followup:<code>.<b64>``
    (with params). Returns None for malformed payloads.
    """
    if not callback_data.startswith(CALLBACK_PREFIX):
        return None
    rest = callback_data[len(CALLBACK_PREFIX):]
    if "." in rest:
        code, encoded = rest.split(".", 1)
    else:
        code, encoded = rest, ""

    intent = _CODE_TO_INTENT.get(code)
    if intent is None:
        # Backwards-compat: support the long-form intent value too.
        try:
            intent = IntentType(code)
        except ValueError:
            logger.debug("Bad follow-up callback_data: %r", callback_data)
            return None

    params: dict | None = None
    if encoded:
        padding = "=" * (-len(encoded) % 4)
        try:
            raw = urlsafe_b64decode(encoded + padding).decode()
            params = json.loads(raw)
            if not isinstance(params, dict):
                params = None
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("Bad follow-up params: %r", callback_data)
            return None

    return FollowUp(label="", intent=intent, parameters=params or None)


__all__ = [
    "CALLBACK_PREFIX",
    "FollowUp",
    "MAX_SUGGESTIONS",
    "build_inline_keyboard",
    "get_follow_ups",
    "parse_callback_data",
]
