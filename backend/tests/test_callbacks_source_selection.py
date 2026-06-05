"""Regression tests for the transaction-source callback flow (`txsrc:*`,
`txsrc_wallet:*`).

Issue #799 reported that after a user typed "+20 tỷ lương" → tapped
``e_wallet`` → tapped a wallet, the database write succeeded but no
confirmation message was ever sent back to Telegram. The user was left
staring at the source-picker screen with no feedback.

Issue #897 follow-up: the wallet picker is now keyed by ``source_asset_id``
(real user wallet) instead of a hard-coded provider list, mirroring the
bank-account flow. ``txsrc_wallet:<asset_uuid>`` pins the asset; the
confirmation renders "Ví điện tử [<asset.name>]" via
``resolve_source_label_for_expense``.

These tests pin the contract:
  - The wallet-asset branch MUST call ``edit_message_text`` to replace
    the picker with a confirmation line.
  - It MUST also fire ``answer_callback`` so the user's tap spinner
    clears.
  - The wizard state is cleared after a successful save.
  - A non-wallet source (``txsrc:cash``) follows the same contract.
  - The intermediate ``txsrc:e_wallet`` tap swaps the keyboard to list
    the user's actual wallet assets without creating an expense.
  - Empty-wallet users get a friendly alert instead of an empty picker.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.bot.keyboards.transaction_keyboard import transaction_source_keyboard  # noqa: E402

import pytest

from backend.bot.handlers import callbacks


def _money_in_state() -> dict:
    return {
        "flow": "transaction_source_select",
        "step": "source_type",
        "draft": {
            "amount": 20_000_000_000.0,
            "merchant": "lương",
            "note": "+20 tỷ lương",
            "transaction_type": "money_in",
        },
    }


_SENTINEL = object()


def _user(state=_SENTINEL) -> MagicMock:
    """Build a fake user with ``wizard_state`` defaulting to a live
    money-in source-picker flow. Pass ``state=None`` (explicitly) to
    simulate an expired/cleared wizard."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.wizard_state = _money_in_state() if state is _SENTINEL else state
    return user


def _callback(data: str) -> dict:
    return {
        "id": "cbq-1",
        "data": data,
        "message": {"chat": {"id": 999}, "message_id": 42},
        "from": {"id": 12345},
    }


def _expense(transaction_type: str = "money_in", amount: float = 20_000_000_000.0):
    expense = SimpleNamespace(
        id=uuid.uuid4(),
        amount=amount,
        transaction_type=transaction_type,
        raw_data=None,
    )
    return expense


