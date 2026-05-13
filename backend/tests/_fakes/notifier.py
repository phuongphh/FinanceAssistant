"""In-memory :class:`Notifier` fake for tests.

Captures each outbound call so tests can assert content and
ordering without mocking HTTP. Use as a drop-in for
``backend.ports.notifier.get_notifier``::

    with patch(
        "backend.ports.notifier.get_notifier",
        return_value=FakeNotifier(),
    ) as fake:
        await some_service.do_it(db, user)
        assert fake.return_value.messages == [...]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SentMessage:
    chat_id: int
    text: str
    parse_mode: str | None = None
    reply_markup: dict | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class SentPhoto:
    chat_id: int
    photo: bytes
    caption: str = ""
    reply_markup: dict | None = None
    extra: dict = field(default_factory=dict)


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[SentMessage] = []
        self.photos: list[SentPhoto] = []
        # Combined ordered log — useful for asserting interleaving.
        self.log: list[SentMessage | SentPhoto] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None:
        entry = SentMessage(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            extra=kwargs,
        )
        self.messages.append(entry)
        self.log.append(entry)
        return {"ok": True}

    async def send_photo(
        self,
        chat_id: int,
        photo: bytes,
        *,
        caption: str = "",
        reply_markup: dict | None = None,
        **kwargs: Any,
    ) -> dict | None:
        entry = SentPhoto(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            extra=kwargs,
        )
        self.photos.append(entry)
        self.log.append(entry)
        return {"ok": True}
