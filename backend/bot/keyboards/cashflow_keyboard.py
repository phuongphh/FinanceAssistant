"""Inline keyboards for Phase 4B Cashflow Forecasting v2 (Epic 3).

Callback prefixes — all handled by bot/handlers/cashflow_review.py:

    cashflow:confirm:<pattern_uuid>   — user confirms pattern is correct
    cashflow:dismiss:<pattern_uuid>   — snooze for 30 days
    cashflow:edit:<pattern_uuid>      — correct the amount
"""
from __future__ import annotations

import uuid

from backend.bot.keyboards.common import build_callback

InlineKeyboardMarkup = dict
CB_CASHFLOW = "cashflow"


def pattern_review_keyboard(pattern_id: uuid.UUID | str) -> InlineKeyboardMarkup:
    """Per-pattern review keyboard (S15) — shown once per detected pattern."""
    pid = str(pattern_id)
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Đúng",
                    "callback_data": build_callback(CB_CASHFLOW, "confirm", pid),
                },
                {
                    "text": "❌ Không phải",
                    "callback_data": build_callback(CB_CASHFLOW, "dismiss", pid),
                },
            ],
            [{
                "text": "✏️ Sửa số tiền",
                "callback_data": build_callback(CB_CASHFLOW, "edit", pid),
            }],
        ]
    }
