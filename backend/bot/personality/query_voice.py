"""Bé Tiền personality layer for Phase 3.5 query responses.

Adds warm Vietnamese personality on top of the structured handler text:
30% chance to prepend a greeting, 50% chance to append a follow-up
suggestion. Variation matters here — same handler firing twice in a
row should *feel* different even when the data is identical.

Critical invariants
-------------------
- Personality is applied ONLY to executed-handler responses. Never to
  clarifications, error messages, OOS, UNCLEAR — those stay literal so
  the user trusts what the bot is saying.
- Generic English-y phrases ("Here are your assets:", "Following are
  …") are forbidden. Tests assert their absence; if you ever see one
  in a real response something has gone wrong.
- The wrapper is deterministic in tests via ``rng_seed`` — production
  uses module-level ``random`` so production replies stay varied.

The dispatcher imports this module and wraps handler outputs at the
``OUTCOME_EXECUTED`` boundary in ``IntentDispatcher._execute``.
"""
from __future__ import annotations

import random
from typing import Iterable

from backend.intent.intents import IntentType
from backend.models.user import User


GREETING_PROBABILITY = 0.30
SUGGESTION_PROBABILITY = 0.50


# 5+ greetings per acceptance criteria. They MUST sound warm and
# Vietnamese; ASCII-only / English greetings are not allowed because
# they break the "Bé Tiền tone" promise.
_GREETINGS: tuple[str, ...] = (
    "{name} ơi,",
    "Hiểu rồi {name}!",
    "Cho mình check liền,",
    "Có ngay {name}!",
    "{name}, đây nè:",
    "Đây {name} ơi:",
)


# 5+ suggestion variations per intent (acceptance criteria) — only
# applied to read intents because action intents already have their
# own follow-up flow. Keep them short and end with an action verb so
# they read as invitations, not statements.
_SUGGESTIONS: dict[IntentType, tuple[str, ...]] = {
    IntentType.QUERY_ASSETS: (
        "Muốn xem chi tiết phần nào? 📊",
        "Mình có thể show trend 30 ngày nếu bạn muốn 📈",
        "Hỏi mình nếu cần breakdown sâu hơn 💎",
        "Bạn muốn so với tháng trước không?",
        "Tap /taisan nếu muốn xem dạng card 🎴",
    ),
    IntentType.QUERY_NET_WORTH: (
        "Muốn xem trend 6 tháng không? 📈",
        "Phân bổ chi tiết theo loại tài sản nhé?",
        "Bạn muốn so với tháng trước không?",
        "Tap mở Mini App để xem chart 📊",
    ),
    IntentType.QUERY_PORTFOLIO: (
        "Muốn xem chi tiết một mã không?",
        "Bạn quan tâm tới P&L của mã nào?",
        "Mình có thể tóm tắt thị trường VN — hỏi nhé 📊",
    ),
    IntentType.QUERY_EXPENSES: (
        "Bạn muốn so với tháng trước không? 📅",
        "Có muốn breakdown theo loại không? 🍕",
        "Xem top 10 giao dịch lớn nhất nhé?",
        "Mình có thể tách theo tuần nếu cần 📅",
    ),
    IntentType.QUERY_EXPENSES_BY_CATEGORY: (
        "Muốn xem các loại khác không?",
        "So với tháng trước cùng loại nhé?",
        "Bạn muốn xem total chi tiêu cả tháng không?",
    ),
    IntentType.QUERY_INCOME: (
        "Muốn so cashflow (thu - chi) tháng này không?",
        "Bạn có thêm nguồn thu nào chưa nhập? Tap /thunhap",
        "Mình có thể tính tỷ lệ thu nhập thụ động 🔍",
    ),
    IntentType.QUERY_CASHFLOW: (
        "Muốn xem chi tiết theo loại không? 🍕",
        "So với tháng trước nhé?",
        "Bạn muốn đặt mục tiêu tiết kiệm không? 🎯",
    ),
    IntentType.QUERY_MARKET: (
        "Muốn xem chi tiết phân tích không?",
        "Có thể giúp bạn check thêm mã khác 📊",
        "Bạn quan tâm thêm mã nào — hỏi mình nhé",
    ),
    IntentType.QUERY_GOALS: (
        "Bạn muốn cập nhật tiến độ không?",
        "Đặt thêm mục tiêu mới nhé? Tap /muctieu",
        "Muốn xem deadline gần nhất không? ⏰",
    ),
    IntentType.QUERY_GOAL_PROGRESS: (
        "Bạn muốn breakdown từng tháng nhé?",
        "Tap /muctieu để cập nhật số mới",
        "Mình có thể đề xuất kế hoạch tiết kiệm — hỏi nhé 🎯",
    ),
    IntentType.GREETING: (),
    IntentType.HELP: (),
}


# Phrases that betray the "generic AI assistant" voice — banned in any
# response that flows through this module. The test suite asserts
# absence; if a translator or future contributor sneaks one in, CI
# catches it.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "here are your",
    "following are",
    "here is the",
    "here's a list",
    "i can show you",
    "as an ai",
    "let me know if",
)


def _rng(seed: int | None) -> random.Random:
    return random.Random(seed) if seed is not None else random


def add_personality(
    response: str,
    user: User,
    intent_type: IntentType,
    *,
    rng_seed: int | None = None,
) -> str:
    """Wrap ``response`` with a maybe-greeting and maybe-suggestion.

    Idempotent on call: mutating the input is not safe (the caller
    might reuse it for analytics) so we only return a new string.
    """
    if not response:
        return response

    rng = _rng(rng_seed)
    out = response

    if rng.random() < GREETING_PROBABILITY:
        greeting = _pick_greeting(user, rng)
        if greeting and not _starts_with_greeting(out):
            out = f"{greeting} {out}"

    if rng.random() < SUGGESTION_PROBABILITY:
        suggestion = _pick_suggestion(intent_type, rng)
        if suggestion:
            out = f"{out}\n\n{suggestion}"

    return out


def _starts_with_greeting(text: str) -> bool:
    """Avoid stacking two greetings — many handlers already start with
    'Tài sản hiện tại của An:' which contains a name address. Only
    block when the response leads with the user-name-greeting pattern.
    """
    head = text.split("\n", 1)[0].lower()
    return any(head.startswith(seed) for seed in ("ơi", "hi ", "chào "))


def _pick_greeting(user: User, rng: random.Random) -> str:
    name = (user.display_name or "").strip() or "bạn"
    template = rng.choice(_GREETINGS)
    return template.format(name=name)


def _pick_suggestion(intent: IntentType, rng: random.Random) -> str | None:
    options = _SUGGESTIONS.get(intent)
    if not options:
        return None
    return rng.choice(options)


def get_suggestions_for_intent(intent: IntentType) -> tuple[str, ...]:
    """Read-only accessor used by the inline-button suggestion layer."""
    return _SUGGESTIONS.get(intent, ())


def assert_no_forbidden_phrases(text: str) -> None:
    """Test helper — raise AssertionError if ``text`` contains a banned
    generic-AI phrase. Public so callers / regressions can assert."""
    lower = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            raise AssertionError(
                f"Response contains forbidden generic phrase {phrase!r}: "
                f"{text[:120]}…"
            )


__all__ = [
    "FORBIDDEN_PHRASES",
    "GREETING_PROBABILITY",
    "SUGGESTION_PROBABILITY",
    "add_personality",
    "assert_no_forbidden_phrases",
    "get_suggestions_for_intent",
]
