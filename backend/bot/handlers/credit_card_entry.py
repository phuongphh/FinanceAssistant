from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full
from backend.schemas.credit_card import CreditCardCreate
from backend.services import wizard_service
from backend.services.credit_card_service import (
    create_credit_card,
    delete_credit_card,
    get_credit_card,
    list_credit_cards,
)
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import send_message

FLOW_CREDIT_CARD_ADD = "credit_card_add"

CB_CREDIT_ADD = "expense:credit:add"
CB_CREDIT_DELETE_PICKER = "expense:credit:del"
CB_CREDIT_DELETE_PICK_PREFIX = "expense:credit:del:pick:"
CB_CREDIT_DELETE_CONFIRM_PREFIX = "expense:credit:del:confirm:"


def _credit_card_footer_keyboard(card_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "➕ Thêm thẻ tín dụng", "callback_data": "expense:credit:add"},
                {"text": "✅ Xong", "callback_data": "menu:expenses"},
            ],
            [{"text": "↩️ Huỷ thẻ vừa nhập", "callback_data": f"expense:credit:undo:{card_id}"}],
        ]
    }


async def show_credit_cards_list(db: AsyncSession, chat_id: int, user) -> None:
    cards = await list_credit_cards(db, user.id)
    if not cards:
        text = "💳 *Thẻ tín dụng*\n\nBạn chưa có thẻ tín dụng nào."
    else:
        lines = ["💳 *Danh sách thẻ tín dụng*"]
        for idx, card in enumerate(cards, start=1):
            lines.append(
                f"\n{idx}. *{card.bank_name}*"
                f"\n- Hạn mức: {format_money_full(float(Decimal(str(card.credit_limit or 0))))}"
                f"\n- Tổng dư nợ hiện có: {format_money_full(float(Decimal(str(card.debt_balance or 0))))}"
                f"\n- Ngày thanh toán: {card.closing_date}"
            )
        text = "\n".join(lines)

    keyboard_rows = [
        [{"text": "➕ Thêm thẻ tín dụng", "callback_data": CB_CREDIT_ADD}],
    ]
    if cards:
        # Only surface delete when there's actually something to remove
        # — keeps the empty-state focused on the primary "Thêm" action.
        keyboard_rows.append(
            [{"text": "🗑️ Xóa thẻ tín dụng", "callback_data": CB_CREDIT_DELETE_PICKER}]
        )
    keyboard_rows.append([{"text": "Quay về", "callback_data": "menu:expenses"}])

    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup={"inline_keyboard": keyboard_rows},
    )


async def start_credit_card_create(db: AsyncSession, chat_id: int, user) -> None:
    await wizard_service.start_flow(
        db,
        user.id,
        FLOW_CREDIT_CARD_ADD,
        step="bank_name",
        draft={},
    )
    await send_message(
        chat_id=chat_id,
        text="🏦 <b>Ngân hàng phát hành?</b> (Ví dụ: MSB, BIDV, Vietinbank...)",
        parse_mode="HTML",
    )


async def handle_credit_card_text_input(db: AsyncSession, message: dict) -> bool:
    text = (message.get("text") or "").strip()
    if not text:
        return False
    chat_id = message["chat"]["id"]
    telegram_id = (message.get("from") or {}).get("id")
    user = await get_user_by_telegram_id(db, telegram_id)
    if user is None or not user.wizard_state:
        return False
    flow = wizard_service.get_flow(user.wizard_state)
    if flow != FLOW_CREDIT_CARD_ADD:
        return False
    step = wizard_service.get_step(user.wizard_state)
    draft = wizard_service.get_draft(user.wizard_state)

    if step == "bank_name":
        bank = text.strip()
        if not bank:
            await send_message(chat_id=chat_id, text="Bạn nhập tên ngân hàng giúp mình nhé.")
            return True
        await wizard_service.update_step(db, user.id, step="credit_limit", draft_patch={"bank_name": bank})
        await send_message(chat_id=chat_id, text="💰 <b>Hạn mức tín dụng?</b> (Ví dụ: 100tr, 250 triệu...)", parse_mode="HTML")
        return True

    if step == "credit_limit":
        from backend.wealth.amount_parser import parse_amount

        limit = parse_amount(text)
        if limit is None or limit <= 0:
            await send_message(chat_id=chat_id, text="Bạn nhập hạn mức hợp lệ nhé. Ví dụ: <code>100tr</code>", parse_mode="HTML")
            return True
        await wizard_service.update_step(db, user.id, step="debt_balance", draft_patch={"credit_limit": float(limit)})
        await send_message(chat_id=chat_id, text="💳 <b>Tổng số dư nợ hiện có?</b> (Ví dụ: 15tr, 40 triệu...)", parse_mode="HTML")
        return True

    if step == "debt_balance":
        from backend.wealth.amount_parser import parse_amount

        debt_balance = parse_amount(text)
        if debt_balance is None or debt_balance < 0:
            await send_message(chat_id=chat_id, text="Bạn nhập tổng dư nợ hợp lệ nhé. Ví dụ: <code>15tr</code>", parse_mode="HTML")
            return True
        await wizard_service.update_step(db, user.id, step="closing_date", draft_patch={"debt_balance": float(debt_balance)})
        await send_message(chat_id=chat_id, text="📅 <b>Ngày thanh toán hàng tháng?</b> (từ 1 đến 31)", parse_mode="HTML")
        return True

    if step == "closing_date":
        if not text.isdigit() or not (1 <= int(text) <= 31):
            await send_message(chat_id=chat_id, text="Bạn nhập ngày từ <code>1</code> đến <code>31</code> nhé.", parse_mode="HTML")
            return True
        bank_name = (draft.get("bank_name") or "").strip()
        try:
            card = await create_credit_card(
                db,
                user.id,
                CreditCardCreate(
                    bank_name=bank_name,
                    credit_limit=float(draft.get("credit_limit") or 0),
                    closing_date=int(text),
                    debt_balance=float(draft.get("debt_balance") or 0),
                ),
            )
        except ValueError:
            await send_message(chat_id=chat_id, text="Tên ngân hàng này đã tồn tại. Bạn thử tên khác nhé.")
            return True
        await wizard_service.clear(db, user.id)
        await send_message(
            chat_id=chat_id,
            text=(
                "✅ Đã thêm thẻ tín dụng thành công:\n"
                f"- Ngân hàng: <b>{card.bank_name}</b>\n"
                f"- Hạn mức: <b>{format_money_full(float(Decimal(str(card.credit_limit or 0))))}</b>\n"
                f"- Tổng dư nợ hiện có: <b>{format_money_full(float(Decimal(str(card.debt_balance or 0))))}</b>\n"
                f"- Ngày thanh toán: <b>{card.closing_date}</b>"
            ),
            parse_mode="HTML",
            reply_markup=_credit_card_footer_keyboard(str(card.id)),
        )
        return True

    return False


