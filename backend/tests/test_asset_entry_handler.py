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
