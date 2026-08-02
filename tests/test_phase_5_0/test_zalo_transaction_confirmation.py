"""Phase 5.0 #2.4 — the transaction confirmation picks its own channel.

``action_quick_transaction`` sends its reply itself and returns an empty
string, so before this issue the only exit path from these two senders was
``send_message(chat_id=user.telegram_id, ...)``. A Zalo user's transaction
was recorded and the channel stayed silent.

What the tests below pin, in order of how expensive the regression would be:

* a Zalo-only user gets exactly one bubble, and the bytes that reach the
  transport are plain text within Zalo's display limit — asserted against a
  *real* :class:`ZaloNotifier` so stripping and truncation are covered too;
* a Telegram user's card is byte-identical to what the formatter produces,
  keyboard and all — the contextvar defaults to Telegram, so every
  pre-existing caller must be untouched;
* unreachable-on-Zalo falls *through* to Telegram rather than dropping the
  confirmation, because "no ``zalo_user_id``" and "OA not configured on this
  box" are ordinary states, not failures.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.adapters import zalo_notifier as zalo_notifier_module
from backend.adapters import zalo_oa as zalo_oa_module
from backend.adapters import zalo_window_notifier as zalo_window_notifier_module
from backend.bot import channel_context
from backend.bot.formatters.templates import (
    format_transaction_batch_confirmation,
    format_transaction_confirmation,
)
from backend.bot.handlers import transaction
from backend.bot.keyboards.transaction_keyboard import transaction_actions_keyboard
from backend.models.zalo_message_window import FREE_MESSAGE_QUOTA
from backend.services import zalo_window_service

ZALO_USER_ID = "zalo-recipient-1"
SOURCE_LABEL = "Techcombank"


class _FakeZaloClient:
    """Stands in for the OA HTTP client.

    Records the *final* body — after ``strip_markdown`` and
    ``truncate_for_zalo`` — because that is what the user actually reads.
    """

    def __init__(self, *, configured: bool = True) -> None:
        self.is_configured = configured
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, zalo_user_id: str, body: str) -> bool:
        self.sent.append((zalo_user_id, body))
        return True


def _user(*, telegram_id: int | None = 555, zalo_user_id: str | None = ZALO_USER_ID):
    return SimpleNamespace(
        id=uuid4(), telegram_id=telegram_id, zalo_user_id=zalo_user_id
    )


def _expense(
    user,
    *,
    amount="45000.00",
    merchant="Phở Bát Đàn",
    category="food",
    transaction_type="expense",
    expense_date: date | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        merchant=merchant,
        note=None,
        amount=Decimal(amount),
        category=category,
        transaction_type=transaction_type,
        expense_date=expense_date or date.today(),
        created_at=datetime(2026, 8, 2, 12, 15),
    )


@pytest.fixture()
def env(monkeypatch, window_store):
    """Wire the sender's collaborators to spies.

    The Zalo notifier itself is left real — only the HTTP client below it
    is faked. A stubbed notifier would let a message through that the live
    one would have truncated or stripped.

    Since #3.2 that real notifier is :class:`WindowedZaloNotifier`, which
    claims a slot in its **own** committed transaction before every send.
    There is no Postgres here, so it is handed the in-memory window store
    from ``conftest``, with a window already open: these tests are about
    *what* the sender says and *where* it goes, not about the ceiling.
    The two that do exercise the ceiling shut the window themselves.
    """
    telegram_sent: list[dict] = []
    aha_calls: list = []
    client = _FakeZaloClient()

    @contextlib.asynccontextmanager
    async def _open_session():
        yield window_store

    monkeypatch.setattr(
        zalo_window_notifier_module,
        "get_session_factory",
        lambda: _open_session,
    )
    # Seeded through the real service rather than by hand so the row is
    # exactly the shape ``reserve_send`` expects. ``asyncio.run`` is safe
    # in a sync fixture: the store holds nothing bound to a loop.
    asyncio.run(
        zalo_window_service.record_inbound(window_store, zalo_user_id=ZALO_USER_ID)
    )

    async def _send_message(**kwargs):
        telegram_sent.append(kwargs)

    async def _source_label(db, expense):
        return SOURCE_LABEL

    async def _is_in_first_transaction_step(db, user_id):
        aha_calls.append(user_id)
        return False

    monkeypatch.setattr(transaction, "send_message", _send_message)
    monkeypatch.setattr(transaction, "resolve_source_label_for_expense", _source_label)
    # Only the transport is faked; ``ZaloNotifier`` stays real, so its
    # stripping and truncation run for every assertion below.
    monkeypatch.setattr(zalo_oa_module, "get_zalo_oa_client", lambda: client)

    from backend.services import onboarding_service

    monkeypatch.setattr(
        onboarding_service,
        "is_in_first_transaction_step",
        _is_in_first_transaction_step,
    )

    def _stub_user(user):
        async def _get_user_by_id(db, user_id):
            return user if user is not None and user_id == user.id else None

        monkeypatch.setattr(transaction, "get_user_by_id", _get_user_by_id)

    return SimpleNamespace(
        telegram=telegram_sent,
        zalo=client,
        aha=aha_calls,
        stub_user=_stub_user,
        client=client,
        window=window_store,
    )


# --------------------------------------------------------------------------
# Single transaction — Zalo
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zalo_only_user_gets_exactly_one_plain_text_bubble(env):
    """The regression this issue exists for: before #2.4 this user's
    transaction was recorded and nothing was ever sent."""
    user = _user(telegram_id=None)
    env.stub_user(user)
    expense = _expense(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, expense)

    assert len(env.zalo.sent) == 1
    recipient, body = env.zalo.sent[0]
    assert recipient == ZALO_USER_ID
    assert env.telegram == []

    assert len(body) <= zalo_notifier_module.ZALO_MESSAGE_MAX_CHARS
    # Zalo renders none of this — a stray marker shows up literally.
    assert not any(marker in body for marker in ("*", "_", "`", "<", ">"))
    assert "45,000đ" in body
    assert "Phở Bát Đàn" in body
    assert SOURCE_LABEL in body


@pytest.mark.asyncio
async def test_edit_hint_is_offered_only_to_users_who_have_telegram(env):
    """The hint says "mở Bé Tiền trên Telegram" — pointing a Zalo-only
    user at an account they don't have is a dead end."""
    zalo_only = _user(telegram_id=None)
    env.stub_user(zalo_only)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(zalo_only))

    assert "Telegram" not in env.zalo.sent[0][1]

    both = _user(telegram_id=777)
    env.stub_user(both)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(both))

    assert "Telegram" in env.zalo.sent[1][1]


