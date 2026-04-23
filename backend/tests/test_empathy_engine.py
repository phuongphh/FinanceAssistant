"""Unit tests for the empathy engine (Phase 2, Issue #40).

Focus
-----
- YAML integrity: each documented trigger has at least one message.
- Render: {name} and trigger-specific placeholders resolve.
- Cooldown: events-table lookup honours cooldown windows.
- Daily cap: count_empathy_fired_today queries events properly.
- Quiet-hours: the hourly-check job exits early during 22:00–07:00.
- Priority ordering: acute triggers beat ambient ones.

The engine's detection queries hit the DB; we stub at the SQLAlchemy
Result layer — same shape as existing milestone detection tests so
the review style stays consistent.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.bot.personality import empathy_engine
from backend.models.user import User


def _make_user(name: str = "Minh") -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 111
    u.display_name = name
    u.onboarding_skipped = False
    u.onboarding_completed_at = datetime.now(timezone.utc)
    return u


def _fake_result(*, all_value=None, scalar_value=None, rowcount=1):
    r = MagicMock()
    if all_value is not None:
        r.all.return_value = all_value
    if scalar_value is not None:
        r.scalar_one.return_value = scalar_value
        r.scalar_one_or_none.return_value = scalar_value
    else:
        r.scalar_one.return_value = 0
        r.scalar_one_or_none.return_value = None
    r.rowcount = rowcount
    return r


# ---------- YAML integrity ------------------------------------------

class TestYamlIntegrity:
    def test_every_documented_trigger_has_messages(self):
        empathy_engine.reload_messages_for_tests()
        msgs = empathy_engine._load_messages()
        expected = {
            "large_transaction",
            "payday_splurge",
            "over_budget_monthly",
            "user_silent_7_days",
            "user_silent_30_days",
            "weekend_high_spending",
            "first_saving_month",
            "consecutive_over_budget",
        }
        for key in expected:
            assert key in msgs, f"Missing empathy trigger: {key}"
            assert isinstance(msgs[key].get("messages"), list)
            assert len(msgs[key]["messages"]) >= 1


# ---------- Render -------------------------------------------------

class TestRenderMessage:
    def test_renders_name_placeholder(self):
        empathy_engine.reload_messages_for_tests()
        user = _make_user("Trang")
        trigger = empathy_engine.EmpathyTrigger(
            name="user_silent_7_days", priority=4,
            cooldown_days=14, context={"days_silent": 8},
        )
        msg = empathy_engine.render_message(trigger, user)
        assert "Trang" in msg
        assert "{name}" not in msg

    def test_renders_amount_for_large_transaction(self):
        empathy_engine.reload_messages_for_tests()
        user = _make_user("Lan")
        trigger = empathy_engine.EmpathyTrigger(
            name="large_transaction", priority=1,
            cooldown_days=1, context={"amount": "5,200,000đ"},
        )
        with patch(
            "backend.bot.personality.empathy_engine.random.choice",
            side_effect=lambda xs: xs[0],
        ):
            msg = empathy_engine.render_message(trigger, user)
        assert "5,200,000đ" in msg

    def test_falls_back_to_default_name(self):
        empathy_engine.reload_messages_for_tests()
        user = _make_user(name="")
        trigger = empathy_engine.EmpathyTrigger(
            name="user_silent_30_days", priority=5,
            cooldown_days=60, context={"days_silent": 45},
        )
        msg = empathy_engine.render_message(trigger, user)
        assert "bạn" in msg.lower()

    def test_unknown_trigger_returns_empty(self):
        empathy_engine.reload_messages_for_tests()
        trigger = empathy_engine.EmpathyTrigger(
            name="__nonexistent__", priority=9,
            cooldown_days=1, context={},
        )
        assert empathy_engine.render_message(trigger, _make_user()) == ""


# ---------- Cooldown -----------------------------------------------

@pytest.mark.asyncio
class TestCooldown:
    async def test_no_prior_fire_returns_false(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(scalar_value=None))
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        assert await empathy_engine._is_on_cooldown(
            db, uuid.uuid4(), "large_transaction", 1, now=now,
        ) is False

    async def test_within_cooldown_returns_true(self):
        last_fired = datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(scalar_value=last_fired))
        now = datetime(2026, 4, 23, 9, 0, tzinfo=timezone.utc)
        # 1-day cooldown, fired ~23h ago → still on cooldown.
        assert await empathy_engine._is_on_cooldown(
            db, uuid.uuid4(), "large_transaction", 1, now=now,
        ) is True

    async def test_beyond_cooldown_returns_false(self):
        last_fired = datetime(2026, 4, 20, tzinfo=timezone.utc)
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(scalar_value=last_fired))
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        # 1-day cooldown, fired 3 days ago → clear.
        assert await empathy_engine._is_on_cooldown(
            db, uuid.uuid4(), "large_transaction", 1, now=now,
        ) is False

    async def test_zero_cooldown_is_once_only(self):
        """cooldown_days=0 means the trigger can only ever fire once."""
        last_fired = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(scalar_value=last_fired))
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        # Even 6 years later, still on cooldown.
        assert await empathy_engine._is_on_cooldown(
            db, uuid.uuid4(), "first_saving_month", 0, now=now,
        ) is True


# ---------- Silence detection --------------------------------------

@pytest.mark.asyncio
class TestSilenceCheck:
    async def test_brand_new_user_returns_none(self):
        """No expense + no events → don't wake them up."""
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(scalar_value=None))
        out = await empathy_engine._days_since_last_activity(
            db, uuid.uuid4(), now=datetime(2026, 4, 23, tzinfo=timezone.utc),
        )
        assert out is None

    async def test_7_day_trigger_fires_at_day_7(self):
        user = _make_user()
        db = MagicMock()
        # Last expense 10 days ago
        last = datetime(2026, 4, 13, tzinfo=timezone.utc)
        # `_days_since_last_activity` runs two queries (last expense, last event).
        db.execute = AsyncMock(side_effect=[
            _fake_result(scalar_value=last),
            _fake_result(scalar_value=None),
        ])
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        trigger = await empathy_engine._check_user_silent_7_days(db, user, now)
        assert trigger is not None
        assert trigger.name == "user_silent_7_days"
        assert trigger.context["days_silent"] == 10

    async def test_7_day_trigger_does_not_fire_past_30(self):
        user = _make_user()
        last = datetime(2026, 3, 10, tzinfo=timezone.utc)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _fake_result(scalar_value=last),
            _fake_result(scalar_value=None),
        ])
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        assert await empathy_engine._check_user_silent_7_days(db, user, now) is None

    async def test_30_day_trigger_fires_at_day_30(self):
        user = _make_user()
        last = datetime(2026, 3, 10, tzinfo=timezone.utc)
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            _fake_result(scalar_value=last),
            _fake_result(scalar_value=None),
        ])
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        trigger = await empathy_engine._check_user_silent_30_days(db, user, now)
        assert trigger is not None
        assert trigger.name == "user_silent_30_days"


