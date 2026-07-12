"""Resolve a user's onboarding cohort — Phase 4.6 / E4 (#4.1).

The decision-query log tags each row with the onboarding cohort so the admin
dashboard can split the new first-life segment (22-35, Level 0→1) from the
legacy asset-management cohort. The onboarding decision moment already has the
session loaded, so it classifies inline; the shock + feasibility handlers only
carry a ``user_id``, so they use this one-lookup resolver.

Layer contract: read-only helper (single indexed PK lookup, no write, no env,
no transport). The pure ``cohort_for_goal`` classifier is the single source of
truth for the goal → cohort mapping.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.onboarding_session import OnboardingSession, cohort_for_goal


async def resolve_user_cohort(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    """Return the onboarding cohort tag for ``user_id`` ("reset" / "legacy") or
    ``None`` when there is no session, no goal, or an unknown goal.

    One indexed primary-key lookup of ``goal_choice`` — cheap enough for the
    decision hot path — then the pure classifier does the mapping.
    """
    goal_choice = await db.scalar(
        select(OnboardingSession.goal_choice).where(
            OnboardingSession.user_id == user_id
        )
    )
    return cohort_for_goal(goal_choice)


__all__ = ["resolve_user_cohort"]