def _wallet_asset(name: str = "MoMo cá nhân", subtype: str = "e_wallet"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        subtype=subtype,
        asset_type="cash",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_txsrc_wallet_asset_sends_confirmation_with_asset_name():
    """After tapping a specific wallet asset, the picker is replaced by
    a confirmation line that includes the asset's display name —
    "Ví điện tử [<name>]" — rendered via ``resolve_source_label_for_expense``.

    This is the visible contract for Issue #897: the user picked a real
    wallet (not a provider key), so the bot must echo that wallet back."""
    user = _user()
    db = MagicMock()
    expense = _expense()
    wallet_id = uuid.uuid4()

    edit_text = AsyncMock(return_value={"ok": True})
    answer = AsyncMock()
    send = AsyncMock()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            callbacks.expense_service,
            "create_expense",
            AsyncMock(return_value=expense),
        ) as create,
        patch.object(
            callbacks,
            "resolve_source_label_for_expense",
            AsyncMock(return_value="Ví điện tử [MoMo cá nhân]"),
        ),
        patch.object(callbacks, "edit_message_text", edit_text),
        patch.object(callbacks, "send_message", send),
        patch.object(callbacks, "answer_callback", answer),
        patch("backend.services.wizard_service.clear", AsyncMock()) as wizard_clear,
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback(f"txsrc_wallet:{wallet_id}")
        )

    assert handled is True
    create.assert_awaited_once()
    payload = create.await_args.args[2]
    assert payload.source_type == "e_wallet"
    assert str(payload.source_asset_id) == str(wallet_id)
    # provider must NOT be set from a hard-coded key — the asset is the truth.
    assert payload.e_wallet_provider is None
    wizard_clear.assert_awaited_once()
    edit_text.assert_awaited_once()
    edit_kwargs = edit_text.await_args.kwargs
    assert edit_kwargs["chat_id"] == 999
    assert edit_kwargs["message_id"] == 42
    assert "+20,000,000,000" in edit_kwargs["text"]
    assert "Ví điện tử [MoMo cá nhân]" in edit_kwargs["text"]
    # No fallback send_message when edit succeeded.
    send.assert_not_awaited()
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_wallet_falls_back_to_send_when_edit_fails():
    """Regression for #799: when ``edit_message_text`` silently returns
    ``None`` (picker message deleted, >48h old, transient Telegram 4xx),
    the handler must send a fresh confirmation so the user always gets
    feedback. Without this fallback the user is stranded on the picker
    even though the expense was written."""
    user = _user()
    db = MagicMock()
    expense = _expense()
    wallet_id = uuid.uuid4()

    edit_text = AsyncMock(return_value=None)
    send = AsyncMock()
    answer = AsyncMock()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            callbacks.expense_service,
            "create_expense",
            AsyncMock(return_value=expense),
        ),
        patch.object(
            callbacks,
            "resolve_source_label_for_expense",
            AsyncMock(return_value="Ví điện tử [ZaloPay nhà]"),
        ),
        patch.object(callbacks, "edit_message_text", edit_text),
        patch.object(callbacks, "send_message", send),
        patch.object(callbacks, "answer_callback", answer),
        patch("backend.services.wizard_service.clear", AsyncMock()),
    ):
        await callbacks._handle_source_selection_callback(
            db, _callback(f"txsrc_wallet:{wallet_id}")
        )

    edit_text.assert_awaited_once()
    send.assert_awaited_once()
    sent_chat_id, sent_text = send.await_args.args[0], send.await_args.args[1]
    assert sent_chat_id == 999
    assert "+20,000,000,000" in sent_text
    assert "Ví điện tử [ZaloPay nhà]" in sent_text
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_wallet_uses_asset_name_for_each_wallet():
    """The asset-keyed flow honours every wallet's own display name —
    whether it's a named provider asset (MoMo, ZaloPay…) or a generic
    user-created e_wallet asset. No hardcoded provider-label table."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    cases = [
        "Ví điện tử [MoMo cá nhân]",
        "Ví điện tử [VNPay công ty]",
        "Ví điện tử [ZaloPay vợ]",
        "Ví điện tử [Ví của bé]",  # user-created generic subtype
    ]
    for expected_label in cases:
        # Wizard state must look "active" each round because
        # ``wizard_service.clear`` is the production teardown.
        user.wizard_state = _money_in_state()
        wallet_id = uuid.uuid4()
        edit_text = AsyncMock(return_value={"ok": True})
        with (
            patch.object(
                callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
            ),
            patch.object(
                callbacks.expense_service,
                "create_expense",
                AsyncMock(return_value=expense),
            ),
            patch.object(
                callbacks,
                "resolve_source_label_for_expense",
                AsyncMock(return_value=expected_label),
            ),
            patch.object(callbacks, "edit_message_text", edit_text),
            patch.object(callbacks, "answer_callback", AsyncMock()),
            patch("backend.services.wizard_service.clear", AsyncMock()),
        ):
            await callbacks._handle_source_selection_callback(
                db, _callback(f"txsrc_wallet:{wallet_id}")
            )
        edit_text.assert_awaited_once()
        assert expected_label in edit_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_txsrc_cash_sends_confirmation_message():
    """Non-wallet source path (``txsrc:cash``) follows the same contract:
    the picker is replaced by a confirmation line."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    edit_text = AsyncMock(return_value={"ok": True})
    answer = AsyncMock()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            callbacks.expense_service,
            "create_expense",
            AsyncMock(return_value=expense),
        ),
        patch.object(
            callbacks,
            "resolve_source_label_for_expense",
            AsyncMock(return_value="Tiền mặt"),
        ),
        patch.object(callbacks, "edit_message_text", edit_text),
        patch.object(callbacks, "send_message", AsyncMock()),
        patch.object(callbacks, "answer_callback", answer),
        patch("backend.services.wizard_service.clear", AsyncMock()),
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:cash")
        )

    assert handled is True
    edit_text.assert_awaited_once()
    assert "Tiền mặt" in edit_text.await_args.kwargs["text"]
    answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_skip_still_sends_confirmation_message():
    """``txsrc:skip`` saves the expense without a source — the picker
    must still be replaced so the user knows the write landed."""
    user = _user()
    db = MagicMock()
    expense = _expense()

    edit_text = AsyncMock(return_value={"ok": True})
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            callbacks.expense_service,
            "create_expense",
            AsyncMock(return_value=expense),
        ),
        patch.object(callbacks, "edit_message_text", edit_text),
        patch.object(callbacks, "send_message", AsyncMock()),
        patch.object(callbacks, "answer_callback", AsyncMock()),
        patch("backend.services.wizard_service.clear", AsyncMock()),
    ):
        await callbacks._handle_source_selection_callback(db, _callback("txsrc:skip"))
    edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_txsrc_e_wallet_lists_user_wallets_in_keyboard():
    """The intermediate ``txsrc:e_wallet`` tap swaps the keyboard to a
    picker listing the user's actual wallet assets — NOT a hardcoded
    provider list. Each row carries ``txsrc_wallet:<asset_uuid>``.

    The handler must NOT call ``create_expense``: it's just a sub-menu."""
    user = _user()
    db = MagicMock()
    wallets = [
        _wallet_asset(name="MoMo cá nhân", subtype="e_wallet"),
        _wallet_asset(name="ZaloPay vợ", subtype="zalopay"),
    ]

    edit_markup = AsyncMock()
    answer = AsyncMock()
    create = AsyncMock()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks, "list_assets", AsyncMock(return_value=wallets)),
        patch.object(callbacks.expense_service, "create_expense", create),
        patch.object(callbacks, "edit_message_reply_markup", edit_markup),
        patch.object(callbacks, "answer_callback", answer),
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:e_wallet")
        )

    assert handled is True
    create.assert_not_awaited()
    edit_markup.assert_awaited_once()
    answer.assert_awaited_once()
    kb = edit_markup.await_args.kwargs["reply_markup"]["inline_keyboard"]
    # First N rows = one button per wallet asset.
    labels = [row[0]["text"] for row in kb[: len(wallets)]]
    assert "MoMo cá nhân" in labels[0]
    assert "ZaloPay vợ" in labels[1]
    callback_data = [row[0]["callback_data"] for row in kb[: len(wallets)]]
    assert callback_data[0] == f"txsrc_wallet:{wallets[0].id}"
    assert callback_data[1] == f"txsrc_wallet:{wallets[1].id}"


