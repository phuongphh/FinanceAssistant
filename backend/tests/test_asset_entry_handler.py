"""End-to-end-ish tests for the asset-entry wizard handler.

Telegram + DB are mocked; we focus on:
- Cash flow: subtype pick → name+amount text → asset created
- Stock flow: subtype → ticker → quantity → price → "use same" → asset
- Real estate flow: subtype → name → initial → current → asset created
- Cancel clears state
- Parse failures re-prompt without dropping wizard state
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import asset_entry
from backend.models.user import User
from backend.wealth.models.asset import Asset


def _user(state: dict | None = None) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 100
    u.display_name = "Test"
    u.wizard_state = state
    u.onboarding_step = 6  # FIRST_ASSET — exercise the bridge
    u.onboarding_completed_at = None
    u.onboarding_skipped_asset = False
    u.created_at = datetime.utcnow()
    return u


def _db(user: User | None = None) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    return db


def _asset(asset_type: str = "cash", value: int = 100_000_000) -> Asset:
    a = Asset()
    a.id = uuid.uuid4()
    a.user_id = uuid.uuid4()
    a.asset_type = asset_type
    a.subtype = "bank_savings"
    a.name = "VCB"
    a.initial_value = Decimal(value)
    a.current_value = Decimal(value)
    a.acquired_at = date.today()
    a.is_active = True
    a.extra = {}
    return a


# -----------------------------------------------------------------
# Cash flow
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cash_amount_input_parses_label_and_creates_asset():
    user = _user({
        "flow": asset_entry.FLOW_CASH,
        "step": "amount",
        "draft": {"asset_type": "cash", "subtype": "bank_savings"},
    })
    db = _db(user)
    created = _asset()

    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "create_asset",
                      AsyncMock(return_value=created)) as create_mock, \
         patch.object(asset_entry.net_worth_calculator, "calculate",
                      AsyncMock(return_value=MagicMock(
                          total=Decimal("100_000_000"), asset_count=1,
                      ))), \
         patch.object(asset_entry, "update_user_level",
                      AsyncMock(return_value=None)), \
         patch.object(asset_entry.wizard_service, "clear",
                      AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB 100 triệu", "chat": {"id": 100},
             "from": {"id": 100}},
        )
    assert consumed is True
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["asset_type"] == "cash"
    assert kwargs["name"] == "VCB"
    assert kwargs["initial_value"] == Decimal("100000000")
    assert kwargs["subtype"] == "bank_savings"
    # Two messages sent: confirmation + add-more prompt.
    assert send.await_count >= 2


@pytest.mark.asyncio
async def test_cash_amount_input_rejects_negative_with_warm_message():
    """TC-1.6.C1 — `"VCB -100 triệu"` must be rejected.

    Asset must NOT be created, wizard state must NOT be cleared, and the
    reply must be the specific "must be > 0" message — not the generic
    "couldn't parse" one.
    """
    user = _user({
        "flow": asset_entry.FLOW_CASH,
        "step": "amount",
        "draft": {"asset_type": "cash", "subtype": "bank_savings"},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "create_asset",
                      AsyncMock()) as create_mock, \
         patch.object(asset_entry, "send_message", AsyncMock()) as send, \
         patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear:
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB -100 triệu", "chat": {"id": 100},
             "from": {"id": 100}},
        )
    assert consumed is True
    create_mock.assert_not_awaited()
    clear.assert_not_awaited()  # user stays on amount step
    send.assert_awaited_once()
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    assert "lớn hơn 0" in sent_text


@pytest.mark.asyncio
async def test_cash_amount_input_parse_fails_keeps_wizard_open():
    user = _user({
        "flow": asset_entry.FLOW_CASH,
        "step": "amount",
        "draft": {"asset_type": "cash", "subtype": "bank_savings"},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "create_asset",
                      AsyncMock()) as create_mock, \
         patch.object(asset_entry, "send_message", AsyncMock()) as send, \
         patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear:
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "blah blah", "chat": {"id": 100},
             "from": {"id": 100}},
        )
    assert consumed is True
    create_mock.assert_not_awaited()
    clear.assert_not_awaited()  # wizard stays open
    send.assert_awaited_once()  # warm re-prompt


# -----------------------------------------------------------------
# Stock flow — ticker step
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_stock_ticker_normalised_uppercase():
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "ticker",
        "draft": {"asset_type": "stock", "subtype": "vn_stock", "extra": {"exchange": "HOSE"}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "vnm stocks", "chat": {"id": 100},
             "from": {"id": 100}},
        )
    update_step.assert_awaited_once()
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["step"] == "quantity"
    assert patch_kwargs["draft_patch"]["extra"]["ticker"] == "VNM"
    assert patch_kwargs["draft_patch"]["name"] == "VNM"


@pytest.mark.asyncio
async def test_stock_ticker_rejects_garbage():
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "ticker",
        "draft": {"extra": {}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "!!!?", "chat": {"id": 100},
             "from": {"id": 100}},
        )
    update_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_stock_quantity_rejects_non_integer():
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "quantity",
        "draft": {"extra": {"ticker": "VNM"}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "abc", "chat": {"id": 100}, "from": {"id": 100}},
        )
    update_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_stock_quantity_accepts_with_separators():
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "quantity",
        "draft": {"extra": {"ticker": "VNM"}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "1,000", "chat": {"id": 100}, "from": {"id": 100}},
        )
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["draft_patch"]["extra"]["quantity"] == 1000


# -----------------------------------------------------------------
# Real estate flow
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_stock_subtype_pick_seeds_usd_currency_for_foreign_stock():
    """Picking 'foreign_stock' must seed extra.currency=USD + fx_rate
    so downstream price prompts and the saver know to convert."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "subtype",
        "draft": {"asset_type": "stock", "extra": {}},
    })
    db = _db(user)
    with patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry._handle_stock_subtype_pick(
            db, 100, user, "foreign_stock",
        )
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["draft_patch"]["subtype"] == "foreign_stock"
    extra = patch_kwargs["draft_patch"]["extra"]
    assert extra["currency"] == "USD"
    assert extra["fx_rate_vnd"] == float(asset_entry.USD_VND_RATE)


