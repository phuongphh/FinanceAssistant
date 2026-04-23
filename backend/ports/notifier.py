"""Notifier port — abstract interface for push notifications.

Services import ``get_notifier()``; tests patch the factory to swap
in a fake. This is deliberately the smallest viable DI pattern — no
container, no decorator magic, just one function behind a module
attribute — so it stays readable without adding framework surface
area.

Implementations live in ``backend/adapters/`` (one per transport).
The default is :class:`TelegramNotifier` which wraps
``backend.services.telegram_service``.
"""
from __future__ import annotations

from typing import Any, Protocol


class Notifier(Protocol):
    """Outbound notification transport.

    Methods return the adapter's raw result so callers can log /
    branch on delivery failures. Implementations MUST NOT raise on
    send errors — the caller owns retry policy.
    """

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None: ...

    async def send_photo(
        self,
        chat_id: int,
        photo: bytes,
        *,
        caption: str = "",
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None: ...


_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    """Return the process-wide Notifier, creating the default on first
    call. Tests override this by patching
    ``backend.ports.notifier.get_notifier`` — no set_notifier mutator
    needed (and no cross-test pollution from global mutable state).
    """
    global _notifier
    if _notifier is None:
        # Import is local to keep the port module free of adapter
        # imports — otherwise Python resolves backend.adapters.* at
        # every port import.
        from backend.adapters.telegram_notifier import TelegramNotifier
        _notifier = TelegramNotifier()
    return _notifier


def _reset_for_tests() -> None:
    """Drop the cached notifier. Only call from test teardown after a
    test has mutated module-level state directly (the normal patch
    path doesn't need this)."""
    global _notifier
    _notifier = None