@pytest.mark.asyncio
async def test_txsrc_e_wallet_alerts_when_user_has_no_wallets():
    """If the user taps "👛 Ví điện tử" but owns no wallet assets, the
    handler must surface a friendly alert (mirrors the bank-account
    empty-state at ``txsrc:bank_pick``) — not show an empty keyboard.

    The expense MUST NOT be created in this branch."""
    user = _user()
    db = MagicMock()

    answer = AsyncMock()
    create = AsyncMock()
    edit_markup = AsyncMock()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks, "list_assets", AsyncMock(return_value=[])),
        patch.object(callbacks.expense_service, "create_expense", create),
        patch.object(callbacks, "edit_message_reply_markup", edit_markup),
        patch.object(callbacks, "answer_callback", answer),
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:e_wallet")
        )

    assert handled is True
    create.assert_not_awaited()
    edit_markup.assert_not_awaited()
    answer.assert_awaited_once()
    assert answer.await_args.kwargs.get("show_alert") is True
    assert "ví điện tử" in (answer.await_args.kwargs.get("text") or "").lower()


@pytest.mark.asyncio
async def test_txsrc_e_wallet_filters_non_wallet_assets():
    """``list_assets(asset_type="cash")`` returns ALL cash-family rows
    (bank_checking, cash, e_wallet, momo…). The handler must filter to
    wallet-only subtypes before rendering the picker, otherwise the user
    would see their checking account in the wallet picker."""
    user = _user()
    db = MagicMock()
    mixed = [
        _wallet_asset(name="VCB checking", subtype="bank_checking"),
        _wallet_asset(name="Tiền mặt", subtype="cash"),
        _wallet_asset(name="MoMo cá nhân", subtype="e_wallet"),
        _wallet_asset(name="ZaloPay vợ", subtype="zalopay"),
    ]

    edit_markup = AsyncMock()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks, "list_assets", AsyncMock(return_value=mixed)),
        patch.object(callbacks, "edit_message_reply_markup", edit_markup),
        patch.object(callbacks, "answer_callback", AsyncMock()),
    ):
        await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:e_wallet")
        )

    edit_markup.assert_awaited_once()
    kb = edit_markup.await_args.kwargs["reply_markup"]["inline_keyboard"]
    # Only the two wallet assets should appear as picker rows. The trailing
    # rows are "Back" / "Skip" controls.
    wallet_rows = [
        row for row in kb if row and row[0]["callback_data"].startswith("txsrc_wallet:")
    ]
    assert len(wallet_rows) == 2
    labels = [row[0]["text"] for row in wallet_rows]
    assert "MoMo cá nhân" in labels[0]
    assert "ZaloPay vợ" in labels[1]


