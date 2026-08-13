"""Telegram implementation of the :class:`Notifier` port.

Thin delegation to ``backend.services.telegram_service`` — the HTTP
client + error handling already live there, so there's no benefit
to re-implementing them. This wrapper exists to give services one
stable import surface (``Notifier``) that doesn't change when we
later add email / SMS / web push transports.
"""
from __future__ import annotations

from typing import Any

from backend.services import telegram_service

# Channel-neutral kwargs a caller may pass to any notifier, which
# ``telegram_service`` has no parameter for. They are dropped rather
# than forwarded: ``telegram_service`` takes explicit keyword arguments,
# so leaking one through is a ``TypeError`` on a live send path.
#
# ``buttons`` (Phase 5.1 #3.3) is the neutral
# ``tuple[tuple[Button, ...], ...]``; Telegram has already received the
# same buttons as ``reply_markup``, so there is nothing left to do with
# it here.
_NON_TELEGRAM_KWARGS = frozenset({"buttons", "image_url"})


def _telegram_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if k not in _NON_TELEGRAM_KWARGS}


class TelegramNotifier:
    """Default :class:`Notifier` implementation for Phase 0/1.

    ``parse_mode=None`` and ``reply_markup=None`` are left OUT of the
    downstream call entirely so the wrapped function's own defaults
    (Markdown parse mode, no reply markup) stay authoritative.
    """

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None:
        call_kwargs: dict[str, Any] = _telegram_kwargs(kwargs)
        if parse_mode is not None:
            call_kwargs["parse_mode"] = parse_mode
        if reply_markup is not None:
            call_kwargs["reply_markup"] = reply_markup
        return await telegram_service.send_message(chat_id, text, **call_kwargs)

    async def send_photo(
        self,
        chat_id: int,
        photo: bytes,
        *,
        caption: str = "",
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None:
        call_kwargs: dict[str, Any] = _telegram_kwargs(kwargs)
        if reply_markup is not None:
            call_kwargs["reply_markup"] = reply_markup
        return await telegram_service.send_photo(
            chat_id,
            photo,
            caption=caption,
            **call_kwargs,
        )

    async def send_document(
        self,
        chat_id: int,
        document: bytes,
        filename: str,
        *,
        caption: str = "",
        mime_type: str = "application/octet-stream",
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None:
        call_kwargs: dict[str, Any] = _telegram_kwargs(kwargs)
        if reply_markup is not None:
            call_kwargs["reply_markup"] = reply_markup
        return await telegram_service.send_document(
            chat_id,
            document,
            filename,
            caption=caption,
            mime_type=mime_type,
            **call_kwargs,
        )
