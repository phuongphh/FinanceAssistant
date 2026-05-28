"""Handler for ``ACTION_EDIT_ASSET`` — open the asset edit dashboard.

Two routes:

1. **Wizard launch** — plain "sửa cổ phiếu FPT", "sửa đất ba tư". The
   handler scopes the picker to the matching ``asset_type`` (and name
   substring when given) and opens the edit wizard. With one match it
   jumps straight into the value-prompt step.

2. **Inline edit** — "sửa cổ phiếu FPT thành 200 cổ", "sửa ACB thành
   50tr". The classifier captures ``asset_name`` and ``new_value``;
   when both are present and resolve to exactly one active asset, the
   handler applies the update inline (after a one-tap confirm card) so
   the user finishes the task without entering the wizard at all.

   For stocks/crypto, "200 cổ" / "10 BTC" updates ``extra.quantity``
   and recomputes ``current_value`` from the last recorded unit price
   (``avg_price`` / market price). For cash/gold/real-estate the
   captured amount is the new VND ``current_value`` directly.

Returns "" so the dispatcher skips the duplicate plain-text send.
"""

from __future__ import annotations

import html
import logging
import re
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.telegram_service import send_message
from backend.bot.formatters.money import format_money_short
from backend.bot.handlers import asset_entry as asset_entry_handlers
from backend.intent.extractors._normalize import strip_diacritics
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.wealth.amount_parser import parse_amount
from backend.wealth.services import asset_service

logger = logging.getLogger(__name__)


_QUANTITY_SUFFIX_RE = re.compile(
    r"(?P<num>[\d.,]+)\s*(?P<unit>co|co\s*phieu|share|shares|btc|eth|sol"
    r"|coin|tokens?|chi|cay|luong|oz|ounces?)\b",
    re.IGNORECASE,
)


def _name_matches(asset_name: str, query: str) -> bool:
    """Diacritic- and case-insensitive containment.

    The classifier hands us the diacritic-stripped, lowercased capture
    (e.g. "vang sjc"); DB asset names keep their diacritics ("Vàng
    SJC"). Strip both sides before comparing.
    """
    if not asset_name or not query:
        return False
    return strip_diacritics(query.lower()) in strip_diacritics(asset_name.lower())


def _parse_quantity(text: str) -> Decimal | None:
    """Extract a quantity from a "N cổ / N BTC / N chỉ" tail.

    Returns the numeric quantity when the trailing unit is one of the
    "count" markers (shares, coin, chỉ vàng, …). Returns ``None`` for
    plain monetary inputs so the caller falls back to ``parse_amount``.
    """
    if not text:
        return None
    text = strip_diacritics(text.lower())
    m = _QUANTITY_SUFFIX_RE.search(text)
    if not m:
        return None
    raw = m.group("num")
    if "," in raw and "." in raw:
        # Mixed separators: treat the rightmost as decimal, the other as thousands.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        # Single comma: ambiguous between thousands ("1,000") and decimal
        # ("1,5"). VN users overwhelmingly write quantities as integers
        # ("200 cổ", "1,000 cổ"), so treat groups of exactly 3 digits
        # after the comma as a thousands separator. A non-3-digit tail
        # ("1,5") is the decimal form.
        head, _, tail = raw.rpartition(",")
        if len(tail) == 3 and tail.isdigit() and head.replace(",", "").isdigit():
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
    elif "." in raw:
        # Single dot: same disambiguation. "1.000" → 1000, "1.5" → 1.5.
        head, _, tail = raw.rpartition(".")
        if len(tail) == 3 and tail.isdigit() and head.replace(".", "").isdigit():
            raw = raw.replace(".", "")
    try:
        return Decimal(raw)
    except Exception:
        return None


def _compute_value_from_quantity(
    asset, quantity: Decimal
) -> Decimal | None:
    """Recompute current_value = quantity × unit price.

    Reads ``extra.avg_price`` (stocks) or ``extra.last_price`` /
    ``extra.unit_price`` (crypto/gold). Returns ``None`` when no price
    is recorded — caller falls back to the wizard so the user can
    enter a price.
    """
    extra = asset.extra or {}
    for key in ("avg_price", "last_price", "unit_price", "price"):
        raw = extra.get(key)
        if raw in (None, "", 0):
            continue
        try:
            return (Decimal(str(raw)) * quantity).quantize(Decimal("1"))
        except Exception:
            continue
    # Fallback: derive from current_value / current_quantity if both stored.
    current_qty = extra.get("quantity")
    if current_qty and asset.current_value:
        try:
            unit = Decimal(str(asset.current_value)) / Decimal(str(current_qty))
            return (unit * quantity).quantize(Decimal("1"))
        except Exception:
            return None
    return None


class ActionEditAssetHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        params = intent.parameters or {}
        asset_type = params.get("asset_type")
        asset_name = (params.get("asset_name") or "").strip()
        new_value_raw = (params.get("new_value") or "").strip()
        chat_id = user.telegram_id

        # ---------- Inline edit path -----------------------------------
        if new_value_raw and asset_name:
            assets = await asset_service.get_user_assets(db, user.id)
            matches = [
                a
                for a in assets
                if a.is_active
                and _name_matches(a.name, asset_name)
                and (asset_type is None or str(a.asset_type) == asset_type)
            ]
            if len(matches) == 1:
                resolved = await self._apply_inline_edit(
                    db=db,
                    chat_id=chat_id,
                    user=user,
                    asset=matches[0],
                    new_value_raw=new_value_raw,
                )
                if resolved:
                    return ""
                # Couldn't parse new_value — fall through to wizard
                # picker so the user gets a guided flow.
            elif len(matches) > 1 and asset_type:
                await asset_entry_handlers.show_asset_edit_picker(
                    db,
                    chat_id,
                    user,
                    [str(a.id) for a in matches],
                )
                return ""
            # No match by name — fall through.

        # ---------- Wizard path (existing behaviour) -------------------
        if asset_type:
            assets = await asset_service.get_user_assets(db, user.id)
            type_matches = [
                a for a in assets if str(a.asset_type) == asset_type and a.is_active
            ]
            if asset_name:
                type_matches = [
                    a for a in type_matches if _name_matches(a.name, asset_name)
                ]
            if len(type_matches) == 1:
                await asset_entry_handlers.start_asset_edit_wizard(
                    db, chat_id, user, str(type_matches[0].id)
                )
                return ""
            if len(type_matches) > 1:
                await asset_entry_handlers.show_asset_edit_picker(
                    db, chat_id, user, [str(a.id) for a in type_matches]
                )
                return ""
            await send_message(
                chat_id=chat_id,
                text=(
                    "Mình không tìm thấy tài sản loại này 🌱 — "
                    "mình mở danh sách để bạn chọn dòng cần sửa nhé."
                ),
            )

        await asset_entry_handlers.show_asset_edit_picker_for_all_assets(
            db, chat_id, user
        )
        return ""

    async def _apply_inline_edit(
        self,
        *,
        db: AsyncSession,
        chat_id: int,
        user: User,
        asset,
        new_value_raw: str,
    ) -> bool:
        """Apply an inline value update. Returns True on success."""

        # 1. Try the "N cổ / N BTC / N chỉ" quantity form first — those
        # mean "set quantity to N and recompute value from stored unit
        # price". If we have no stored price we cannot finish without
        # the wizard, so we return False to fall back.
        quantity = _parse_quantity(new_value_raw)
        new_value: Decimal | None
        delta_quantity: Decimal | None = None
        if quantity is not None:
            new_value = _compute_value_from_quantity(asset, quantity)
            if new_value is None:
                await send_message(
                    chat_id=chat_id,
                    text=(
                        "Mình chưa có giá đơn vị đã ghi cho tài sản này — "
                        "bạn cập nhật qua wizard nhé."
                    ),
                )
                # Open the wizard so the user has a clear next step.
                await asset_entry_handlers.start_asset_edit_wizard(
                    db, chat_id, user, str(asset.id)
                )
                return True  # consumed — wizard now owns the flow
            delta_quantity = quantity
        else:
            # 2. Plain monetary value ("50tr", "1.2 tỷ").
            new_value = parse_amount(new_value_raw)

        if new_value is None or new_value < 0:
            return False

        # Apply update.
        try:
            updated = await asset_service.update_current_value(
                db, user.id, asset.id, Decimal(new_value)
            )
        except ValueError:
            return False

        # For quantity-style edits, persist the new quantity in extra
        # so subsequent reads (portfolio listing, briefings) reflect it.
        if delta_quantity is not None:
            extra = dict(updated.extra or {})
            extra["quantity"] = str(delta_quantity)
            await asset_service.update_asset_metadata(
                db, user.id, updated.id, extra=extra
            )

        safe_name = html.escape(asset.name or "Tài sản")
        qty_note = (
            f"\n• Số lượng: <b>{delta_quantity}</b>"
            if delta_quantity is not None
            else ""
        )
        await send_message(
            chat_id=chat_id,
            text=(
                f"✅ Đã cập nhật <b>{safe_name}</b>\n"
                f"• Giá trị mới: <b>{format_money_short(Decimal(new_value))}</b>"
                f"{qty_note}"
            ),
            parse_mode="HTML",
        )
        return True