@pytest.mark.asyncio
async def test_stale_wizard_state_does_not_call_create_expense():
    """If the source-picker wizard already expired (state cleared),
    we must NOT silently create a duplicate expense."""
    user = _user(state=None)
    db = MagicMock()

    create = AsyncMock()
    answer = AsyncMock()
    wallet_id = uuid.uuid4()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks.expense_service, "create_expense", create),
        patch.object(callbacks, "answer_callback", answer),
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback(f"txsrc_wallet:{wallet_id}")
        )

    assert handled is True
    create.assert_not_awaited()
    answer.assert_awaited_once()
    assert "hết hạn" in answer.await_args.kwargs["text"].lower()


@pytest.mark.asyncio
async def test_txsrc_credit_card_shows_all_cards_for_expense_only():
    user = _user(
        state={
            "flow": "transaction_source_select",
            "step": "source_type",
            "draft": {"amount": 200000.0, "transaction_type": "expense"},
        }
    )
    db = MagicMock()
    cards = [
        SimpleNamespace(id=uuid.uuid4(), bank_name="VCB"),
        SimpleNamespace(id=uuid.uuid4(), bank_name="ACB"),
    ]
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks, "list_credit_cards", AsyncMock(return_value=cards)),
        patch.object(
            callbacks, "edit_message_reply_markup", AsyncMock()
        ) as edit_markup,
        patch.object(callbacks, "answer_callback", AsyncMock()),
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback("txsrc:credit_card")
        )

    assert handled is True
    kb = edit_markup.await_args.kwargs["reply_markup"]["inline_keyboard"]
    labels = [row[0]["text"] for row in kb[:2]]
    assert labels == ["💳 Thẻ tín dụng - VCB", "💳 Thẻ tín dụng - ACB"]