async def show_credit_card_delete_picker(
    db: AsyncSession, chat_id: int, user
) -> None:
    """List live cards as buttons so the user can pick which to remove.

    Falls back to a friendly message when nothing remains — the entry
    point is suppressed in the list view, but a stale callback (e.g.
    user tapped "Xóa" then deleted from another device) shouldn't
    crash.
    """
    cards = await list_credit_cards(db, user.id)
    if not cards:
        await send_message(
            chat_id=chat_id,
            text="Bạn chưa có thẻ tín dụng nào để xóa.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "◀️ Quay lại", "callback_data": "menu:expenses:credit_cards"}],
                ]
            },
        )
        return

    rows = [
        [{
            "text": f"💳 {card.bank_name}",
            "callback_data": f"{CB_CREDIT_DELETE_PICK_PREFIX}{card.id}",
        }]
        for card in cards
    ]
    rows.append([{"text": "◀️ Quay lại", "callback_data": "menu:expenses:credit_cards"}])
    await send_message(
        chat_id=chat_id,
        text="🗑️ <b>Chọn thẻ tín dụng muốn xóa:</b>",
        parse_mode="HTML",
        reply_markup={"inline_keyboard": rows},
    )


async def show_credit_card_delete_confirm(
    db: AsyncSession, chat_id: int, user, card_id: str
) -> None:
    """Two-tap guard before the irreversible (to the user) soft-delete."""
    from uuid import UUID

    try:
        parsed_id = UUID(card_id)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy thẻ này.")
        return
    card = await get_credit_card(db, user.id, parsed_id)
    if card is None:
        await send_message(
            chat_id=chat_id,
            text="Thẻ này không còn trong danh sách. Bạn quay lại chọn thẻ khác nhé.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "◀️ Quay lại", "callback_data": CB_CREDIT_DELETE_PICKER}],
                ]
            },
        )
        return

    await send_message(
        chat_id=chat_id,
        text=(
            f"🗑️ <b>Xác nhận xóa thẻ {card.bank_name}?</b>\n\n"
            "Thẻ sẽ được gỡ khỏi danh sách và không hiển thị khi ghi chi tiêu mới.\n"
            "Lịch sử chi tiêu đã ghi nhận trên thẻ này vẫn được giữ nguyên."
        ),
        parse_mode="HTML",
        reply_markup={
            "inline_keyboard": [
                [{
                    "text": "🗑️ Xóa thật",
                    "callback_data": f"{CB_CREDIT_DELETE_CONFIRM_PREFIX}{card.id}",
                }],
                [{
                    "text": "❌ Không, giữ lại",
                    "callback_data": CB_CREDIT_DELETE_PICKER,
                }],
            ]
        },
    )


async def confirm_credit_card_delete(
    db: AsyncSession, chat_id: int, user, card_id: str
) -> None:
    """Perform the soft-delete and bounce back to the (now-updated) list."""
    from uuid import UUID

    try:
        parsed_id = UUID(card_id)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy thẻ này.")
        return
    card = await delete_credit_card(db, user.id, parsed_id)
    if card is None:
        await send_message(
            chat_id=chat_id,
            text="Thẻ này đã được xóa trước đó rồi 🤔",
        )
    else:
        await send_message(
            chat_id=chat_id,
            text=f"✅ Đã xóa thẻ <b>{card.bank_name}</b> khỏi danh sách.",
            parse_mode="HTML",
        )
    # Refresh the list so the user sees the updated state immediately
    # — saves one extra tap and confirms the action visually.
    await show_credit_cards_list(db, chat_id, user)


async def undo_credit_card_create(db: AsyncSession, chat_id: int, user, card_id: str) -> None:
    from uuid import UUID

    try:
        parsed_id = UUID(card_id)
    except ValueError:
        await send_message(chat_id=chat_id, text="Không tìm thấy thẻ để huỷ.")
        return
    card = await delete_credit_card(db, user.id, parsed_id)
    if card is None:
        await send_message(chat_id=chat_id, text="Thẻ này đã được xử lý rồi 🤔")
        return
    await send_message(
        chat_id=chat_id,
        text=f"↩️ Đã huỷ <b>{card.bank_name}</b>. Danh sách thẻ tín dụng đã được cập nhật.",
        parse_mode="HTML",
    )