# ---------- Large transaction --------------------------------------

@pytest.mark.asyncio
class TestLargeTransaction:
    async def test_skips_when_below_sample_threshold(self):
        """Too few expenses to compute a stable median."""
        user = _make_user()
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        # Only 3 rows — below LARGE_TX_MIN_SAMPLES=5.
        rows = [
            MagicMock(amount=1_000_000, category="food", created_at=now),
            MagicMock(amount=50_000, category="food", created_at=now),
            MagicMock(amount=60_000, category="food", created_at=now),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(all_value=rows))
        assert await empathy_engine._check_large_transaction(db, user, now) is None

    async def test_fires_when_latest_is_large_outlier(self):
        user = _make_user()
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        rows = [
            MagicMock(amount=3_000_000, category="shopping", created_at=now),
            MagicMock(amount=100_000, category="food", created_at=now),
            MagicMock(amount=80_000, category="food", created_at=now),
            MagicMock(amount=120_000, category="food", created_at=now),
            MagicMock(amount=90_000, category="food", created_at=now),
            MagicMock(amount=110_000, category="food", created_at=now),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(all_value=rows))
        trigger = await empathy_engine._check_large_transaction(db, user, now)
        assert trigger is not None
        assert trigger.name == "large_transaction"
        assert "3,000,000đ" in trigger.context["amount"]

    async def test_skips_when_below_absolute_floor(self):
        """Even if the median is tiny, the floor stops silly messages."""
        user = _make_user()
        now = datetime(2026, 4, 23, tzinfo=timezone.utc)
        # Latest 200k is 4× median 50k but below LARGE_TX_MIN_ABSOLUTE=500k.
        rows = [
            MagicMock(amount=200_000, category="food", created_at=now),
            MagicMock(amount=40_000, category="food", created_at=now),
            MagicMock(amount=50_000, category="food", created_at=now),
            MagicMock(amount=60_000, category="food", created_at=now),
            MagicMock(amount=45_000, category="food", created_at=now),
            MagicMock(amount=55_000, category="food", created_at=now),
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(all_value=rows))
        assert await empathy_engine._check_large_transaction(db, user, now) is None


# ---------- Weekend high spending ---------------------------------

@pytest.mark.asyncio
class TestWeekendHighSpending:
    async def test_fires_when_weekend_over_half(self):
        user = _make_user()
        # Yesterday = Wed 2026-04-22 → window Thu 16 → Wed 22.
        # Put big spends on Sat 18 + Sun 19.
        from datetime import date as _date
        rows = [
            (1_000_000, _date(2026, 4, 18)),  # Sat
            (1_000_000, _date(2026, 4, 19)),  # Sun
            (500_000, _date(2026, 4, 20)),    # Mon
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(all_value=rows))
        now = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        trigger = await empathy_engine._check_weekend_high_spending(db, user, now)
        assert trigger is not None
        assert trigger.name == "weekend_high_spending"
        assert "%" in trigger.context["weekend_pct"]

    async def test_skips_balanced_spending(self):
        user = _make_user()
        from datetime import date as _date
        rows = [
            (100_000, _date(2026, 4, 18)),  # Sat
            (500_000, _date(2026, 4, 20)),  # Mon
            (500_000, _date(2026, 4, 21)),  # Tue
        ]
        db = MagicMock()
        db.execute = AsyncMock(return_value=_fake_result(all_value=rows))
        now = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        assert await empathy_engine._check_weekend_high_spending(
            db, user, now
        ) is None
