from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.formatters.money import format_money_full
from backend.schemas.credit_card import CreditCardCreate
from backend.services import wizard_service
from backend.services.credit_card_service import create_credit_card, list_credit_cards
from backend.services.dashboard_service import get_user_by_telegram_id
from backend.services.telegram_service import send_message

FLOW_CREDIT_CARD_ADD = "credit_card_add"


def _credit_card_footer_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "+ Thêm tài sản khác", "callback_data": "expense:credit:add"}],
            [{"text": "Xong", "callback_data": "menu:expenses"}],
            [{"text": "Huỷ tài sản vừa nhập", "callback_data": "expense:credit:undo_last"}],
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
                f"\n- Hạn mức: {format_money_full(float(Decimal(str(card.debt_balance or 0))))}"
                f"\n- Ngày thanh toán: {card.closing_date}"
            )
        text = "\n".join(lines)

    await send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup={
            "inline_keyboard": [
                [{"text": "+ Thêm thẻ tín dụng", "callback_data": "expense:credit:add"}],
                [{"text": "Quay về", "callback_data": "menu:expenses"}],
            ]
        },
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
        await wizard_service.update_step(db, user.id, step="closing_date", draft_patch={"credit_limit": float(limit)})
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
                    closing_date=int(text),
                    debt_balance=float(draft.get("credit_limit") or 0),
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
                f"- Hạn mức: <b>{format_money_full(float(Decimal(str(card.debt_balance or 0))))}</b>\n"
                f"- Ngày thanh toán: <b>{card.closing_date}</b>"
            ),
            parse_mode="HTML",
            reply_markup=_credit_card_footer_keyboard(),
        )
        return True

    return False
