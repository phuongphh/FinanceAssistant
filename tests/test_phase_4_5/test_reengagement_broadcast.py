"""Phase 4.5 / E5 #5.2 — one-time re-engagement broadcast script.

The DB-touching bits (``collect_recipients`` query, ``on_sent`` stamping) live
behind small seams so the meat is testable without Postgres:

* ``select_dormant`` — the pure cohort filter (dormant + never-broadcast).
* ``broadcast`` — the send loop with an injected fake notifier and an
  ``on_sent`` recorder; proves incremental (crash-safe) stamping, that a
  failed send is not stamped, and that one bad chat never aborts the run.
* ``load_copy`` — the Vietnamese body comes from YAML and stays persona-clean.
* ``parse_args`` — ``--confirm`` / ``--dry-run`` gating.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts.send_reengagement_broadcast import (
    Recipient,
    broadcast,
    load_copy,
    parse_args,
    select_dormant,
)

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
_BANNED = ("Decision Engine", "CFO", "GPS tài chính")


def _row(
    *,
    last_active_days=None,
    created_days=30,
    manual_status=None,
    broadcast_at=None,
    telegram_id=None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        telegram_id=telegram_id if telegram_id is not None else 100000 + created_days,
        created_at=NOW - timedelta(days=created_days),
        manual_status=manual_status,
        reengagement_broadcast_at=broadcast_at,
        last_active_at=None if last_active_days is None else NOW - timedelta(days=last_active_days),
    )


# --------------------------------------------------------------------------
# Cohort filter
# --------------------------------------------------------------------------


def test_select_dormant_includes_only_never_broadcast_dormant():
    rows = [
        _row(last_active_days=None),  # never active → dormant ✓
        _row(last_active_days=10),  # >7d → dormant ✓
        _row(last_active_days=5),  # at_risk ✗
        _row(last_active_days=1),  # active ✗
        _row(created_days=1),  # new ✗
        _row(last_active_days=30, manual_status="suspended"),  # suspended ✗
        _row(last_active_days=20, broadcast_at=NOW - timedelta(days=1)),  # already sent ✗
    ]
    picked = select_dormant(rows, now=NOW)
    assert len(picked) == 2
    assert all(isinstance(r, Recipient) for r in picked)


def test_select_dormant_empty_when_none_eligible():
    rows = [_row(last_active_days=1), _row(created_days=1)]
    assert select_dormant(rows, now=NOW) == []


def test_already_broadcast_dormant_is_excluded_idempotency():
    # The core idempotency guarantee: a dormant user who already received the
    # nudge is never picked again, so a second run is a no-op for them.
    row = _row(last_active_days=30, broadcast_at=NOW - timedelta(days=2))
    assert select_dormant([row], now=NOW) == []


# --------------------------------------------------------------------------
# Send loop
# --------------------------------------------------------------------------


class _FakeNotifier:
    def __init__(self, fail_ids=()):
        self.sent: list[tuple[int, str]] = []
        self._fail_ids = set(fail_ids)

    async def send_message(self, chat_id, text, *, parse_mode=None, **kw):
        self.sent.append((chat_id, text))
        return None if chat_id in self._fail_ids else {"ok": True}


class _BoomNotifier:
    def __init__(self, boom_id):
        self.sent: list[int] = []
        self._boom_id = boom_id

    async def send_message(self, chat_id, text, *, parse_mode=None, **kw):
        self.sent.append(chat_id)
        if chat_id == self._boom_id:
            raise RuntimeError("blocked bot")
        return {"ok": True}


def _recipients(*telegram_ids):
    return [Recipient(user_id=uuid.uuid4(), telegram_id=t) for t in telegram_ids]


@pytest.mark.asyncio
async def test_broadcast_sends_and_stamps_each_success():
    recips = _recipients(111, 222, 333)
    notifier = _FakeNotifier()
    stamped: list = []

    async def on_sent(uid):
        stamped.append(uid)

    sent, failed = await broadcast(
        recips, "hi", notifier=notifier, on_sent=on_sent, throttle_ms=0
    )
    assert (sent, failed) == (3, 0)
    assert [c for c, _ in notifier.sent] == [111, 222, 333]
    # Incremental stamping: one on_sent per delivered message.
    assert stamped == [r.user_id for r in recips]


@pytest.mark.asyncio
async def test_broadcast_does_not_stamp_failed_send():
    recips = _recipients(111, 222)
    notifier = _FakeNotifier(fail_ids={222})
    stamped: list = []

    async def on_sent(uid):
        stamped.append(uid)

    sent, failed = await broadcast(
        recips, "hi", notifier=notifier, on_sent=on_sent, throttle_ms=0
    )
    assert (sent, failed) == (1, 1)
    # 222 failed → not stamped → a later re-run can retry it.
    assert stamped == [recips[0].user_id]


@pytest.mark.asyncio
async def test_broadcast_one_bad_chat_does_not_abort_run():
    recips = _recipients(111, 222, 333)
    notifier = _BoomNotifier(boom_id=222)
    stamped: list = []

    async def on_sent(uid):
        stamped.append(uid)

    sent, failed = await broadcast(
        recips, "hi", notifier=notifier, on_sent=on_sent, throttle_ms=0
    )
    # 222 raised, run continued to 333.
    assert notifier.sent == [111, 222, 333]
    assert (sent, failed) == (2, 1)
    assert len(stamped) == 2


# --------------------------------------------------------------------------
# Copy
# --------------------------------------------------------------------------


def test_load_copy_is_nonempty_and_persona_clean():
    body = load_copy()
    assert body
    assert "Bé Tiền" in body
    for banned in _BANNED:
        assert banned not in body


# --------------------------------------------------------------------------
# Arg gating
# --------------------------------------------------------------------------


def test_parse_args_defaults_are_safe():
    args = parse_args([])
    assert args.dry_run is False
    assert args.confirm is False
    assert args.only is None


def test_parse_args_flags():
    args = parse_args(["--dry-run"])
    assert args.dry_run is True
    args = parse_args(["--confirm", "--only", "555"])
    assert args.confirm is True and args.only == 555