@pytest.mark.asyncio
async def test_txsrc_card_select_confirmation_mentions_bank_name():
    user = _user(
        state={
            "flow": "transaction_source_select",
            "step": "source_type",
            "draft": {
                "amount": 200000.0,
                "transaction_type": "expense",
                "merchant": "test",
            },
        }
    )
    db = MagicMock()
    expense = _expense(transaction_type="expense", amount=200000.0)
    card_id = uuid.uuid4()
    card = SimpleNamespace(id=card_id, bank_name="MSB")
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks, "list_credit_cards", AsyncMock(return_value=[card])),
        patch.object(
            callbacks.expense_service, "create_expense", AsyncMock(return_value=expense)
        ),
        patch.object(
            callbacks, "resolve_source_label_for_expense", AsyncMock(return_value=None)
        ),
        patch.object(
            callbacks, "edit_message_text", AsyncMock(return_value={"ok": True})
        ) as edit_text,
        patch.object(callbacks, "answer_callback", AsyncMock()),
        patch("backend.services.wizard_service.clear", AsyncMock()),
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback(f"txsrc_card:{card_id}")
        )

    assert handled is True
    assert "Thẻ tín dụng MSB" in edit_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_txsrc_card_select_creates_expense_with_credit_card_source():
    user = _user(
        state={
            "flow": "transaction_source_select",
            "step": "source_type",
            "draft": {
                "amount": 200000.0,
                "transaction_type": "expense",
                "merchant": "test",
            },
        }
    )
    db = MagicMock()
    expense = _expense(transaction_type="expense", amount=200000.0)
    card_id = uuid.uuid4()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            callbacks,
            "list_credit_cards",
            AsyncMock(return_value=[SimpleNamespace(id=card_id, bank_name="VCB")]),
        ),
        patch.object(
            callbacks.expense_service, "create_expense", AsyncMock(return_value=expense)
        ) as create,
        patch.object(
            callbacks, "resolve_source_label_for_expense", AsyncMock(return_value=None)
        ),
        patch.object(
            callbacks, "edit_message_text", AsyncMock(return_value={"ok": True})
        ),
        patch.object(callbacks, "answer_callback", AsyncMock()),
        patch("backend.services.wizard_service.clear", AsyncMock()),
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback(f"txsrc_card:{card_id}")
        )

    assert handled is True
    payload = create.await_args.args[2]
    assert payload.source_type == "credit_card"
    assert str(payload.source_credit_card_id) == str(card_id)


@pytest.mark.asyncio
async def test_txsrc_card_select_rejects_unknown_card_id():
    user = _user(
        state={
            "flow": "transaction_source_select",
            "step": "source_type",
            "draft": {
                "amount": 200000.0,
                "transaction_type": "expense",
                "merchant": "test",
            },
        }
    )
    db = MagicMock()
    card_id = uuid.uuid4()
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks, "list_credit_cards", AsyncMock(return_value=[])),
        patch.object(
            callbacks.expense_service, "create_expense", AsyncMock()
        ) as create,
        patch.object(callbacks, "answer_callback", AsyncMock()) as answer,
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback(f"txsrc_card:{card_id}")
        )

    assert handled is True
    create.assert_not_awaited()
    answer.assert_awaited_once()
    assert "không hợp lệ" in (answer.await_args.kwargs.get("text") or "").lower()


def test_tx_source_keyboard_expense_includes_credit_card():
    kb = transaction_source_keyboard("expense")["inline_keyboard"]
    assert any(btn["callback_data"] == "txsrc:credit_card" for row in kb for btn in row)


def test_tx_source_keyboard_money_in_excludes_credit_card():
    kb = transaction_source_keyboard("money_in")["inline_keyboard"]
    assert all(btn["callback_data"] != "txsrc:credit_card" for row in kb for btn in row)


@pytest.mark.asyncio
async def test_handle_transaction_callback_routes_txsrc_bank_prefix():
    db = MagicMock()
    cb = _callback(f"txsrc_bank:{uuid.uuid4()}")
    with patch.object(
        callbacks,
        "_handle_source_selection_callback",
        AsyncMock(return_value=True),
    ) as source_handler:
        handled = await callbacks.handle_transaction_callback(db, cb)

    assert handled is True
    source_handler.assert_awaited_once_with(db, cb)