@pytest.mark.asyncio
async def test_dual_linked_user_is_not_told_twice(env):
    """One transaction, one notification. Sending on both channels would
    read as two separate expenses."""
    user = _user(telegram_id=777)
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert len(env.zalo.sent) == 1
    assert env.telegram == []


@pytest.mark.asyncio
async def test_onboarding_aha_moment_stays_on_telegram(env):
    """The aha-moment is a Telegram-only onboarding beat. Reaching it from
    the Zalo branch would send a Telegram message the Zalo user never sees
    — and burn the one-time moment."""
    user = _user(telegram_id=777)
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert env.aha == []


@pytest.mark.asyncio
async def test_money_in_reads_as_received_not_spent(env):
    user = _user(telegram_id=None)
    env.stub_user(user)
    expense = _expense(user, transaction_type="money_in", category="salary")

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, expense)

    assert env.zalo.sent[0][1].startswith("✅ Đã nhận")


@pytest.mark.asyncio
async def test_backdated_transaction_shows_the_day_it_belongs_to(env):
    """A date row costs characters, so it appears only when the user
    pinned a day other than today — same rule as the Telegram card."""
    user = _user(telegram_id=None)
    env.stub_user(user)
    yesterday = date.today() - timedelta(days=1)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(
            None, _expense(user, expense_date=yesterday)
        )
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert yesterday.strftime("%d/%m/%Y") in env.zalo.sent[0][1]
    assert "Ngày giao dịch" not in env.zalo.sent[1][1]


# --------------------------------------------------------------------------
# Single transaction — Telegram must be untouched
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_card_is_byte_identical_to_the_formatter_output(env):
    """No channel entered → the contextvar default applies. Asserted
    against the formatter rather than a frozen string so the test tracks
    copy changes but still catches the sender feeding it different data
    (a normalised category, a dropped source label)."""
    user = _user()
    env.stub_user(user)
    expense = _expense(user)

    await transaction.send_transaction_confirmation(
        None, expense, daily_spent=215_000, daily_budget=400_000
    )

    assert env.zalo.sent == []
    assert len(env.telegram) == 1
    call = env.telegram[0]
    assert call["chat_id"] == user.telegram_id
    assert call["parse_mode"] == "HTML"
    assert call["reply_markup"] == transaction_actions_keyboard(str(expense.id))
    assert call["text"] == format_transaction_confirmation(
        merchant="Phở Bát Đàn",
        amount=float(expense.amount),
        category_code="food",
        time=expense.created_at,
        daily_spent=215_000,
        daily_budget=400_000,
        source_label=SOURCE_LABEL,
        show_edit_hint=True,
        transaction_type="expense",
        expense_date=expense.expense_date,
    )