@pytest.mark.asyncio
async def test_stock_subtype_pick_no_currency_for_vn_stock():
    """vn_stock must NOT get a currency tag — the saver branches on it."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "subtype",
        "draft": {"asset_type": "stock", "extra": {}},
    })
    db = _db(user)
    with patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry._handle_stock_subtype_pick(
            db, 100, user, "vn_stock",
        )
    extra = update_step.await_args.kwargs["draft_patch"]["extra"]
    assert "currency" not in extra
    assert extra.get("exchange") == "HOSE"


@pytest.mark.asyncio
async def test_fund_quantity_prompt_uses_chung_chi_quy():
    """Fund subtype must prompt with 'chứng chỉ quỹ', not 'cổ phiếu'."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "quantity",
        "draft": {"asset_type": "stock", "subtype": "fund",
                  "extra": {"ticker": "VESAF"}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "100", "chat": {"id": 100}, "from": {"id": 100}},
        )
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    assert "chứng chỉ quỹ" in sent_text
    assert "cổ phiếu" not in sent_text  # do NOT reuse stock wording


@pytest.mark.asyncio
async def test_fund_avg_price_confirm_uses_ccq_suffix():
    """Per-unit price confirmation should read '/ccq' for funds, '/cp' for stocks."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "avg_price",
        "draft": {"asset_type": "stock", "subtype": "fund",
                  "extra": {"ticker": "VESAF", "quantity": 100}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "15000", "chat": {"id": 100}, "from": {"id": 100}},
        )
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    assert "/ccq" in sent_text
    assert "/cp" not in sent_text
    assert "1 chứng chỉ quỹ" in sent_text


@pytest.mark.asyncio
async def test_foreign_stock_avg_price_parses_usd_and_converts_to_vnd():
    """Typing '150' on a foreign-stock avg-price step must be read as USD,
    converted with USD_VND_RATE, and saved as float VND in extra.avg_price."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "avg_price",
        "draft": {"asset_type": "stock", "subtype": "foreign_stock",
                  "extra": {"ticker": "AAPL", "quantity": 10,
                            "currency": "USD",
                            "fx_rate_vnd": float(asset_entry.USD_VND_RATE)}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "150", "chat": {"id": 100}, "from": {"id": 100}},
        )
    patch_kwargs = update_step.await_args.kwargs
    extra = patch_kwargs["draft_patch"]["extra"]
    expected_vnd = float(Decimal("150") * asset_entry.USD_VND_RATE)
    assert extra["avg_price"] == expected_vnd
    assert extra["avg_price_usd"] == 150.0
    # initial_value (VND) = 150 USD × 10 × rate.
    assert patch_kwargs["draft_patch"]["initial_value"] == expected_vnd * 10
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    # User-facing message must show both USD and tạm tính VND.
    assert "$150" in sent_text
    assert "$1,500" in sent_text
    assert "VNĐ tạm tính" in sent_text


