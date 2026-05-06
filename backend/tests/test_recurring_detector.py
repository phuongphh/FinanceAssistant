"""Unit tests for ``backend.services.recurring_detector``.

Spec scenarios from § P3.8-S8 acceptance:
- 4 months in a row of "thuê nhà 15tr" → detected.
- Different restaurants × 4 same amount → NOT detected (different
  category/amount buckets).

Also exercise the de-spam guards (existing pattern + recently-rejected
fingerprint).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.expense import Expense
from backend.models.recurring_pattern import (
    PatternSuggestionLog,
    RecurringPattern,
)
from backend.services import recurring_detector


def _expense(
    *,
    user_id: uuid.UUID,
    amount: Decimal,
    expense_date: date,
    category: str = "housing",
    merchant: str | None = None,
    recurrence_id: uuid.UUID | None = None,
) -> Expense:
    e = Expense()
    e.id = uuid.uuid4()
    e.user_id = user_id
    e.amount = amount
    e.currency = "VND"
    e.merchant = merchant
    e.category = category
    e.source = "manual"
    e.expense_date = expense_date
    e.month_key = expense_date.strftime("%Y-%m")
    e.is_recurring = recurrence_id is not None
    e.recurrence_id = recurrence_id
    e.deleted_at = None
    return e


# ---------------------------------------------------------------------
# Heuristic tests — pure function, no DB needed.
# ---------------------------------------------------------------------


class TestLooksRecurring:
    def test_three_monthly_occurrences_detected(self):
        user_id = uuid.uuid4()
        txns = [
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, 1, 5)),
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, 2, 5)),
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, 3, 5)),
        ]
        assert recurring_detector._looks_recurring(txns) is True

    def test_two_occurrences_not_enough(self):
        user_id = uuid.uuid4()
        txns = [
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, 1, 5)),
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, 2, 5)),
        ]
        assert recurring_detector._looks_recurring(txns) is False

    def test_weekly_cadence_rejected(self):
        """Same amount every week ≠ monthly recurring expense."""
        user_id = uuid.uuid4()
        txns = [
            _expense(user_id=user_id, amount=Decimal("100000"),
                     expense_date=date(2026, 1, 5) + timedelta(days=7 * i))
            for i in range(4)
        ]
        assert recurring_detector._looks_recurring(txns) is False

    def test_yearly_cadence_rejected(self):
        """Annual interval > 35 days → not "monthly recurring"."""
        user_id = uuid.uuid4()
        txns = [
            _expense(user_id=user_id, amount=Decimal("100000"),
                     expense_date=date(2024, 1, 5)),
            _expense(user_id=user_id, amount=Decimal("100000"),
                     expense_date=date(2025, 1, 5)),
            _expense(user_id=user_id, amount=Decimal("100000"),
                     expense_date=date(2026, 1, 5)),
        ]
        assert recurring_detector._looks_recurring(txns) is False


class TestFingerprint:
    def test_same_category_same_bucket_collide(self):
        # 14_950_000 and 15_000_000 round to the same 100k bucket.
        fp_a = recurring_detector._fingerprint("housing", Decimal("15000000"))
        fp_b = recurring_detector._fingerprint("housing", Decimal("14950000"))
        assert fp_a == fp_b

    def test_amount_drift_to_different_bucket(self):
        # 15tr vs 14tr: clearly different bucket.
        fp_a = recurring_detector._fingerprint("housing", Decimal("15000000"))
        fp_b = recurring_detector._fingerprint("housing", Decimal("14000000"))
        assert fp_a != fp_b

    def test_different_categories_different_fingerprints(self):
        fp_a = recurring_detector._fingerprint("housing", Decimal("500000"))
        fp_b = recurring_detector._fingerprint("utility", Decimal("500000"))
        assert fp_a != fp_b


# ---------------------------------------------------------------------
# detect_patterns end-to-end (with mocked DB returns).
# ---------------------------------------------------------------------


def _result_with_rows(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _mock_session(execute_returns: list) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.side_effect = execute_returns
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
class TestDetectPatterns:
    async def test_spec_rent_4_months_detected(self):
        """Spec: User pays 15tr 'thuê nhà' 4 months in a row → detected."""
        user_id = uuid.uuid4()
        rent = [
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, m, 5), category="housing",
                     merchant="Chủ nhà")
            for m in (1, 2, 3, 4)
        ]
        db = _mock_session([
            _result_with_rows(rent),    # _load_recent_expenses
            _result_with_rows([]),      # existing patterns
            _result_with_rows([]),      # rejected fingerprints
        ])
        suggestions = await recurring_detector.detect_patterns(
            db, user_id, today=date(2026, 5, 1),
        )
        assert len(suggestions) == 1
        s = suggestions[0]
        assert s["category"] == "housing"
        assert s["occurrences"] == 4
        assert s["typical_day"] == 5
        assert s["merchant_hint"] == "Chủ nhà"

    async def test_different_restaurants_not_detected(self):
        """Spec: 4 different restaurant lunches at similar amounts on
        irregular days → NOT detected (intervals don't fit monthly)."""
        user_id = uuid.uuid4()
        # Same category + same amount but ~weekly cadence.
        meals = [
            _expense(user_id=user_id, amount=Decimal("200000"),
                     expense_date=date(2026, 1, 5) + timedelta(days=7 * i),
                     category="food", merchant=f"Quán {i}")
            for i in range(4)
        ]
        db = _mock_session([
            _result_with_rows(meals),
            _result_with_rows([]),
            _result_with_rows([]),
        ])
        suggestions = await recurring_detector.detect_patterns(
            db, user_id, today=date(2026, 2, 1),
        )
        assert suggestions == []

    async def test_existing_pattern_skipped(self):
        """If user already confirmed a "rent 15tr" pattern, the
        detector shouldn't re-suggest it."""
        user_id = uuid.uuid4()
        rent = [
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, m, 5), category="housing")
            for m in (1, 2, 3, 4)
        ]
        existing = RecurringPattern()
        existing.id = uuid.uuid4()
        existing.user_id = user_id
        existing.category = "housing"
        existing.expected_amount = Decimal("15000000")
        existing.is_active = True
        db = _mock_session([
            _result_with_rows(rent),
            _result_with_rows([existing]),
            _result_with_rows([]),
        ])
        suggestions = await recurring_detector.detect_patterns(
            db, user_id, today=date(2026, 5, 1),
        )
        assert suggestions == []

    async def test_recent_rejection_skipped(self):
        """User rejected this fingerprint last week → don't re-suggest."""
        user_id = uuid.uuid4()
        rent = [
            _expense(user_id=user_id, amount=Decimal("15000000"),
                     expense_date=date(2026, m, 5), category="housing")
            for m in (1, 2, 3, 4)
        ]
        rejected = PatternSuggestionLog()
        rejected.user_id = user_id
        rejected.fingerprint = recurring_detector._fingerprint(
            "housing", Decimal("15000000"),
        )
        rejected.outcome = "rejected"
        rejected.suggested_at = datetime.utcnow()
        db = _mock_session([
            _result_with_rows(rent),
            _result_with_rows([]),
            _result_with_rows([rejected]),
        ])
        suggestions = await recurring_detector.detect_patterns(
            db, user_id, today=date(2026, 5, 1),
        )
        assert suggestions == []


