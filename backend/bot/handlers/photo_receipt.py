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
import secrets
import time
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.formatters.money import format_money_short
from backend.bot.formatters.templates import format_receipt_confirmation
from backend.bot.handlers.transaction import _normalize_category
from backend.bot.keyboards.transaction_keyboard import receipt_confirm_keyboard
from backend.config.categories import get_all_categories
from backend.models.user import User
from backend.schemas.expense import VALID_CATEGORIES, ExpenseCreate
from backend.services import expense_service
from backend.services.expense_source_resolver import apply_default_source
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
EVENT_RECEIPT_EXPENSE_AUTOSAVED = "receipt_expense_autosaved"
_PENDING_RECEIPT_TTL_S = 180
_pending_receipt_confirms: dict[str, dict[str, Any]] = {}

# Receipt notes are echoed back to the user and persisted verbatim; bound
# the length so a noisy OCR dump can't blow up the message or the column.
_MAX_NOTE_LEN = 200

# Display-code namespace the inline category picker offers. A user pick must
# be one of these before we mutate the pending payload.
_VALID_DISPLAY_CATEGORY_CODES = frozenset(cat.code for cat in get_all_categories())


def _clean_note(value: Any) -> str | None:
    """Normalize an OCR-extracted note: collapse whitespace, bound length.

    Returns ``None`` for empty/non-string input so callers can fall back to
    an item-name preview.
    """
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if len(cleaned) > _MAX_NOTE_LEN:
        cleaned = cleaned[:_MAX_NOTE_LEN].rstrip() + "…"
    return cleaned


def _item_name_preview(items: list[Any]) -> str | None:
    """Short ", "-joined preview of item names, used when no OCR note exists."""
    names = [
        str(it.get("name") or "").strip()
        for it in items
        if isinstance(it, dict) and (it.get("name") or "").strip()
    ]
    if not names:
        return None
    preview = ", ".join(names[:3])
    if len(names) > 3:
        preview += f" +{len(names) - 3}"
    return preview