@pytest.mark.asyncio
async def test_foreign_stock_avg_price_rejects_vn_unit_suffix():
    """'150 tr' on a foreign-stock step must be rejected, not interpreted as
    150 million USD. The USD parser ignores VN units entirely."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "avg_price",
        "draft": {"asset_type": "stock", "subtype": "foreign_stock",
                  "extra": {"ticker": "AAPL", "quantity": 10,
                            "currency": "USD"}},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "150 tr", "chat": {"id": 100}, "from": {"id": 100}},
        )
    update_step.assert_not_awaited()  # bail with re-prompt
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    assert "USD" in sent_text


@pytest.mark.asyncio
async def test_foreign_stock_save_persists_usd_and_fx_rate():
    """End of foreign-stock flow: extra must carry USD-side fields + FX rate."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "current_price",
        "draft": {
            "asset_type": "stock",
            "subtype": "foreign_stock",
            "name": "AAPL",
            "extra": {
                "ticker": "AAPL",
                "quantity": 10,
                "currency": "USD",
                "fx_rate_vnd": float(asset_entry.USD_VND_RATE),
                "avg_price": float(Decimal("150") * asset_entry.USD_VND_RATE),
                "avg_price_usd": 150.0,
            },
        },
    })
    db = _db(user)
    created = _asset(asset_type="stock", value=int(Decimal("165") * asset_entry.USD_VND_RATE * 10))
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "create_asset",
                      AsyncMock(return_value=created)) as create_mock, \
         patch.object(asset_entry.net_worth_calculator, "calculate",
                      AsyncMock(return_value=MagicMock(
                          total=Decimal("100_000_000"), asset_count=1,
                      ))), \
         patch.object(asset_entry, "update_user_level",
                      AsyncMock(return_value=None)), \
         patch.object(asset_entry.wizard_service, "clear", AsyncMock()), \
         patch.object(asset_entry.wizard_service, "update_step", AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()):
        # Simulate the user picking "Nhập giá hiện tại" and typing "165".
        draft = user.wizard_state["draft"]
        await asset_entry._handle_stock_current_price_input(
            db, 100, user, "165", draft,
        )
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    extra = kwargs["extra"]
    assert extra["currency"] == "USD"
    assert extra["avg_price_usd"] == 150.0
    assert extra["current_price_usd"] == 165.0
    assert extra["initial_value_usd"] == 1500.0
    assert extra["current_value_usd"] == 1650.0
    assert extra["fx_rate_vnd"] == float(asset_entry.USD_VND_RATE)
    # Stored VND value is the converted current_price × quantity.
    expected_current_vnd = Decimal("165") * asset_entry.USD_VND_RATE * 10
    assert kwargs["current_value"] == expected_current_vnd


@pytest.mark.asyncio
async def test_foreign_stock_same_as_purchase_reuses_usd_avg_as_current():
    """'Use purchase price' for foreign stock: current_price_usd must mirror
    avg_price_usd, not be left missing or zero."""
    user = _user({
        "flow": asset_entry.FLOW_STOCK,
        "step": "current_price",
        "draft": {
            "asset_type": "stock",
            "subtype": "foreign_stock",
            "name": "AAPL",
            "extra": {
                "ticker": "AAPL",
                "quantity": 10,
                "currency": "USD",
                "fx_rate_vnd": float(asset_entry.USD_VND_RATE),
                "avg_price": float(Decimal("150") * asset_entry.USD_VND_RATE),
                "avg_price_usd": 150.0,
            },
        },
    })
    db = _db(user)
    created = _asset(asset_type="stock")
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "create_asset",
                      AsyncMock(return_value=created)) as create_mock, \
         patch.object(asset_entry.net_worth_calculator, "calculate",
                      AsyncMock(return_value=MagicMock(
                          total=Decimal("100_000_000"), asset_count=1,
                      ))), \
         patch.object(asset_entry, "update_user_level",
                      AsyncMock(return_value=None)), \
         patch.object(asset_entry.wizard_service, "clear", AsyncMock()), \
         patch.object(asset_entry, "answer_callback", AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:stock_price:same",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    extra = create_mock.await_args.kwargs["extra"]
    assert extra["current_price_usd"] == 150.0
    assert extra["initial_value_usd"] == 1500.0
    assert extra["current_value_usd"] == 1500.0


@pytest.mark.asyncio
async def test_real_estate_initial_value_accepts_ty():
    user = _user({
        "flow": asset_entry.FLOW_REAL_ESTATE,
        "step": "initial_value",
        "draft": {
            "asset_type": "real_estate",
            "subtype": "house_primary",
            "name": "Nhà Mỹ Đình",
            "extra": {},
        },
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "update_step",
                      AsyncMock()) as update_step, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "2 tỷ", "chat": {"id": 100}, "from": {"id": 100}},
        )
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["draft_patch"]["initial_value"] == float(Decimal("2_000_000_000"))
    assert patch_kwargs["step"] == "current_value"


