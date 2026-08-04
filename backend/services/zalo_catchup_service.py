"""One line of "here's what happened while you were away" (Phase 5.1 #4.5).

Zalo is reactive-first: the OA may only speak inside 48 hours of the
user's last message, so every proactive surface — morning briefing,
price alert, empathy nudge — is skipped for a Zalo-only user rather than
queued. On Telegram that is fine, the other channel carries it. A user
who has *only* Zalo has no other channel, and the silence is total.

This module closes that gap the cheapest honest way: when such a user
comes back after a quiet stretch, reconstruct what changed **from data
that already exists** and say it once, in one short line.

Why no ``zalo_missed_notice`` table
-----------------------------------
The issue allows one, "chỉ thêm nếu không dựng lại được". It isn't
needed, and the reason is worth keeping:

* A literal replay was never possible anyway. ``morning_briefing_job``
  stores a ``MORNING_BRIEFING_SENT`` event, not the briefing text, and
  the #4.2 guards make the proactive jobs bail *before generating* for a
  Zalo-only user — so for these users no text is ever produced to be
  logged. A missed-notice table would have to be filled by re-running
  the generators, which is a different feature.
* What the user actually wants back is the *state change*, and that is
  durable: ``asset_snapshots`` holds yesterday's net worth and
  ``user_milestones`` holds every milestone with ``celebrated_at`` still
  NULL — ``check_milestones`` detects and commits those for Zalo-only
  users and only skips the *send*, so the queue is already there.
* Dedup falls out of the window instead of out of a stored flag. The
  lookback starts at the user's **previous inbound message**, so the
  moment they speak, everything already mentioned drops out of every
  future window. Stamping ``celebrated_at`` here would be worse: it
  marks a milestone as told before we know the send succeeded — the
  exact hazard ``check_milestones`` guards against.

Contract with the layer rules
-----------------------------
Flush-only — nothing here calls ``db.commit()``, and in fact nothing
here writes at all. Nothing reads env. No branching on channel: this
service is *about* the Zalo channel, it does not ask which channel it is
on. All copy comes from ``content/zalo.yaml`` section ``catchup``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_short
from backend.models.user import User
from backend.models.user_milestone import MilestoneType, UserMilestone
from backend.models.zalo_update import ZaloUpdate
from backend.utils.zalo_copy import load_copy, text as copy_text
from backend.utils.zalo_limits import ZALO_MESSAGE_MAX_CHARS
from backend.wealth.models.asset_snapshot import AssetSnapshot
from backend.wealth.services import asset_service

logger = logging.getLogger(__name__)

# How long a gap has to be before coming back counts as "returning".
# Under two days there is nothing to catch up on: the user was here
# yesterday and the same numbers were already on their screen.
SILENCE_DAYS = 2

# How far back the reconstruction reaches, per the issue's "N ngày gần
# nhất, đề xuất N=3". A 60-day absence still yields three days of news —
# a returning user wants to know where they stand now, not to read two
# months of history in one bubble.
LOOKBACK_DAYS = 3

# Below this, a net-worth move over three days is noise: market ticks and
# rounding, not something Bé Tiền should open a conversation with.
MIN_DELTA = Decimal("100000")

# Two is the most that fits alongside the money clause inside 300 chars.
MAX_MILESTONES = 2

# Level *downgrades* never appear in catch-up. They are real milestones
# and Telegram does celebrate the ups, but "welcome back, you dropped a
# tier" is exactly the harshness the persona forbids — and a user who
# has been away for days is the worst possible audience for it. Derived
# rather than hand-listed so a new DOWN_* code is excluded on arrival.
_SKIP_MILESTONE_TYPES = frozenset(
    code for code in MilestoneType.all() if code.startswith("wealth_level_down_")
)

_COPY_SECTION = "catchup"


def _aware(value: datetime | None) -> datetime | None:
    """Force a timestamp into UTC-aware form.

    ``zalo_updates.received_at`` and ``user_milestones.achieved_at`` are
    ``DateTime(timezone=True)`` columns with a Python-side default of
    ``datetime.utcnow`` — which is *naive*. Postgres hands them back
    aware, but any caller holding a freshly-defaulted object does not,
    and subtracting the two raises. Attaching UTC is correct for both,
    because the naive value was UTC to begin with.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _copy_args(salutation: str) -> dict[str, str]:
    """Both salutation keys, always supplied together.

    ``zalo_copy.text`` returns the *raw template* when a format key is
    missing, so a line using ``{Salutation}`` at the start would reach
    the user with a literal brace if only the lowercase key were passed.
    """
    value = (salutation or "").strip() or "bạn"
    return {"salutation": value, "Salutation": value.capitalize()}


def _milestone_titles() -> dict[str, str]:
    """The short noun-phrase title per milestone code.

    ``milestone_service.get_celebration_message`` only produces the long
    multi-line celebration; there is no short form anywhere in the
    codebase, so catch-up carries its own under ``catchup.milestones``.
    A code with no entry falls back to the generic line rather than
    blanking or crashing — adding a ``MilestoneType`` must never take the
    channel down.
    """
    section = load_copy().get(_COPY_SECTION) or {}
    titles = section.get("milestones")
    return titles if isinstance(titles, dict) else {}


