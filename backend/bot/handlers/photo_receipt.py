"""Photo → receipt OCR pipeline (Issue #603).

A user sends a photo of a receipt; we reply with the parsed amount,
merchant, and item list — or a friendly "not a receipt" nudge.

## Latency-first design

The two slow steps are (1) downloading the image from Telegram and
(2) the external OCR provider call. Combined they dominate the
end-to-end time; everything else is microseconds. The handler is
written so the *perceived* latency stays sub-second even when the real
work takes several seconds:

* **Immediate ack** — we send "📸 Đang đọc hoá đơn..." right away and
  edit that message in place when the result arrives. The user sees a
  reply within one webhook round-trip.
* **Refreshing chat action** — a background task keeps an
  ``upload_photo`` chat action alive on a 4 s cadence (Telegram clears
  it after 5 s) so the client UI stays in the "processing" state
  instead of going idle.
* **Smart photo-size pick** — Telegram delivers a photo as a list of
  thumbnails ascending in size. We pick the *largest size whose
  longest edge is ≤ 1600 px*. Bigger isn't better: OCR latency scales
  with bytes uploaded and pixels scanned, while accuracy plateaus for
  receipt text around 1280–1600 px. Defaulting to the biggest available
  costs 2–3× upload + OCR time for no accuracy gain.
* **Reuse the OCR client** — ``ocr_service._get_client`` is a singleton
  ``httpx.AsyncClient`` with HTTP/2 + keepalive, so consecutive
  receipts skip the TLS handshake.
* **Per-user LLM cache** — re-uploading the same receipt only pays the
  OCR provider cost the second time; the structuring LLM call is
  cached per ``user_id`` inside ``parse_receipt_image``.
"""

from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.models.user import User
from backend.services.ocr_service import parse_receipt_image
from backend.services.telegram_service import (
    download_file,
    edit_message_text,
    send_chat_action,
    send_message,
)

logger = logging.getLogger(__name__)

# Telegram cancels a chat action after ~5 s. Refresh slightly inside
# that window so the "uploading photo..." indicator never blinks off.
_CHAT_ACTION_REFRESH_S = 4.0

# Image-size sweet spot for receipt OCR. Larger inputs cost more upload
# bandwidth + provider compute without improving extraction accuracy.
_TARGET_MAX_EDGE_PX = 1600

# Telegram caps photo uploads at 10 MB; document-as-image can be larger.
# Bail before we send a giant payload upstream.
_MAX_IMAGE_BYTES = 10 * 1024 * 1024

EVENT_RECEIPT_PHOTO_RECEIVED = "receipt_photo_received"
EVENT_RECEIPT_PHOTO_PARSED = "receipt_photo_parsed"
EVENT_RECEIPT_PHOTO_FAILED = "receipt_photo_failed"


def _select_photo(photos: list[dict]) -> dict | None:
    """Pick the photo size with the best speed/accuracy tradeoff.

    Telegram returns ``photo`` as a list of thumbnails ascending in
    size. The smallest is ~90 px (illegible for OCR); the largest can
    be 1600+ px (slow). We return the largest size whose longest edge
    is ≤ ``_TARGET_MAX_EDGE_PX``; if every size is already smaller, we
    fall back to the biggest one so we still attempt OCR.
    """
    if not photos:
        return None

    def long_edge(p: dict) -> int:
        return max(int(p.get("width") or 0), int(p.get("height") or 0))

    in_budget = [p for p in photos if long_edge(p) <= _TARGET_MAX_EDGE_PX]
    if in_budget:
        return max(in_budget, key=long_edge)
    return min(photos, key=long_edge)


def _extract_message_id(send_result: dict | None) -> int | None:
    if not isinstance(send_result, dict):
        return None
    payload = send_result.get("result") if "result" in send_result else send_result
    if not isinstance(payload, dict):
        return None
    msg_id = payload.get("message_id")
    return int(msg_id) if isinstance(msg_id, int) else None


async def _keep_chat_action_alive(chat_id: int) -> None:
    """Background task that re-sends ``upload_photo`` every few seconds.

    Cancelled by the caller as soon as the real reply is ready. Errors
    are swallowed because losing the typing indicator is harmless.
    """
    try:
        while True:
            try:
                await send_chat_action(chat_id, "upload_photo")
            except Exception:
                logger.debug("send_chat_action failed", exc_info=True)
            await asyncio.sleep(_CHAT_ACTION_REFRESH_S)
    except asyncio.CancelledError:
        pass


def _format_receipt(result: dict[str, Any]) -> str:
    """Render the OCR result as a Telegram-HTML reply."""
    total = result.get("total_amount") or 0
    currency = (result.get("currency") or "VND").upper()
    merchant = result.get("merchant_name")
    date = result.get("date")
    items = result.get("items") or []
    confidence = (result.get("confidence") or "medium").lower()

    if currency == "VND":
        total_str = format_money_short(float(total))
    else:
        total_str = f"{total:,.2f} {currency}"

    lines = ["🧾 <b>Hoá đơn của bạn</b>", ""]
    if merchant:
        lines.append(f"🏪 <b>{html.escape(str(merchant))}</b>")
    lines.append(f"💸 Tổng: <b>{total_str}</b>")
    if date:
        lines.append(f"📅 {html.escape(str(date))}")

    if items:
        lines.append("")
        lines.append("<i>Chi tiết:</i>")
        for item in items[:10]:
            name = html.escape(str(item.get("name") or "")).strip()
            price = item.get("price")
            if not name:
                continue
            if price:
                if currency == "VND":
                    price_str = format_money_short(float(price))
                else:
                    price_str = f"{price:,.2f}"
                lines.append(f"• {name} — {price_str}")
            else:
                lines.append(f"• {name}")
        if len(items) > 10:
            lines.append(f"<i>… và {len(items) - 10} món khác</i>")

    if confidence == "low":
        lines.append("")
        lines.append(
            "<i>⚠️ Mình đọc chưa chắc lắm — bạn xem lại số tiền giúp nhé.</i>"
        )

    return "\n".join(lines)