@pytest.mark.asyncio
async def test_handle_transaction_callback_routes_txsrc_wallet_prefix():
    """Regression: ``txsrc_wallet:<uuid>`` must hit the source-selection
    handler — not fall through to the generic callback dispatcher.
    Otherwise the user's wallet tap silently no-ops."""
    db = MagicMock()
    cb = _callback(f"txsrc_wallet:{uuid.uuid4()}")
    with patch.object(
        callbacks,
        "_handle_source_selection_callback",
        AsyncMock(return_value=True),
    ) as source_handler:
        handled = await callbacks.handle_transaction_callback(db, cb)

    assert handled is True
    source_handler.assert_awaited_once_with(db, cb)


@pytest.mark.asyncio
async def test_create_expense_failure_alerts_user_and_clears_wizard():
    """Issue #948 safety net: when ``create_expense`` raises (e.g. DB
    check-constraint violation on the e_wallet flow), the user must NOT
    be left staring at a stuck spinner.

    Contract:
      - ``answer_callback`` fires with ``show_alert=True`` and a friendly
        Vietnamese message (Bé Tiền tone — no harsh wording).
      - A chat fallback ``send_message`` follows so the message survives
        the alert dismiss.
      - The wizard state is cleared so the user can retry from scratch.
      - The handler returns ``True`` so the dispatcher stops processing.
    """
    user = _user()
    db = MagicMock()
    wallet_id = uuid.uuid4()

    answer = AsyncMock()
    send = AsyncMock()
    edit_text = AsyncMock()
    boom = AsyncMock(side_effect=RuntimeError("simulated IntegrityError"))
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks.expense_service, "create_expense", boom),
        patch.object(callbacks, "edit_message_text", edit_text),
        patch.object(callbacks, "send_message", send),
        patch.object(callbacks, "answer_callback", answer),
        patch("backend.services.wizard_service.clear", AsyncMock()) as wizard_clear,
    ):
        handled = await callbacks._handle_source_selection_callback(
            db, _callback(f"txsrc_wallet:{wallet_id}")
        )

    assert handled is True
    # The picker message is NOT edited on failure — the user gets a fresh
    # chat message + alert instead.
    edit_text.assert_not_awaited()
    answer.assert_awaited_once()
    assert answer.await_args.kwargs.get("show_alert") is True
    alert_text = (answer.await_args.kwargs.get("text") or "").lower()
    # Friendly Bé Tiền tone — never harsh.
    assert "chưa ghi" in alert_text or "không ghi" in alert_text
    send.assert_awaited_once()
    sent_text = send.await_args.args[1].lower()
    assert "chưa ghi" in sent_text or "không ghi" in sent_text
    wizard_clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_expense_failure_does_not_crash_without_chat_id():
    """If Telegram somehow delivers a callback without a chat (rare —
    shouldn't happen for inline keyboards but is defensively guarded),
    the safety net must still alert the user via ``answer_callback``
    without raising on the missing ``chat_id``."""
    user = _user()
    db = MagicMock()
    wallet_id = uuid.uuid4()

    cb = _callback(f"txsrc_wallet:{wallet_id}")
    cb["message"] = {}  # no chat key — chat_id resolves to None

    answer = AsyncMock()
    send = AsyncMock()
    boom = AsyncMock(side_effect=RuntimeError("boom"))
    with (
        patch.object(
            callbacks, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(callbacks.expense_service, "create_expense", boom),
        patch.object(callbacks, "send_message", send),
        patch.object(callbacks, "answer_callback", answer),
        patch("backend.services.wizard_service.clear", AsyncMock()),
    ):
        handled = await callbacks._handle_source_selection_callback(db, cb)

    assert handled is True
    answer.assert_awaited_once()
    # No chat to send a fallback into — skip silently rather than crash.
    send.assert_not_awaited()