async def _previous_inbound_at(
    db: AsyncSession, *, user_id: UUID, exclude_msg_id: str | None
) -> datetime | None:
    """When this user last spoke to the OA, before the message in hand.

    ``zalo_updates`` is the anchor rather than
    ``ZaloMessageWindow.last_inbound_at``: the worker calls
    ``record_inbound`` **and commits** before dispatching, so by the time
    a handler runs the window row already reads "now" and the previous
    value is gone. The update row survives either ordering — the worker
    stamps ``user_id`` on it only *after* handling, so normally it isn't
    matched at all yet, and ``exclude_msg_id`` covers the replay path
    where it already is.

    ``None`` means this is the first message we have from them, which is
    the right answer for a brand-new user: nothing was missed.
    """
    stmt = select(func.max(ZaloUpdate.received_at)).where(ZaloUpdate.user_id == user_id)
    if exclude_msg_id:
        stmt = stmt.where(ZaloUpdate.msg_id != exclude_msg_id)
    return _aware((await db.execute(stmt)).scalar_one_or_none())


async def _net_worth_delta(
    db: AsyncSession, *, user_id: UUID, since: datetime, until: datetime
) -> Decimal:
    """How much the user's net worth moved across the window.

    The baseline is the earliest snapshot **inside** the window for each
    asset; an asset with no snapshot in range defaults to its current
    value and therefore contributes nothing, which is the honest reading
    — we do not know that it moved. Assets are read through
    ``asset_service`` so the "what counts as net worth" filter stays in
    one place: its defaults already drop sold, placeholder and
    unconfirmed rows.
    """
    assets = await asset_service.get_user_assets(db, user_id)
    if not assets:
        return Decimal("0")

    rows = (
        await db.execute(
            select(AssetSnapshot.asset_id, AssetSnapshot.value)
            .where(
                AssetSnapshot.user_id == user_id,
                AssetSnapshot.snapshot_date >= since.date(),
                AssetSnapshot.snapshot_date <= until.date(),
            )
            .order_by(AssetSnapshot.snapshot_date.asc())
        )
    ).all()

    baseline: dict[UUID, Decimal] = {}
    for row in rows:
        baseline.setdefault(row.asset_id, Decimal(str(row.value)))

    delta = Decimal("0")
    for asset in assets:
        current = Decimal(str(asset.current_value or 0))
        delta += current - baseline.get(asset.id, current)
    return delta


async def _fresh_milestones(
    db: AsyncSession, *, user_id: UUID, since: datetime
) -> list[UserMilestone]:
    """Milestones hit during the silence that nobody has told them about.

    ``celebrated_at IS NULL`` is what makes this a queue rather than a
    re-read: ``check_milestones`` records the row for a Zalo-only user
    and skips only the send, so the flag stays NULL exactly when the news
    never reached anyone.
    """
    rows = (
        (
            await db.execute(
                select(UserMilestone)
                .where(
                    UserMilestone.user_id == user_id,
                    UserMilestone.celebrated_at.is_(None),
                )
                .order_by(UserMilestone.achieved_at.desc())
            )
        )
        .scalars()
        .all()
    )
    fresh = [
        row
        for row in rows
        if row.milestone_type not in _SKIP_MILESTONE_TYPES
        and (_aware(row.achieved_at) or since) >= since
    ]
    return list(reversed(fresh[:MAX_MILESTONES]))


def _compose(parts: list[str], *, fmt: dict[str, str]) -> str | None:
    """Join the clauses into one bubble, dropping the tail until it fits.

    Dropping whole clauses rather than clipping characters is deliberate:
    a truncated amount is worse than a missing one. If even the first
    clause overflows, there is no line — silence beats a half sentence.
    """
    joiner = copy_text(_COPY_SECTION, "joiner") or " · "
    for count in range(len(parts), 0, -1):
        line = copy_text(
            _COPY_SECTION, "lead", summary=joiner.join(parts[:count]), **fmt
        )
        if line and len(line) <= ZALO_MESSAGE_MAX_CHARS:
            return line
    return None


async def build_catchup_line(
    db: AsyncSession,
    *,
    user: User,
    exclude_msg_id: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """One short catch-up line for a returning Zalo-only user, or ``None``.

    ``None`` — the common case — means "say nothing extra", and every
    guard below is a reason to say nothing:

    * the user has Telegram, so the proactive channel already told them;
    * we have no earlier message from them, so nothing was missed;
    * the gap is shorter than :data:`SILENCE_DAYS`;
    * nothing moved and no milestone landed.

    ``exclude_msg_id`` is the message being handled right now — it must
    not count as the *previous* one.
    """
    if user.telegram_id is not None:
        return None

    now = _aware(now) or datetime.now(timezone.utc)
    previous = await _previous_inbound_at(
        db, user_id=user.id, exclude_msg_id=exclude_msg_id
    )
    if previous is None or now - previous < timedelta(days=SILENCE_DAYS):
        return None

    since = max(previous, now - timedelta(days=LOOKBACK_DAYS))
    fmt = _copy_args(getattr(user, "salutation", "") or "")

    parts: list[str] = []
    delta = await _net_worth_delta(db, user_id=user.id, since=since, until=now)
    if abs(delta) >= MIN_DELTA:
        key = "money_up" if delta > 0 else "money_down"
        money = copy_text(
            _COPY_SECTION, key, amount=format_money_short(abs(delta)), **fmt
        )
        if money:
            parts.append(money)

    titles = _milestone_titles()
    for row in await _fresh_milestones(db, user_id=user.id, since=since):
        title = titles.get(row.milestone_type)
        line = (
            copy_text(_COPY_SECTION, "milestone", title=title, **fmt)
            if title
            else copy_text(_COPY_SECTION, "milestone_generic", **fmt)
        )
        if line:
            parts.append(line)

    if not parts:
        return None

    line = _compose(parts, fmt=fmt)
    if line is None:
        logger.warning("zalo.catchup line did not fit — skipped")
    return line
