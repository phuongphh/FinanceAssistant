"""Which channel is the current message being handled for? (Phase 5.0 #2.4)

Several intent handlers send their own reply and then return an empty
string — ``action_quick_transaction`` builds a rich Telegram card with an
inline keyboard, sends it, and tells the dispatcher there is nothing left
to deliver. That works fine while Telegram is the only channel; the
moment a Zalo user triggers the same handler, the card goes to a
``telegram_id`` they may not even have and the Zalo side stays silent.

Threading a ``channel`` argument down through pipeline → dispatcher →
handler → formatter would touch every handler signature for the benefit
of the two that self-send. A :class:`~contextvars.ContextVar` carries it
instead: each inbound Zalo event already runs inside its own
``asyncio.create_task`` (see :mod:`backend.workers.zalo_worker`), and
context variables are copied per task, so concurrent Telegram and Zalo
work cannot observe each other's value.

The default is :data:`CHANNEL_TELEGRAM`, deliberately: every existing
call site — schedulers, the Telegram worker, admin scripts, the whole
test suite — keeps behaving exactly as it did before this module
existed. Only code that explicitly enters :func:`use_channel` sees
anything different.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar

CHANNEL_TELEGRAM = "telegram"
CHANNEL_ZALO = "zalo"

_channel: ContextVar[str] = ContextVar("bt_channel", default=CHANNEL_TELEGRAM)


def get_channel() -> str:
    """The channel the current task is answering on."""
    return _channel.get()


def is_zalo() -> bool:
    """True while handling an inbound Zalo message.

    Prefer this over comparing :func:`get_channel` yourself — it keeps
    the "is this the legacy path?" question in one place, so adding a
    third channel in 5.1 doesn't mean auditing every equality check.
    """
    return _channel.get() == CHANNEL_ZALO


@contextlib.contextmanager
def use_channel(channel: str) -> Iterator[None]:
    """Run a block as if the message arrived on ``channel``.

    Always resets on exit, including on exception, so a handler that
    raises cannot leak its channel into whatever the task does next.
    """
    token = _channel.set(channel)
    try:
        yield
    finally:
        _channel.reset(token)