@pytest.mark.asyncio
async def test_real_estate_current_value_creates_asset():
    user = _user({
        "flow": asset_entry.FLOW_REAL_ESTATE,
        "step": "current_value",
        "draft": {
            "asset_type": "real_estate",
            "subtype": "house_primary",
            "name": "Nhà Mỹ Đình",
            "initial_value": float(Decimal("2_000_000_000")),
            "extra": {},
        },
    })
    db = _db(user)
    created = _asset(asset_type="real_estate", value=2_500_000_000)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "create_asset",
                      AsyncMock(return_value=created)) as create_mock, \
         patch.object(asset_entry.net_worth_calculator, "calculate",
                      AsyncMock(return_value=MagicMock(
                          total=Decimal("2_500_000_000"), asset_count=1,
                      ))), \
         patch.object(asset_entry, "update_user_level",
                      AsyncMock(return_value=None)), \
         patch.object(asset_entry.wizard_service, "clear", AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "2.5 tỷ", "chat": {"id": 100}, "from": {"id": 100}},
        )
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["initial_value"] == Decimal("2_000_000_000")
    assert kwargs["current_value"] == Decimal("2_500_000_000")


# -----------------------------------------------------------------
# Callback dispatch
# -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_cancel_clears_state():
    user = _user({"flow": "asset_add_cash", "step": "amount", "draft": {}})
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.wizard_service, "clear",
                      AsyncMock()) as clear, \
         patch.object(asset_entry, "answer_callback", AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()):
        consumed = await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:cancel",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    assert consumed is True
    clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_type_picker_routes_to_starter():
    user = _user()
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry, "_start_cash_subtype_pick",
                      AsyncMock()) as starter, \
         patch.object(asset_entry, "answer_callback", AsyncMock()):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:type:cash",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    starter.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_undo_hard_deletes_asset_and_recomputes_net_worth():
    """User taps 'Huỷ tài sản vừa nhập' → hard delete + send confirmation."""
    user = _user()
    db = _db(user)
    target_id = uuid.uuid4()
    asset = _asset()
    asset.id = target_id
    asset.name = "VCB-001"

    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "get_asset_by_id",
                      AsyncMock(return_value=asset)), \
         patch.object(asset_entry.asset_service, "hard_delete",
                      AsyncMock(return_value=True)) as delete_mock, \
         patch.object(asset_entry.net_worth_calculator, "calculate",
                      AsyncMock(return_value=MagicMock(
                          total=Decimal("0"), asset_count=0,
                      ))), \
         patch.object(asset_entry, "update_user_level",
                      AsyncMock(return_value=None)), \
         patch.object(asset_entry, "answer_callback", AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        consumed = await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": f"asset_add:undo:{target_id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    assert consumed is True
    delete_mock.assert_awaited_once()
    args = delete_mock.await_args.args
    assert args[1] == user.id
    assert args[2] == target_id
    send.assert_awaited()
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    assert "Đã huỷ" in sent_text
    assert "VCB-001" in sent_text


@pytest.mark.asyncio
async def test_callback_undo_handles_invalid_uuid_gracefully():
    user = _user()
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "hard_delete",
                      AsyncMock()) as delete_mock, \
         patch.object(asset_entry, "answer_callback", AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        consumed = await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:undo:not-a-uuid",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    assert consumed is True
    delete_mock.assert_not_awaited()
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_undo_when_asset_already_gone():
    """Tapping undo twice (or after another action removed the asset)
    should not crash — show a friendly message instead."""
    user = _user()
    db = _db(user)
    target_id = uuid.uuid4()
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry.asset_service, "get_asset_by_id",
                      AsyncMock(return_value=None)), \
         patch.object(asset_entry.asset_service, "hard_delete",
                      AsyncMock(return_value=False)) as delete_mock, \
         patch.object(asset_entry, "answer_callback", AsyncMock()), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": f"asset_add:undo:{target_id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    delete_mock.assert_not_awaited()  # bailed before delete
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_text_input_returns_false_when_no_wizard():
    user = _user(state=None)
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "anything", "chat": {"id": 100}, "from": {"id": 100}},
        )
    assert consumed is False


