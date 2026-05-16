"""Onboarding v2 state machine service (Phase 4.1, Stories A.1 & A.2).

Replaces the legacy ``users.onboarding_step`` int with a richer
:class:`OnboardingSession` row so we can track goal pick, inferred
wealth segment, in-onboarding emoji feedback, first-Twin timing
(TTFT), and resume-nudge bookkeeping.

The legacy 5-step flow on ``users`` row is untouched — both can
coexist. New users routed through v2 set
``users.onboarding_step = COMPLETED`` once
``OnboardingSession.current_step = 'completed'`` to keep downstream
code that queries ``user.is_onboarded`` working.

Transaction discipline: every mutator flushes only; the worker /
router boundary commits.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.onboarding_session import (
    ALL_GOALS,
    OnboardingSession,
    STEP_COMPLETED,
    STEP_FIRST_ASSET,
    STEP_TRUST_PRIVACY,
    STEP_GOAL_QUESTION,
    STEP_TWIN_SHOWN,
)
from backend.services.onboarding.wealth_inference_service import infer_segment
from backend.wealth.amount_parser import parse_amount as _parse_amount_canonical

logger = logging.getLogger(__name__)


_CONTENT_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "onboarding" / "welcome_v2.yaml"
)


def load_copy() -> dict[str, Any]:
    """Load v2 onboarding copy.

    NOT lru-cached — content updates during a long-running scheduler
    should land without a process restart. The file is small (~2KB)
    so the read cost is trivial relative to a Telegram round-trip.
    """
    with open(_CONTENT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------- Amount parsing -------------------------------------------

# Onboarding free-text amount parsing delegates to the canonical
# wealth/amount_parser so "510tr215", "20tr5", "1tỷ2" and other
# decimal-fraction shortcuts behave consistently with the rest of the
# app. The local copy used to fail on "Xtr<digits>" inputs because the
# trailing digit and the unit letter share a word boundary, dropping
# the user into the "Bé Tiền chưa hiểu con số đó" reprompt.

# Minimum sane first-asset value (1 triệu). Anything smaller is more
# likely a typo than a wealth signal.
MIN_ASSET_VND = Decimal("1_000_000")
# Hard cap to detect typos like "1000000 ty" (1 quadrillion).
MAX_ASSET_VND = Decimal("100_000_000_000_000")

DEMO_ASSET_VND = Decimal("50_000_000")  # Demo Twin uses 50tr placeholder.
TRUST_CARD_FLAG_ENV = "TRUST_CARD_ENABLED"


def is_trust_card_enabled() -> bool:
    return os.environ.get(TRUST_CARD_FLAG_ENV, "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def parse_asset_amount(raw: str) -> Decimal | None:
    """Parse a Vietnamese free-text money input into VND Decimal.

    Accepts every shortcut the post-onboarding asset wizard accepts
    (``200tr``, ``1.5 tỷ``, ``500k``, ``1tỷ2``, ``510tr215``,
    ``200,000,000``, raw integers). Returns ``None`` for unparseable
    input; callers handle the invalid / too_small / too_large
    branches separately.
    """
    if not raw:
        return None
    value = _parse_amount_canonical(raw)
    if value is None:
        return None
    # Canonical parser returns positive amounts only. Onboarding wants
    # an integer VND value — quantize away any sub-đồng noise from
    # decimal-fraction shortcuts like "1.5 tỷ".
    return value.quantize(Decimal("1"))


# ---------- Session CRUD ----------------------------------------------


async def get_session(db: AsyncSession, user_id: uuid.UUID) -> OnboardingSession | None:
    return await db.get(OnboardingSession, user_id)


async def start_or_resume(db: AsyncSession, user_id: uuid.UUID) -> OnboardingSession:
    """Idempotent: returns the existing session if it exists, else
    creates one in ``goal_question``.

    Callers commit at the worker boundary.
    """
    existing = await get_session(db, user_id)
    if existing is not None:
        return existing
    session = OnboardingSession(
        user_id=user_id,
        current_step=STEP_GOAL_QUESTION,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return session


async def set_goal(
    db: AsyncSession, user_id: uuid.UUID, goal_code: str
) -> OnboardingSession | None:
    if goal_code not in ALL_GOALS:
        return None
    session = await get_session(db, user_id)
    if session is None:
        return None
    session.goal_choice = goal_code
    if is_trust_card_enabled() and session.trust_accepted_at is None:
        session.current_step = STEP_TRUST_PRIVACY
    else:
        session.current_step = STEP_FIRST_ASSET
    await db.flush()
    return session


async def mark_trust_shown(db: AsyncSession, user_id: uuid.UUID) -> OnboardingSession | None:
    session = await get_session(db, user_id)
    if session is None:
        return None
    if session.trust_shown_at is None:
        session.trust_shown_at = datetime.now(timezone.utc)
    await db.flush()
    return session


async def accept_trust(db: AsyncSession, user_id: uuid.UUID) -> OnboardingSession | None:
    session = await get_session(db, user_id)
    if session is None:
        return None
    if session.trust_accepted_at is None:
        session.trust_accepted_at = datetime.now(timezone.utc)
    session.current_step = STEP_FIRST_ASSET
    await db.flush()
    return session


async def mark_trust_question_raised(db: AsyncSession, user_id: uuid.UUID) -> OnboardingSession | None:
    session = await get_session(db, user_id)
    if session is None:
        return None
    if session.trust_question_raised_at is None:
        session.trust_question_raised_at = datetime.now(timezone.utc)
    await db.flush()
    return session


async def set_first_asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    value_vnd: Decimal,
    *,
    demo: bool = False,
) -> OnboardingSession | None:
    session = await get_session(db, user_id)
    if session is None:
        return None
    session.first_asset_value_vnd = value_vnd
    session.inferred_wealth_segment = infer_segment(value_vnd)
    session.demo_mode_used = demo
    session.current_step = STEP_TWIN_SHOWN
    await db.flush()
    return session


async def mark_twin_shown(
    db: AsyncSession, user_id: uuid.UUID
) -> OnboardingSession | None:
    session = await get_session(db, user_id)
    if session is None:
        return None
    session.first_twin_shown_at = datetime.now(timezone.utc)
    await db.flush()
    return session


async def record_feedback_signal(
    db: AsyncSession, user_id: uuid.UUID, signal: str
) -> OnboardingSession | None:
    session = await get_session(db, user_id)
    if session is None:
        return None
    session.onboarding_feedback_signal = signal
    await db.flush()
    return session


async def mark_completed(
    db: AsyncSession, user_id: uuid.UUID
) -> OnboardingSession | None:
    session = await get_session(db, user_id)
    if session is None:
        return None
    session.current_step = STEP_COMPLETED
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return session


async def mark_nudge_sent(db: AsyncSession, user_id: uuid.UUID) -> None:
    session = await get_session(db, user_id)
    if session is None:
        return
    session.nudge_sent_at = datetime.now(timezone.utc)
    await db.flush()


async def find_stuck_sessions(
    db: AsyncSession, *, stuck_minutes: int = 10
) -> list[OnboardingSession]:
    """Return sessions that need a resume nudge.

    Criteria (Story A.2):
      - current_step != completed
      - nudge_sent_at IS NULL  (cap: 1 nudge per user, ever)
      - updated_at older than ``stuck_minutes`` ago

    Worker scans this list every 5 min — partial index
    ``idx_onboarding_stuck`` keeps the scan O(stuck rows).
    """
    cutoff = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta

    cutoff = cutoff - timedelta(minutes=stuck_minutes)
    stmt = (
        select(OnboardingSession)
        .where(
            OnboardingSession.current_step != STEP_COMPLETED,
            OnboardingSession.nudge_sent_at.is_(None),
            OnboardingSession.updated_at < cutoff,
        )
        .limit(200)  # safety net
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