def _parse_iso_date(value: Any) -> date | None:
    """Parse OCR's ``YYYY-MM-DD`` date string. Returns ``None`` on bad input.

    Rejects future dates (clock skew or hallucination) by falling back to
    ``None`` so the caller defaults to today instead of recording a
    plausible-but-wrong receipt date.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    if parsed > date.today():
        return None
    return parsed


def _resolve_ocr_category(suggestion: Any) -> str:
    """Map OCR ``category_suggestion`` to a valid expense category code.

    Unknown / missing values fall through to ``needs_review`` so
    ``create_expense`` triggers its LLM categorizer fallback.
    """
    if isinstance(suggestion, str) and suggestion in VALID_CATEGORIES:
        return suggestion
    return "needs_review"


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
    """Render the OCR result as a Telegram-HTML reply.

    Used as a fallback when we *can't* auto-save the expense (e.g.
    missing/zero total amount) — the regular happy path uses
    `format_receipt_confirmation` + an inline action keyboard.
    """
    total = result.get("total_amount") or 0
    currency = (result.get("currency") or "VND").upper()
    merchant = result.get("merchant_name")
    raw_date = result.get("date")
    parsed_date = _parse_iso_date(raw_date)
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
    if parsed_date:
        lines.append(f"📅 {parsed_date.strftime('%d/%m/%Y')}")
    elif raw_date:
        # Couldn't parse — still surface the raw string rather than dropping it.
        lines.append(f"📅 {html.escape(str(raw_date))}")

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


def _render_receipt_confirmation(
    payload: dict[str, Any], token: str
) -> tuple[str, dict]:
    """Build the confirmation text + inline keyboard from a pending payload.

    Single source of truth for both the first render (after OCR) and the
    re-render after a category pick, so the message body and the keyboard's
    ticked category never drift apart.

    A stored ``needs_review`` category means we couldn't confidently
    auto-categorize: the body invites the user to pick and the keyboard
    leaves every category un-ticked instead of pre-selecting "Khác".
    """
    stored = str(payload.get("category") or "needs_review")
    uncertain = stored == "needs_review"
    display_code = _normalize_category(stored)

    note = payload.get("note")
    items = [
        (str(it.get("name") or ""), it.get("price"))
        for it in (payload.get("items") or [])
        if isinstance(it, dict)
    ]
    merchant = payload.get("merchant") or note or "Hoá đơn"
    receipt_date = _parse_iso_date(payload.get("expense_date"))

    body = format_receipt_confirmation(
        merchant=str(merchant),
        amount=float(payload["amount"]),
        category_code=display_code,
        receipt_date=receipt_date,
        items=items,
        confidence=str(payload.get("confidence") or "medium"),
        note=note,
        category_uncertain=uncertain,
    )

    if uncertain:
        cta = "Chọn danh mục bên dưới rồi tap ✅ Đồng ý để lưu nhé 👇"
    else:
        cta = "Đúng rồi thì tap ✅ Đồng ý. Muốn đổi danh mục thì chọn bên dưới."

    text = f"{body}\n\n{cta}"
    keyboard = receipt_confirm_keyboard(
        token, selected_code=None if uncertain else display_code
    )
    return text, keyboard


async def _autosave_and_confirm(
    *,
    db: AsyncSession,
    user: User,
    result: dict[str, Any],
    chat_id: int,
    ack_id: int | None,
    finish,
) -> None:
    """Auto-create an expense from the OCR result and edit-in the confirmation.

    Falls back to the read-only `_format_receipt` view (no DB write) when
    the receipt is missing a usable total — the user can re-snap or type
    the amount manually instead of us persisting a zero-amount expense.
    """
    raw_total = result.get("total_amount")
    try:
        amount = float(raw_total) if raw_total is not None else 0.0
    except (TypeError, ValueError):
        amount = 0.0
    currency = (result.get("currency") or "VND").upper()
    merchant = (result.get("merchant_name") or "").strip() or None
    parsed_date = _parse_iso_date(result.get("date")) or date.today()
    confidence = (result.get("confidence") or "medium").lower()
    items = result.get("items") or []
    schema_category = _resolve_ocr_category(result.get("category_suggestion"))

    if amount <= 0:
        # Can't auto-save without a total. Keep the legacy read-only view
        # and nudge the user to add the amount manually.
        await finish(
            _format_receipt(result)
            + "\n\n<i>Mình chưa thấy số tiền trên hoá đơn — bạn gõ tay giúp,"
            " ví dụ \"150k cà phê\" nhé.</i>"
        )
        return

    # Prefer the receipt's own memo ("Lời nhắn"/"Nội dung chuyển khoản")
    # so transfer details aren't dropped; fall back to an item preview.
    note = _clean_note(result.get("note")) or _item_name_preview(items)

    # Keep ``needs_review`` so ``create_expense`` runs its LLM categorizer on
    # the no-pick path; otherwise store the display code we actually show.
    if schema_category == "needs_review":
        category = "needs_review"
    else:
        category = _normalize_category(schema_category)

    token = secrets.token_urlsafe(8)
    _pending_receipt_confirms[token] = {
        "created_at": time.monotonic(),
        "user_id": str(user.id),
        "amount": amount,
        "currency": currency,
        "merchant": merchant,
        "category": category,
        "expense_date": parsed_date.isoformat(),
        "note": note,
        "confidence": confidence,
        "items": items[:20],
        "category_suggestion": result.get("category_suggestion"),
    }
    text, keyboard = _render_receipt_confirmation(
        _pending_receipt_confirms[token], token
    )

    edited = False
    if ack_id:
        try:
            await edit_message_text(
                chat_id=chat_id,
                message_id=ack_id,
                text=text,
                parse_mode=None,
                reply_markup=keyboard,
            )
            edited = True
        except Exception:
            logger.debug("edit ack with receipt confirmation failed", exc_info=True)
    if not edited:
        await send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=None,
            reply_markup=keyboard,
        )


async def confirm_pending_receipt(*, db: AsyncSession, user: User, token: str) -> bool:
    payload = _pending_receipt_confirms.pop(token, None)
    if not payload or payload.get("user_id") != str(user.id):
        return False
    if time.monotonic() - float(payload.get("created_at", 0)) > _PENDING_RECEIPT_TTL_S:
        return False
    expense_data = ExpenseCreate(
        amount=float(payload["amount"]),
        currency=str(payload["currency"]),
        merchant=payload.get("merchant"),
        category=str(payload["category"]),
        source="ocr",
        expense_date=date.fromisoformat(str(payload["expense_date"])),
        note=payload.get("note"),
        raw_data={
            "ocr": {
                "confidence": payload.get("confidence"),
                "category_suggestion": payload.get("category_suggestion"),
                "items": payload.get("items") or [],
            }
        },
    )
    expense_data = await apply_default_source(db, user.id, expense_data)
    await expense_service.create_expense(db, user.id, expense_data)
    return True


def set_pending_receipt_category(
    *, token: str, user: User, category: str
) -> tuple[str, dict] | None:
    """Record the user's category pick on a pending receipt; re-render it.

    Returns the refreshed ``(text, keyboard)`` so the caller can edit the
    confirmation message in place, or ``None`` when the pick is rejected —
    unknown token, not the owner, expired, or an invalid display code (a
    spoofed callback). Picking refreshes the TTL so the user isn't rushed.
    """
    payload = _pending_receipt_confirms.get(token)
    if not payload or payload.get("user_id") != str(user.id):
        return None
    if time.monotonic() - float(payload.get("created_at", 0)) > _PENDING_RECEIPT_TTL_S:
        return None
    if category not in _VALID_DISPLAY_CATEGORY_CODES:
        return None
    payload["category"] = category
    payload["created_at"] = time.monotonic()
    return _render_receipt_confirmation(payload, token)


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

        await _autosave_and_confirm(
            db=db,
            user=user,
            result=result,
            chat_id=chat_id,
            ack_id=ack_id,
            finish=_finish,
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
    "confirm_pending_receipt",
    "handle_photo_message",
    "set_pending_receipt_category",
]