@pytest.mark.asyncio
class TestPersistAndDeliver:
    async def test_rate_limit_respects_3_per_week(self):
        """If the user already received 3 suggestions in the last 7
        days, the function returns an empty list — no new log rows."""
        user_id = uuid.uuid4()
        # Three already-this-week log rows.
        last_week_logs = [PatternSuggestionLog() for _ in range(3)]
        db = _mock_session([_result_with_rows(last_week_logs)])
        suggestions = [
            {"fingerprint": "housing|150",
             "category": "housing", "amount": Decimal("15000000"),
             "occurrences": 4, "typical_day": 5},
        ]
        saved = await recurring_detector.persist_and_deliver(
            db, user_id, suggestions, today=date(2026, 5, 1),
        )
        assert saved == []
        # No log row added — db.add should not have received a
        # PatternSuggestionLog instance.
        added = [c.args[0] for c in db.add.call_args_list]
        assert not any(isinstance(x, PatternSuggestionLog) for x in added)

    async def test_under_quota_creates_log_rows(self):
        user_id = uuid.uuid4()
        db = _mock_session([_result_with_rows([])])  # 0 this week
        suggestions = [
            {"fingerprint": "housing|150",
             "category": "housing", "amount": Decimal("15000000"),
             "occurrences": 4, "typical_day": 5},
        ]
        saved = await recurring_detector.persist_and_deliver(
            db, user_id, suggestions, today=date(2026, 5, 1),
        )
        assert len(saved) == 1
        assert saved[0].user_id == user_id
        assert saved[0].fingerprint == "housing|150"


class TestFormatSuggestionMessage:
    def test_message_contains_spec_fields(self):
        msg = recurring_detector.format_suggestion_message({
            "category": "housing",
            "amount": Decimal("15000000"),
            "occurrences": 4,
            "typical_day": 5,
            "merchant_hint": "Chủ nhà",
        })
        assert "Nhà cửa" in msg or "🏠" in msg
        assert "5" in msg  # day
        assert "4" in msg  # occurrences
        assert "Có phải hàng tháng" in msg