@pytest.mark.asyncio
async def test_telegram_user_never_constructs_a_zalo_client(env, monkeypatch):
    """Cheap guarantee that the Telegram hot path did not gain a Zalo
    dependency: touching the OA client on that path is a hard failure."""

    def _boom():
        raise AssertionError("Telegram path must not reach the Zalo adapter")

    monkeypatch.setattr(zalo_oa_module, "get_zalo_oa_client", _boom)
    user = _user()
    env.stub_user(user)

    await transaction.send_transaction_confirmation(None, _expense(user))

    assert len(env.telegram) == 1


# --------------------------------------------------------------------------
# Fall-through when Zalo can't be reached
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlinked_zalo_account_still_gets_the_telegram_card(env):
    """A Telegram user whose message happened to arrive on the Zalo worker
    (orphan recovery replaying an old event, say) must not lose their
    confirmation."""
    user = _user(zalo_user_id=None)
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert env.zalo.sent == []
    assert len(env.telegram) == 1


@pytest.mark.asyncio
async def test_unconfigured_oa_falls_back_instead_of_raising(env, monkeypatch):
    """A dev box without Zalo env is a normal state, not an error."""
    monkeypatch.setattr(
        zalo_oa_module, "get_zalo_oa_client", lambda: _FakeZaloClient(configured=False)
    )
    user = _user()
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert len(env.telegram) == 1


def _exhaust_quota(row) -> None:
    row.free_msg_count = FREE_MESSAGE_QUOTA


def _expire_window(row) -> None:
    row.window_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)


@pytest.mark.parametrize(
    ("shut_window", "expected_reason"),
    [
        (_exhaust_quota, zalo_window_service.REASON_QUOTA_EXHAUSTED),
        (_expire_window, zalo_window_service.REASON_WINDOW_CLOSED),
    ],
)
@pytest.mark.asyncio
async def test_shut_window_falls_through_to_telegram(
    env, caplog, shut_window, expected_reason
):
    """The #3.1 DoD, asserted from the caller's side: *"Ngoài cửa sổ 48h
    hoặc đã dùng 8 tin → không gọi ``/message/cs``, Telegram vẫn nhận, log
    rõ lý do."*

    The ceiling itself is tested in ``test_zalo_window_notifier.py``; what
    is unique here is the consequence one layer up. ``_send_on_zalo``
    returning ``False`` has to mean *fall through*, not *return* — a
    refusal is the notifier declining to spend a slot, not the user
    losing their confirmation.
    """
    user = _user(telegram_id=777)
    env.stub_user(user)
    shut_window(env.window.rows[ZALO_USER_ID])

    with caplog.at_level(logging.INFO, logger="backend.adapters.zalo_window_notifier"):
        with channel_context.use_channel(channel_context.CHANNEL_ZALO):
            await transaction.send_transaction_confirmation(None, _expense(user))

    assert env.zalo.sent == []
    assert len(env.telegram) == 1
    assert env.telegram[0]["chat_id"] == 777

    blocked = [r for r in caplog.records if "zalo.send.blocked" in r.getMessage()]
    assert len(blocked) == 1
    message = blocked[0].getMessage()
    assert f"reason={expected_reason}" in message
    # The recipient id is a stable identifier for a real person; only the
    # masked form may reach a log line.
    assert ZALO_USER_ID not in message


@pytest.mark.asyncio
async def test_shut_window_leaves_a_zalo_only_user_silent_rather_than_double_sent(env):
    """No Telegram side means there is nowhere to fall through to. The
    transaction is still recorded — the caller's contract is "notify if you
    can", and burning a rejected ``/message/cs`` call would help nobody."""
    user = _user(telegram_id=None)
    env.stub_user(user)
    _exhaust_quota(env.window.rows[ZALO_USER_ID])

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert env.zalo.sent == []
    assert env.telegram == []


