"""Shared test doubles for the Phase 4.5 Decision-Engine handler tests."""

from __future__ import annotations


class FakeSession:
    """Minimal ``AsyncSession`` stand-in for the decision handlers.

    The handlers now drop an append-only ``DecisionQueryLog`` row through the
    flush-only ``decision_query_log_service`` (E5 #5.1), so a bare ``object()``
    no longer works as ``db``. This records what was added and treats ``flush``
    as a no-op — enough for the DB-free handler tests, and lets a test assert on
    ``session.added`` when it cares about the logging side effect.
    """

    def __init__(self, *, goal_choice: str | None = None) -> None:
        self.added: list = []
        self.flushes = 0
        # Phase 4.6 E4: the decision handlers resolve the onboarding cohort with
        # one ``db.scalar`` lookup of ``goal_choice``. Default ``None`` keeps the
        # pre-4.6 tests untagged; a test can pass a goal to exercise tagging.
        self.goal_choice = goal_choice

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    async def scalar(self, *args, **kwargs):
        return self.goal_choice
