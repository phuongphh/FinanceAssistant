"""Rate limiter + cost tracker unit tests."""
from __future__ import annotations

from datetime import date

import pytest

from backend.agent.rate_limit import DailyCostTracker, RateLimiter


@pytest.mark.asyncio
class TestRateLimiter:
    async def test_under_limit_allowed(self):
        rl = RateLimiter(max_total_per_hour=3, max_tier3_per_hour=1)
        d = await rl.check_total("u1")
        assert d.allowed is True

    async def test_over_total_limit_blocks(self):
        rl = RateLimiter(max_total_per_hour=2)
        await rl.record("u1")
        await rl.record("u1")
        d = await rl.check_total("u1")
        assert d.allowed is False
        assert d.reason == "rate_limit_total"
        assert d.retry_after_seconds is not None

    async def test_tier3_separate_window(self):
        rl = RateLimiter(max_total_per_hour=100, max_tier3_per_hour=2)
        await rl.record("u1", tier="tier3")
        await rl.record("u1", tier="tier3")
        d = await rl.check_tier3("u1")
        assert d.allowed is False

    async def test_tier3_record_doesnt_block_total(self):
        rl = RateLimiter(max_total_per_hour=100, max_tier3_per_hour=1)
        # Burn the tier-3 cap.
        await rl.record("u1", tier="tier3")
        # Tier 3 is full but total still has room.
        assert (await rl.check_tier3("u1")).allowed is False
        assert (await rl.check_total("u1")).allowed is True

    async def test_per_user_isolation(self):
        rl = RateLimiter(max_total_per_hour=1)
        await rl.record("u1")
        # u2 unaffected by u1 hitting the cap.
        assert (await rl.check_total("u2")).allowed is True
        assert (await rl.check_total("u1")).allowed is False

    async def test_window_expiry_with_fake_clock(self):
        now = [0.0]
        rl = RateLimiter(
            max_total_per_hour=1,
            window_seconds=10,
            clock=lambda: now[0],
        )
        await rl.record("u1")
        # Within window — blocked.
        assert (await rl.check_total("u1")).allowed is False
        # Advance past window — slot frees up.
        now[0] = 11.0
        assert (await rl.check_total("u1")).allowed is True

    async def test_unlimited_user_bypasses(self):
        rl = RateLimiter(max_total_per_hour=1)
        rl.allow_unlimited("admin")
        # Admin can record indefinitely.
        for _ in range(5):
            await rl.record("admin")
        assert (await rl.check_total("admin")).allowed is True


@pytest.mark.asyncio
class TestDailyCostTracker:
    async def test_initially_can_spend(self):
        t = DailyCostTracker()
        assert await t.can_spend() is True

    async def test_blocks_after_hard_limit(self):
        t = DailyCostTracker(alert_threshold_usd=1.0, hard_limit_usd=2.0)
        await t.add(2.5)
        assert await t.can_spend() is False

    async def test_alert_logged_once(self, caplog):
        import logging
        t = DailyCostTracker(alert_threshold_usd=1.0, hard_limit_usd=10.0)
        with caplog.at_level(logging.WARNING):
            await t.add(1.5)
            await t.add(0.5)  # well past the alert threshold
        # Exactly one warning emitted (alerted-once).
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1

    async def test_rolls_on_new_day(self):
        days = [date(2026, 5, 5)]
        t = DailyCostTracker(
            alert_threshold_usd=1.0,
            hard_limit_usd=2.0,
            clock=lambda: days[0],
        )
        await t.add(2.5)
        assert await t.can_spend() is False
        # Move to next day — bucket resets.
        days[0] = date(2026, 5, 6)
        assert await t.can_spend() is True
        assert t.spent_today_usd == 0.0

    async def test_negative_or_zero_ignored(self):
        t = DailyCostTracker()
        new_total = await t.add(-1.0)
        assert new_total == 0.0
        new_total = await t.add(0.0)
        assert new_total == 0.0
