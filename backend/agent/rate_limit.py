"""Per-user rate limits + global cost kill-switch.

The phase doc calls for Redis. Redis isn't yet a project dependency
(see CLAUDE.md §Stack — listed for Phase 1+) so we ship an in-memory
sliding-window limiter with a tight, swap-friendly interface. When
Redis lands, replace the store; the public surface stays.

Two collaborators:
- ``RateLimiter`` — per-user query-rate tracking (sliding window).
- ``DailyCostTracker`` — global cumulative cost-per-day with
  alert + hard-stop thresholds.

Both are thread-safe (``asyncio.Lock``) and time-aware via an
injectable clock so tests are deterministic.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable

from backend.agent.limits import (
    COST_ALERT_THRESHOLD_DAILY_USD,
    COST_HARD_LIMIT_DAILY_USD,
    MAX_TIER3_QUERIES_PER_HOUR,
    MAX_TOTAL_QUERIES_PER_HOUR,
)

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 3600  # one hour


@dataclass
class RateLimitDecision:
    """What the limiter said about one check.

    ``allowed=False`` always carries a reason so the caller can pick
    an appropriate user-facing message ("đợi 1 lát nhé" vs "tier 3
    chỉ dành cho gói Pro" — both are real product needs)."""

    allowed: bool
    reason: str | None = None
    retry_after_seconds: int | None = None


class RateLimiter:
    """In-memory sliding-window limiter scoped per user_id.

    Two windows tracked per user: total queries and tier-3-specific.
    Storing per-user means evicting old entries lazily inside the
    check; we never grow unbounded under steady-state load.
    """

    def __init__(
        self,
        *,
        max_total_per_hour: int = MAX_TOTAL_QUERIES_PER_HOUR,
        max_tier3_per_hour: int = MAX_TIER3_QUERIES_PER_HOUR,
        window_seconds: int = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        unlimited_users: Iterable[str] = (),
    ) -> None:
        self.max_total = max_total_per_hour
        self.max_tier3 = max_tier3_per_hour
        self.window = window_seconds
        self._clock = clock
        self._unlimited = set(unlimited_users)
        self._total: dict[str, deque[float]] = defaultdict(deque)
        self._tier3: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    def allow_unlimited(self, user_id: str) -> None:
        """Add an admin / debug user to the no-limit allowlist."""
        self._unlimited.add(str(user_id))

    async def check_total(self, user_id: str | int) -> RateLimitDecision:
        """Check the global per-hour cap for ``user_id``."""
        return await self._check(self._total, str(user_id), self.max_total, "total")

    async def check_tier3(self, user_id: str | int) -> RateLimitDecision:
        """Check the tier-3-specific cap. Should be called BEFORE
        ``check_total`` because tier-3 has a tighter limit; the caller
        typically does ``check_tier3 -> check_total`` and uses both
        decisions."""
        return await self._check(self._tier3, str(user_id), self.max_tier3, "tier3")

    async def record(self, user_id: str | int, *, tier: str = "tier1") -> None:
        """Record one query against the windows.

        ``tier`` of ``"tier3"`` (or higher) records against both
        windows so the tier-3 cap fills as expected."""
        uid = str(user_id)
        now = self._clock()
        async with self._lock:
            self._total[uid].append(now)
            if tier == "tier3":
                self._tier3[uid].append(now)

    # ------------------------------------------------------------------

    async def _check(
        self,
        store: dict[str, deque[float]],
        user_id: str,
        limit: int,
        label: str,
    ) -> RateLimitDecision:
        if user_id in self._unlimited:
            return RateLimitDecision(allowed=True)
        now = self._clock()
        cutoff = now - self.window
        async with self._lock:
            window = store[user_id]
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) < limit:
                return RateLimitDecision(allowed=True)
            # Earliest sample defines when the window slot frees up.
            # Limit may be 0 (deny-all) — empty window in that case.
            retry_after = (
                max(0, int(window[0] + self.window - now))
                if window
                else self.window
            )
            return RateLimitDecision(
                allowed=False,
                reason=f"rate_limit_{label}",
                retry_after_seconds=retry_after,
            )


class DailyCostTracker:
    """Accumulate per-day USD spend; alert + hard-stop at thresholds.

    State lives in memory keyed by the calendar day. When a new day
    starts the tracker rolls the counter automatically — perfect for
    a long-running Python process. Persistence (Redis / Postgres)
    can be bolted on by replacing ``_load`` / ``_save``.
    """

    def __init__(
        self,
        *,
        alert_threshold_usd: float = COST_ALERT_THRESHOLD_DAILY_USD,
        hard_limit_usd: float = COST_HARD_LIMIT_DAILY_USD,
        clock: Callable[[], date] = date.today,
    ) -> None:
        self.alert_threshold = alert_threshold_usd
        self.hard_limit = hard_limit_usd
        self._today_clock = clock
        self._day: date | None = None
        self._spent_today_usd: float = 0.0
        self._alerted = False
        self._lock = asyncio.Lock()

    async def can_spend(self) -> bool:
        """Return False if today's spend has hit the hard limit.

        Caller patterns: check before issuing an LLM call. We don't
        reserve budget — the check is best-effort, with a small
        race window between check and ``add``. Acceptable for a
        kill-switch (one extra call won't break the bank)."""
        async with self._lock:
            self._roll_if_new_day()
            return self._spent_today_usd < self.hard_limit

    async def add(self, usd: float) -> float:
        """Record ``usd`` against today's bucket. Returns new total.

        Emits a one-shot alert log when crossing the alert threshold."""
        if usd <= 0:
            return self._spent_today_usd
        async with self._lock:
            self._roll_if_new_day()
            previous = self._spent_today_usd
            self._spent_today_usd = previous + usd
            if (
                not self._alerted
                and self._spent_today_usd >= self.alert_threshold
            ):
                self._alerted = True
                logger.warning(
                    "Agent daily cost crossed alert threshold: "
                    "$%.4f >= $%.2f",
                    self._spent_today_usd,
                    self.alert_threshold,
                )
            return self._spent_today_usd

    @property
    def spent_today_usd(self) -> float:
        return self._spent_today_usd

    def _roll_if_new_day(self) -> None:
        today = self._today_clock()
        if self._day != today:
            self._day = today
            self._spent_today_usd = 0.0
            self._alerted = False


# Module-level singletons. Tests can construct their own; production
# code uses these so all callers share the same windows.
_RATE_LIMITER = RateLimiter()
_COST_TRACKER = DailyCostTracker()


def get_rate_limiter() -> RateLimiter:
    return _RATE_LIMITER


def get_cost_tracker() -> DailyCostTracker:
    return _COST_TRACKER
