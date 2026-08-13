"""Zalo channel display limits (Phase 5.0).

The 300-character ceiling started life inside
:mod:`backend.adapters.zalo_notifier`, where it is enforced. But
enforcement is blind truncation, and a formatter that wants to *fit*
the bubble — rather than be cut to it — needs the same number while
composing.

It lives here instead of in the adapter because
:mod:`backend.bot.formatters.zalo_transaction` is imported at module
scope by the Telegram transaction handler, which deliberately defers
its Zalo adapter import (the adapter pulls in the OA client and its
settings on a path that runs at every startup, flag on or off).
Importing the adapter from the formatter just to read an integer would
undo that. This module imports nothing.
"""

from __future__ import annotations

# What Zalo actually shows before clipping the bubble on mobile.
# Enforced by ``backend.adapters.zalo_notifier.truncate_for_zalo``;
# budgeted against by the Zalo formatters so truncation never fires on
# copy we generated ourselves.
ZALO_MESSAGE_MAX_CHARS = 300

# Emoji the channel tolerates before the message reads as spam. One per
# message header is the house style; the second is the reserve.
ZALO_MAX_EMOJI = 2
