from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Phase 5.1 #4.2 — nullable since Zalo became a signup channel. A
    # user who arrived through the OA has no Telegram side at all, and
    # forcing a placeholder id here would be worse than NULL: it would
    # collide with the unique index the moment a second Zalo-only user
    # signed up, and every ``send_message(chat_id=...)`` would deliver
    # to a chat that doesn't exist.
    #
    # ``unique=True`` stays and needs no partial predicate: Postgres
    # treats NULLs as distinct in a unique index, so any number of
    # Zalo-only rows coexist while two real Telegram ids still can't.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, index=True
    )
    telegram_handle: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    # Phase 4.4 Epic 0 — how Bé Tiền addresses the user (anh/chị/bạn).
    # NULL until the onboarding salutation step; helpers fall back to "bạn".
    salutation: Mapped[str | None] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Ho_Chi_Minh")
    currency: Mapped[str] = mapped_column(String(10), default="VND")
    monthly_income: Mapped[float | None] = mapped_column(Numeric(15, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Phase 2 — Onboarding
    primary_goal: Mapped[str | None] = mapped_column(String(30))
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    onboarding_skipped: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    onboarding_skipped_asset: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Phase 3A — Wealth foundation
    primary_currency: Mapped[str] = mapped_column(
        String(3), default="VND", nullable=False
    )
    wealth_level: Mapped[str | None] = mapped_column(String(20))
    expense_threshold_micro: Mapped[int] = mapped_column(
        Integer, default=200_000, nullable=False
    )
    expense_threshold_major: Mapped[int] = mapped_column(
        Integer, default=2_000_000, nullable=False
    )
    briefing_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    briefing_time: Mapped[time] = mapped_column(
        Time, default=time(7, 0), nullable=False
    )
    # Multi-step wizard scratch space (asset entry etc).
    # Shape: {"flow": "asset_add_cash", "step": "amount", "draft": {...}}
    wizard_state: Mapped[dict | None] = mapped_column(JSONB)

    # Phase 4B Epic 3 — Cashflow Forecasting v2
    # User-customisable cashflow alert floor. NULL → system computes the
    # default (avg monthly expense from confirmed patterns × 1.0).
    cashflow_alert_threshold: Mapped[float | None] = mapped_column(Numeric(20, 2))

    # Phase 4B Epic 4 — Zalo channel link. NULL until the user pairs
    # their Zalo OA follow with a /link_zalo token; populated from the
    # Zalo webhook handler. Used by ``get_notifiers_for_user`` to fan
    # alerts out across channels.
    zalo_user_id: Mapped[str | None] = mapped_column(String(64))

    # Phase 4.1 — Founding member cohort + acquisition tracking.
    is_founding_member: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    founding_member_sequence: Mapped[int | None] = mapped_column(Integer)
    founding_member_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acquisition_source: Mapped[str | None] = mapped_column(String(64))

    # Phase 4.2.5 — Admin user management override. NULL means normal
    # system-derived status; ``suspended`` blocks bot interactions.
    manual_status: Mapped[str | None] = mapped_column(String(50), index=True)

    # Phase 4.3 — advanced users can opt into raw P10/P50/P90 labels.
    twin_show_technical_terms: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Phase 4.5 E4 #4.2 — tone dial. NULL → default gentle voice; the
    # /profile control sets "gentle" / "strict" once the user chooses.
    tone_preference: Mapped[str | None] = mapped_column(String(10))

    # Phase 4.5 E5 #5.2 — one-time re-engagement broadcast marker. NULL →
    # never messaged; stamped with the send time so the nudge fires once.
    reengagement_broadcast_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Phase 5.1 E4 #4.3 — the one-time "come to Telegram too" invitation a
    # Zalo-first user is shown at the end of onboarding. Two columns rather
    # than one because they answer different questions and only one of them
    # gates the send:
    #
    #   ``_at``       NULL → never invited. This alone is the "at most once"
    #                 gate, so an invitation the user ignored is still never
    #                 repeated — silence is an answer.
    #   ``_response`` what they chose ("declined"), or NULL while unanswered.
    #                 Recorded because the spec asks us to remember the
    #                 choice, and because "declined" and "ignored" mean
    #                 different things to anyone reading this row later.
    #
    # Accepting leaves no mark here: the accept path is a URL button that
    # opens Telegram, so the acceptance shows up as a Telegram id, not as a
    # message coming back to Zalo.
    zalo_telegram_invite_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    zalo_telegram_invite_response: Mapped[str | None] = mapped_column(String(20))

    @property
    def is_onboarded(self) -> bool:
        """True once the user has either finished or explicitly skipped."""
        return self.onboarding_completed_at is not None or self.onboarding_skipped

    def get_greeting_name(self) -> str:
        """Name to address the user by — falls back to 'bạn' (Vietnamese)."""
        name = (self.display_name or "").strip()
        return name if name else "bạn"
