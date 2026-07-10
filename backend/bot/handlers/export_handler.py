"""export_handler — /export command surface (Phase 4.5, Epic E4, Issue #4.1).

Thin handler: reads the ``EXPORT_EXCEL_ENABLED`` flag at the edge (layer
contract — services never read env), asks ``export_service`` for the
workbook bytes, then ships them through the :class:`Notifier` port's
``send_document``. No business logic lives here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import yaml
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.intent.handlers.decision_flags import is_export_excel_enabled
from backend.models.user import User
from backend.ports.notifier import get_notifier
from backend.services.export import export_service
from backend.services.onboarding import onboarding_service

logger = logging.getLogger(__name__)

_COPY_PATH = Path(__file__).resolve().parents[3] / "content" / "export_copy.yaml"
_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@lru_cache(maxsize=1)
def _copy() -> dict:
    with _COPY_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


async def cmd_export(
    db: AsyncSession, chat_id: int, user: User | None
) -> None:
    """Build the user's Excel workbook and send it as a Telegram document.

    Guards:
      * flag off → short "tạm tắt" note (never build).
      * no user → gentle /start nudge.
      * empty data → still send a header-only workbook with an empathetic
        caption (DoD: user trống không crash).
    """
    copy = _copy()
    notifier = get_notifier()

    if not is_export_excel_enabled():
        await notifier.send_message(chat_id, copy.get("disabled", ""), parse_mode=None)
        return

    if user is None:
        await notifier.send_message(
            chat_id, copy.get("not_registered", ""), parse_mode=None
        )
        return

    salutation = onboarding_service.salutation_of(user)
    building = copy.get("building", "").format(salutation=salutation)
    if building:
        await notifier.send_message(chat_id, building, parse_mode=None)

    xlsx_bytes, is_empty = await export_service.build_export(db, user.id)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = copy.get("filename", "export-{date}.xlsx").format(date=today)
    caption_key = "caption_empty" if is_empty else "caption"
    caption = copy.get(caption_key, "").format(salutation=salutation)

    await notifier.send_document(
        chat_id,
        xlsx_bytes,
        filename,
        caption=caption,
        mime_type=_XLSX_MIME,
    )
    logger.info(
        "export sent: user_id=%s bytes=%d empty=%s",
        user.id,
        len(xlsx_bytes),
        is_empty,
    )