@pytest.mark.asyncio
async def test_text_input_returns_false_for_non_asset_flow():
    """Storytelling and other non-asset flows must NOT be intercepted —
    they have their own router earlier in the dispatch chain."""
    user = _user({"flow": "storytelling", "step": "awaiting_story", "draft": {}})
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "anything", "chat": {"id": 100}, "from": {"id": 100}},
        )
    assert consumed is False


@pytest.mark.asyncio
async def test_text_input_at_picker_step_nudges_instead_of_leaking():
    """Regression for the VCB-002 incident.

    User taps "+Thêm tài sản" → wizard at FLOW_PICKER:type. Then types
    "VCB-002 20 triệu" without picking a type. Must be CONSUMED with a
    nudge — not fall through to the NL expense parser.
    """
    user = _user({
        "flow": asset_entry.FLOW_PICKER,
        "step": "type",
        "draft": {},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send, \
         patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear:
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB-002 20 triệu", "chat": {"id": 100},
             "from": {"id": 100}},
        )
    assert consumed is True
    clear.assert_not_awaited()  # picker stays open so user can still tap
    send.assert_awaited_once()
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    assert "tap nút" in sent_text


@pytest.mark.asyncio
async def test_text_input_at_subtype_step_nudges_instead_of_leaking():
    """Same incident class, second leaky step: user picked Cash type but
    typed text instead of picking a subtype. Must be consumed."""
    user = _user({
        "flow": asset_entry.FLOW_CASH,
        "step": "subtype",
        "draft": {"asset_type": "cash"},
    })
    db = _db(user)
    with patch.object(asset_entry, "get_user_by_telegram_id",
                      AsyncMock(return_value=user)), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB-002 20 triệu", "chat": {"id": 100},
             "from": {"id": 100}},
        )
    assert consumed is True
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_asset_wizard_sets_picker_state():
    """After starting the wizard, wizard_state must be the picker
    sentinel — NOT null. That's what closes the leak window."""
    user = _user(state={"flow": "asset_add_cash", "step": "amount", "draft": {}})
    db = _db(user)
    with patch.object(asset_entry.wizard_service, "start_flow",
                      AsyncMock()) as start_flow, \
         patch.object(asset_entry, "send_message", AsyncMock()):
        await asset_entry.start_asset_wizard(db, 100, user)
    start_flow.assert_awaited_once()
    args = start_flow.await_args.args
    kwargs = start_flow.await_args.kwargs
    # Signature: start_flow(db, user_id, flow, step=, draft=)
    assert args[2] == asset_entry.FLOW_PICKER
    assert kwargs["step"] == "type"
    assert kwargs["draft"] == {}


@pytest.mark.asyncio
async def test_cancel_wizard_clears_active_asset_flow():
    user = _user({
        "flow": asset_entry.FLOW_CASH,
        "step": "amount",
        "draft": {"asset_type": "cash"},
    })
    db = _db(user)
    with patch.object(asset_entry.wizard_service, "clear",
                      AsyncMock()) as clear, \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        cancelled = await asset_entry.cancel_wizard(db, 100, user)
    assert cancelled is True
    clear.assert_awaited_once()
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_wizard_noop_when_other_flow_active():
    """If the user is in storytelling (or no flow), cancel_wizard must
    return False so the caller can fall back to the right canceller."""
    user = _user({"flow": "storytelling", "step": "x", "draft": {}})
    db = _db(user)
    with patch.object(asset_entry.wizard_service, "clear",
                      AsyncMock()) as clear, \
         patch.object(asset_entry, "send_message", AsyncMock()) as send:
        cancelled = await asset_entry.cancel_wizard(db, 100, user)
    assert cancelled is False
    clear.assert_not_awaited()
    send.assert_not_awaited()
