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
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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

# Common VN money shortcuts. Order matters: longer tokens first so
# "triệu" matches before "tr" inside the same string. Patterns deliberately
# don't use ``\b`` because "200tr" has no word boundary between the
# digit and the letter (both are word chars).
_AMOUNT_PATTERNS: list[tuple[re.Pattern[str], Decimal]] = [
    (re.compile(r"(?i)(?:tỷ|tỉ|ty)\b"), Decimal("1_000_000_000")),
    (re.compile(r"(?i)(?:triệu|trieu|tr|m)\b"), Decimal("1_000_000")),
    (re.compile(r"(?i)(?:nghìn|nghin|k)\b"), Decimal("1_000")),
]

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

    Accepts:
      • "200tr" → 200_000_000
      • "1.5 tỷ" → 1_500_000_000
      • "500k" → 500_000
      • "200,000,000" / "200.000.000" / "200000000" → 200_000_000

    Returns None for unparseable input. Callers handle the
    invalid / too_small / too_large branches separately.
    """
    if not raw:
        return None
    text = raw.strip().lower()

    multiplier = Decimal("1")
    for pattern, factor in _AMOUNT_PATTERNS:
        if pattern.search(text):
            multiplier = factor
            text = pattern.sub("", text)
            break

    # Strip thousand separators (both . and ,) and whitespace. We rely
    # on a single decimal separator at most for shortcut values like
    # "1.5 tỷ"; treat the LAST . or , as decimal if there's exactly
    # one of either, otherwise as thousand separator.
    cleaned = text.strip()
    if "," in cleaned and "." in cleaned:
        # Mixed — drop both (assume thousand separators only).
        cleaned = cleaned.replace(",", "").replace(".", "")
    elif cleaned.count(",") == 1 and multiplier != Decimal("1"):
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") == 1 and multiplier != Decimal("1"):
        pass  # already decimal-formatted
    else:
        cleaned = cleaned.replace(",", "").replace(".", "")

    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        return None

    try:
        return (Decimal(cleaned) * multiplier).quantize(Decimal("1"))
    except (InvalidOperation, ValueError):
        return None


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
