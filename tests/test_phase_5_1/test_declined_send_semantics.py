"""A notifier that declines without raising must not count as delivered.

The ``Notifier`` port returns ``None`` when a send never reached the
transport, and it does so *without* raising — see
:class:`~backend.adapters.zalo_notifier.ZaloNotifier.send_message`. On
Telegram that is rare; on Zalo it is the normal state, because the
48h reactive window closes and the 8-message quota runs out. Since #4.2
a Zalo-only user has no Telegram target to fall back to, so "the send
raised" and "the send happened" are no longer the only two outcomes.

Two callers treated them as if they were, and both stamp a
write-once flag on the strength of it:

* the resume nudge sets ``nudge_sent_at``, which is a hard cap and not
  a backoff — a false positive means the user is never nudged again;
* feedback triage stamps ``first_responded_at`` + status ACTIONED,
  closing the SLA on a reply nobody received.

:mod:`backend.cashflow.alert` already gets this right; these tests pin
the other two to the same behaviour.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


class _DecliningNotifier:
    """Accepts the call, delivers nothing — the Zalo window-shut path."""

    def __init__(self, channel: str = "zalo") -> None:
        self.channel = channel
        self.calls: list[dict] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append({"chat_id": chat_id, "text": text, **kwargs})
        return None


class _AcceptingNotifier:
    def __init__(self, channel: str = "telegram") -> None:
        self.channel = channel
        self.calls: list[dict] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append({"chat_id": chat_id, "text": text, **kwargs})
        return {"ok": True, "channel": self.channel}


def _target(notifier, channel: str, target_id: str):
    from backend.services.notifier_resolver import ChannelTarget

    return ChannelTarget(channel=channel, notifier=notifier, target_id=target_id)


# ---------------------------------------------------------------------------
# Resume nudge
# ---------------------------------------------------------------------------


def _stuck_session():
    from backend.models.onboarding_session import STEP_FIRST_ASSET

    return SimpleNamespace(current_step=STEP_FIRST_ASSET)


@pytest.mark.asyncio
async def test_resume_nudge_declined_by_zalo_is_not_counted_as_sent(monkeypatch):
    from backend.jobs import onboarding_resume_job as job

    notifier = _DecliningNotifier()
    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=None, zalo_user_id="z1")
    monkeypatch.setattr(
        job, "resolve_targets", lambda _user: [_target(notifier, "zalo", "z1")]
    )

    sent = await job._send_nudge(_stuck_session(), user)

    # The attempt was made — we do not pre-check the window, the notifier
    # owns that decision — but it must not be reported as delivered.
    assert notifier.calls
    assert sent is False


@pytest.mark.asyncio
async def test_resume_nudge_one_accepting_channel_is_enough(monkeypatch):
    from backend.jobs import onboarding_resume_job as job

    declining = _DecliningNotifier()
    accepting = _AcceptingNotifier()
    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=42, zalo_user_id="z1")
    monkeypatch.setattr(
        job,
        "resolve_targets",
        lambda _user: [
            _target(accepting, "telegram", "42"),
            _target(declining, "zalo", "z1"),
        ],
    )

    assert await job._send_nudge(_stuck_session(), user) is True
    # A declined second channel must not undo the first one's success.
    assert accepting.calls and declining.calls


# ---------------------------------------------------------------------------
# Feedback triage reply
# ---------------------------------------------------------------------------


class _FakeDB:
    """Just enough session for ``reply``: ``get`` a user, ``flush``."""

    def __init__(self, user) -> None:
        self._user = user
        self.flushed = 0

    async def get(self, _model, _pk):
        return self._user

    async def flush(self):
        self.flushed += 1


@pytest.mark.asyncio
async def test_triage_reply_declined_leaves_sla_fields_untouched(monkeypatch):
    from backend.feedback.services import feedback_triage_service as svc

    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=None, zalo_user_id="z1")
    notifier = _DecliningNotifier()
    monkeypatch.setattr(
        svc, "resolve_targets", lambda _user: [_target(notifier, "zalo", "z1")]
    )
    feedback = SimpleNamespace(user_id=user.id, first_responded_at=None, status="new")
    db = _FakeDB(user)

    assert await svc.reply(db, feedback, "Cảm ơn bạn nhé") is False
    assert feedback.first_responded_at is None
    assert feedback.status == "new"
    assert db.flushed == 0


@pytest.mark.asyncio
async def test_triage_reply_stamps_sla_when_a_channel_accepts(monkeypatch):
    from backend.feedback.services import feedback_triage_service as svc

    user = SimpleNamespace(id=uuid.uuid4(), telegram_id=42, zalo_user_id=None)
    notifier = _AcceptingNotifier()
    monkeypatch.setattr(
        svc, "resolve_targets", lambda _user: [_target(notifier, "telegram", "42")]
    )
    feedback = SimpleNamespace(user_id=user.id, first_responded_at=None, status="new")
    db = _FakeDB(user)

    before = datetime.now(timezone.utc)
    assert await svc.reply(db, feedback, "Cảm ơn bạn nhé") is True
    assert feedback.first_responded_at >= before
    assert feedback.status == svc.FEEDBACK_STATUS_ACTIONED
    # Flush only — the transaction boundary belongs to the caller.
    assert db.flushed == 1