@pytest.mark.asyncio
async def test_batch_on_a_shut_window_falls_through_to_telegram(env):
    """The batch sender has its own copy of the fall-through, so it needs
    its own guard against that copy losing the ``if sent: return``."""
    user = _user(telegram_id=777)
    env.stub_user(user)
    _exhaust_quota(env.window.rows[ZALO_USER_ID])

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_batch_confirmation(
            None, _batch(user), batch_id="b-1"
        )

    assert env.zalo.sent == []
    assert len(env.telegram) == 1


@pytest.mark.asyncio
async def test_every_zalo_send_spends_exactly_one_slot(env):
    """Two confirmations, two slots — not one (the reservation is not
    cached) and not three (nothing re-reserves on the success path)."""
    user = _user(telegram_id=None)
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(user))
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert env.window.rows[ZALO_USER_ID].free_msg_count == 2


@pytest.mark.asyncio
async def test_user_reachable_on_neither_channel_is_a_silent_no_op(env):
    user = _user(telegram_id=None, zalo_user_id=None)
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(user))

    assert env.zalo.sent == []
    assert env.telegram == []


@pytest.mark.asyncio
async def test_deleted_user_sends_nothing(env):
    """``get_user_by_id`` returning ``None`` used to be folded into the
    same guard as "no telegram_id"; #2.4 split them, so pin both halves."""
    env.stub_user(None)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_confirmation(None, _expense(_user()))

    assert env.zalo.sent == []
    assert env.telegram == []


# --------------------------------------------------------------------------
# Batch
# --------------------------------------------------------------------------


def _batch(user, count: int = 3):
    return [
        _expense(user, merchant=f"Quán {index}", amount=f"{(index + 1) * 10000}.00")
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_batch_on_zalo_is_one_bubble_with_the_total(env):
    user = _user(telegram_id=None)
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_batch_confirmation(
            None, _batch(user), batch_id="b-1"
        )

    assert len(env.zalo.sent) == 1
    body = env.zalo.sent[0][1]
    assert env.telegram == []
    assert len(body) <= zalo_notifier_module.ZALO_MESSAGE_MAX_CHARS
    # 10,000 + 20,000 + 30,000
    assert "60,000đ" in body
    assert "Quán 0" in body


@pytest.mark.asyncio
async def test_batch_on_telegram_is_byte_identical_to_the_formatter_output(env):
    user = _user()
    env.stub_user(user)
    expenses = _batch(user)

    await transaction.send_transaction_batch_confirmation(
        None, expenses, batch_id="b-1"
    )

    assert env.zalo.sent == []
    call = env.telegram[0]
    assert call["parse_mode"] == "HTML"
    # All-expense batches carry no keyboard — the per-item edit flow is
    # single-transaction only.
    assert call["reply_markup"] is None
    assert call["text"] == format_transaction_batch_confirmation(
        items=[(e.merchant, float(e.amount), "food") for e in expenses],
        time=max(e.created_at for e in expenses),
        source_label=SOURCE_LABEL,
        show_edit_hint=True,
        expense_date=expenses[0].expense_date,
    )


@pytest.mark.asyncio
async def test_empty_batch_sends_nothing(env):
    user = _user()
    env.stub_user(user)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_batch_confirmation(None, [], batch_id="b-1")

    assert env.zalo.sent == []
    assert env.telegram == []


@pytest.mark.asyncio
async def test_mixed_day_batch_omits_the_date_row(env):
    """Items on different days can't be summarised by one date, and a
    wrong date on a receipt is worse than no date."""
    user = _user(telegram_id=None)
    env.stub_user(user)
    expenses = _batch(user, count=2)
    expenses[1].expense_date = date.today() - timedelta(days=3)

    with channel_context.use_channel(channel_context.CHANNEL_ZALO):
        await transaction.send_transaction_batch_confirmation(
            None, expenses, batch_id="b-1"
        )

    assert "Ngày giao dịch" not in env.zalo.sent[0][1]


@pytest.mark.asyncio
async def test_mixed_type_batch_keeps_its_telegram_keyboard(env):
    """A batch containing a money-in row is reviewable on Telegram, so the
    batch keyboard must survive — the Zalo branch must not have changed
    how ``all_expense`` is computed."""
    user = _user()
    env.stub_user(user)
    expenses = _batch(user, count=2)
    expenses[1].transaction_type = "money_in"

    await transaction.send_transaction_batch_confirmation(
        None, expenses, batch_id="b-77"
    )

    assert env.telegram[0]["reply_markup"] is not None