async def handle_photo_message(
    db: AsyncSession,
    message: dict,
    user: User,
) -> bool:
    """Consume a photo (or image document) as a receipt.

    Returns ``True`` once a reply has been sent. Returns ``False`` only
    when the message carries no image at all so the caller can fall
    through to the next handler.
    """
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return False

    photos = message.get("photo") or []
    document = message.get("document") or {}
    doc_is_image = isinstance(document.get("mime_type"), str) and document[
        "mime_type"
    ].startswith("image/")

    if not photos and not doc_is_image:
        return False

    if photos:
        chosen = _select_photo(photos)
        if not chosen:
            return False
        file_id = chosen.get("file_id")
        mime_type = "image/jpeg"
        declared_size = int(chosen.get("file_size") or 0)
    else:
        file_id = document.get("file_id")
        mime_type = document.get("mime_type") or "image/jpeg"
        declared_size = int(document.get("file_size") or 0)

    if not file_id:
        return False

    if declared_size and declared_size > _MAX_IMAGE_BYTES:
        await send_message(
            chat_id,
            "📸 Ảnh hơi nặng quá 😅 Bạn thử chụp lại với chất lượng vừa nhé.",
        )
        analytics.track(
            EVENT_RECEIPT_PHOTO_FAILED,
            user_id=user.id,
            properties={"reason": "too_large", "bytes": declared_size},
        )
        return True

    analytics.track(
        EVENT_RECEIPT_PHOTO_RECEIVED,
        user_id=user.id,
        properties={
            "source": "document" if doc_is_image else "photo",
            "declared_size": declared_size,
        },
    )

    # Immediate ack — the user sees a reply within one webhook round-trip
    # regardless of how slow the OCR provider is today.
    ack = await send_message(chat_id, "📸 Đang đọc hoá đơn...")
    ack_id = _extract_message_id(ack)

    keepalive = asyncio.create_task(_keep_chat_action_alive(chat_id))

    async def _finish(text: str) -> None:
        """Edit the ack message in place, falling back to a new send."""
        edited = False
        if ack_id:
            try:
                await edit_message_text(
                    chat_id=chat_id,
                    message_id=ack_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=None,
                )
                edited = True
            except Exception:
                logger.debug("edit ack failed", exc_info=True)
        if not edited:
            await send_message(chat_id, text, parse_mode="HTML")

    try:
        image_bytes = await download_file(file_id)
        if not image_bytes:
            await _finish(
                "Mình không tải được ảnh 😔 Bạn gửi lại giúp mình nhé?"
            )
            analytics.track(
                EVENT_RECEIPT_PHOTO_FAILED,
                user_id=user.id,
                properties={"reason": "download_failed"},
            )
            return True

        if len(image_bytes) > _MAX_IMAGE_BYTES:
            await _finish(
                "📸 Ảnh hơi nặng quá 😅 Bạn thử chụp lại với chất lượng vừa nhé."
            )
            analytics.track(
                EVENT_RECEIPT_PHOTO_FAILED,
                user_id=user.id,
                properties={"reason": "too_large", "bytes": len(image_bytes)},
            )
            return True

        try:
            result = await parse_receipt_image(
                image_bytes,
                mime_type,
                db=db,
                user_id=user.id,
            )
        except ValueError as exc:
            logger.warning("OCR provider/parser failed: %s", exc)
            await _finish(
                "Mình đọc chưa được hoá đơn này 😔\n"
                "Bạn thử chụp lại rõ hơn, hoặc gõ tay giúp mình nhé."
            )
            analytics.track(
                EVENT_RECEIPT_PHOTO_FAILED,
                user_id=user.id,
                properties={"reason": "ocr_error"},
            )
            return True

        if result.get("error") == "not_a_receipt":
            await _finish(
                "Hmm, mình không thấy đây là hoá đơn 🤔\n"
                "Bạn gửi ảnh hoá đơn (có tên cửa hàng + tổng tiền) giúp mình nhé."
            )
            analytics.track(
                EVENT_RECEIPT_PHOTO_FAILED,
                user_id=user.id,
                properties={"reason": "not_a_receipt"},
            )
            return True

        await _finish(_format_receipt(result))
        analytics.track(
            EVENT_RECEIPT_PHOTO_PARSED,
            user_id=user.id,
            properties={
                "amount": float(result.get("total_amount") or 0),
                "confidence": result.get("confidence"),
                "category": result.get("category_suggestion"),
                "has_merchant": bool(result.get("merchant_name")),
                "item_count": len(result.get("items") or []),
            },
        )
        return True
    finally:
        keepalive.cancel()
        try:
            await keepalive
        except (asyncio.CancelledError, Exception):
            pass


__all__ = [
    "EVENT_RECEIPT_PHOTO_FAILED",
    "EVENT_RECEIPT_PHOTO_PARSED",
    "EVENT_RECEIPT_PHOTO_RECEIVED",
    "handle_photo_message",
]
