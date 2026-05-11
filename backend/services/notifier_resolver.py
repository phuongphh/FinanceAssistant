"""Multi-channel Notifier resolver.

Phase 4B Epic 4 (Story P4B-S24).

The original :func:`backend.ports.notifier.get_notifier` returns a
single process-wide notifier (Telegram). With Zalo we need a per-user
fan-out: the alert engine should reach every channel the user has
opted into.

Channel selection is keyed on the user row, not config — a user is
"Zalo-enabled" iff ``users.zalo_user_id`` is set, regardless of
whether the OA token is configured globally. This keeps the model
clean: linking is consent; the global token toggles delivery for the
whole platform.

This module sits in ``services/`` (not ``ports/``) because resolving
the list is product logic; the port stays a single-channel transport.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.adapters.zalo_notifier import ZaloNotifier
from backend.adapters.zalo_oa import get_zalo_oa_client
from backend.models.user import User
from backend.ports.notifier import Notifier, get_notifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelTarget:
    """A resolved (notifier, channel, target) tuple.

    ``target_id`` is the per-channel address (Telegram chat_id or
    Zalo user_id). The alert engine uses it for per-channel dedup
    keys so a multi-channel resend doesn't clobber the other channel's
    dedup window.
    """

    channel: str
    notifier: Notifier
    target_id: str


def resolve_targets(user: User) -> list[ChannelTarget]:
    """Return all opted-in channels for ``user``.

    Telegram is always included (telegram_id is required at signup).
    Zalo is appended when the user has linked their Zalo account AND
    the OA access token is configured on the server (so we don't
    enqueue sends that will immediately fail).
    """
    targets: list[ChannelTarget] = [
        ChannelTarget(
            channel="telegram",
            notifier=get_notifier(),
            target_id=str(user.telegram_id),
        )
    ]

    if user.zalo_user_id:
        zalo_client = get_zalo_oa_client()
        if zalo_client.is_configured:
            targets.append(
                ChannelTarget(
                    channel="zalo",
                    notifier=ZaloNotifier(
                        client=zalo_client, zalo_user_id=user.zalo_user_id
                    ),
                    target_id=user.zalo_user_id,
                )
            )
        else:
            logger.warning(
                "User %s has zalo_user_id but ZALO_OA_ACCESS_TOKEN not set — "
                "skipping Zalo channel",
                user.id,
            )

    return targets
