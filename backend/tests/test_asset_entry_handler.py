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
    user = _user(
        {
            "flow": asset_entry.FLOW_CASH,
            "step": "amount",
            "draft": {"asset_type": "cash", "subtype": "bank_savings"},
        }
    )
    db = _db(user)
    created = _asset()

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ) as create_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("100_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB 100 triệu", "chat": {"id": 100}, "from": {"id": 100}},
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
    user = _user(
        {
            "flow": asset_entry.FLOW_CASH,
            "step": "amount",
            "draft": {"asset_type": "cash", "subtype": "bank_savings"},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock()
        ) as create_mock,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear,
    ):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB -100 triệu", "chat": {"id": 100}, "from": {"id": 100}},
        )
    assert consumed is True
    create_mock.assert_not_awaited()
    clear.assert_not_awaited()  # user stays on amount step
    send.assert_awaited_once()
    sent_text = send.await_args.kwargs.get("text") or send.await_args.args[0]
    assert "lớn hơn 0" in sent_text


@pytest.mark.asyncio
async def test_cash_amount_input_parse_fails_keeps_wizard_open():
    user = _user(
        {
            "flow": asset_entry.FLOW_CASH,
            "step": "amount",
            "draft": {"asset_type": "cash", "subtype": "bank_savings"},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock()
        ) as create_mock,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear,
    ):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "blah blah", "chat": {"id": 100}, "from": {"id": 100}},
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
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "ticker",
            "draft": {
                "asset_type": "stock",
                "subtype": "vn_stock",
                "extra": {"exchange": "HOSE"},
            },
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "vnm stocks", "chat": {"id": 100}, "from": {"id": 100}},
        )
    update_step.assert_awaited_once()
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["step"] == "quantity"
    assert patch_kwargs["draft_patch"]["extra"]["ticker"] == "VNM"
    assert patch_kwargs["draft_patch"]["name"] == "VNM"


@pytest.mark.asyncio
async def test_stock_ticker_rejects_garbage():
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "ticker",
            "draft": {"extra": {}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "!!!?", "chat": {"id": 100}, "from": {"id": 100}},
        )
    update_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_stock_quantity_rejects_non_integer():
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "quantity",
            "draft": {"extra": {"ticker": "VNM"}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "abc", "chat": {"id": 100}, "from": {"id": 100}},
        )
    update_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_stock_quantity_accepts_with_separators():
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "quantity",
            "draft": {"extra": {"ticker": "VNM"}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "1,000", "chat": {"id": 100}, "from": {"id": 100}},
        )
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["draft_patch"]["extra"]["quantity"] == 1000


# -----------------------------------------------------------------
# Crypto flow
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_type_picker_routes_to_crypto_starter():
    user = _user()
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry, "_start_crypto_subtype_pick", AsyncMock()) as starter,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:type:crypto",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    starter.assert_awaited_once()


@pytest.mark.asyncio
async def test_crypto_subtype_bitcoin_advances_to_quantity():
    user = _user(
        {
            "flow": asset_entry.FLOW_CRYPTO,
            "step": "subtype",
            "draft": {"asset_type": "crypto", "extra": {}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:crypto_subtype:bitcoin",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    kwargs = update_step.await_args.kwargs
    assert kwargs["step"] == "quantity"
    assert kwargs["draft_patch"]["name"] == "BTC"
    assert kwargs["draft_patch"]["extra"]["symbol"] == "BTC"


@pytest.mark.asyncio
async def test_crypto_current_price_same_creates_asset():
    user = _user(
        {
            "flow": asset_entry.FLOW_CRYPTO,
            "step": "current_price",
            "draft": {
                "asset_type": "crypto",
                "subtype": "bitcoin",
                "name": "BTC",
                "initial_value": float(Decimal("100000000")),
                "extra": {
                    "symbol": "BTC",
                    "ticker": "BTC",
                    "quantity": 0.05,
                    "avg_price": float(Decimal("2000000000")),
                },
            },
        }
    )
    db = _db(user)
    created = _asset(asset_type="crypto", value=100_000_000)
    created.subtype = "bitcoin"
    created.name = "BTC"
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ) as create_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("100_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:crypto_price:same",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["asset_type"] == "crypto"
    assert kwargs["subtype"] == "bitcoin"
    assert kwargs["name"] == "BTC"
    assert kwargs["initial_value"] == Decimal("100000000.000")
    assert kwargs["current_value"] == Decimal("100000000.000")
    assert kwargs["extra"]["symbol"] == "BTC"


# -----------------------------------------------------------------
# Gold flow
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_type_picker_routes_to_gold_starter():
    user = _user()
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry, "_start_gold_subtype_pick", AsyncMock()) as starter,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:type:gold",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    starter.assert_awaited_once()


@pytest.mark.asyncio
async def test_gold_subtype_pick_advances_to_quantity():
    user = _user(
        {
            "flow": asset_entry.FLOW_GOLD,
            "step": "subtype",
            "draft": {"asset_type": "gold", "extra": {}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:gold_subtype:sjc",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    kwargs = update_step.await_args.kwargs
    assert kwargs["step"] == "quantity"
    assert kwargs["draft_patch"]["subtype"] == "sjc"
    assert kwargs["draft_patch"]["name"] == "Vàng SJC"
    assert kwargs["draft_patch"]["extra"]["symbol"] == "SJC_GOLD"


@pytest.mark.asyncio
async def test_gold_quantity_accepts_chi_and_stores_tael_and_grams():
    user = _user(
        {
            "flow": asset_entry.FLOW_GOLD,
            "step": "quantity",
            "draft": {"asset_type": "gold", "subtype": "sjc", "extra": {}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "5 chỉ", "chat": {"id": 100}, "from": {"id": 100}},
        )
    kwargs = update_step.await_args.kwargs
    assert kwargs["step"] == "avg_price"
    extra = kwargs["draft_patch"]["extra"]
    assert extra["quantity"] == 0.5
    assert extra["tael"] == 0.5
    assert extra["weight_gram"] == 18.75


@pytest.mark.asyncio
async def test_gold_current_price_same_creates_asset():
    user = _user(
        {
            "flow": asset_entry.FLOW_GOLD,
            "step": "current_price",
            "draft": {
                "asset_type": "gold",
                "subtype": "sjc",
                "name": "Vàng SJC",
                "initial_value": float(Decimal("180000000")),
                "extra": {
                    "type": "SJC",
                    "symbol": "SJC_GOLD",
                    "quantity": 2.0,
                    "tael": 2.0,
                    "weight_gram": 75.0,
                    "avg_price": float(Decimal("90000000")),
                },
            },
        }
    )
    db = _db(user)
    created = _asset(asset_type="gold", value=180_000_000)
    created.subtype = "sjc"
    created.name = "Vàng SJC"
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ) as create_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("180000000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:gold_price:same",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    create_mock.assert_awaited_once()
    kwargs = create_mock.await_args.kwargs
    assert kwargs["asset_type"] == "gold"
    assert kwargs["subtype"] == "sjc"
    assert kwargs["name"] == "Vàng SJC"
    assert kwargs["initial_value"] == Decimal("180000000.0")
    assert kwargs["current_value"] == Decimal("180000000.0")
    assert kwargs["extra"]["symbol"] == "SJC_GOLD"


# -----------------------------------------------------------------
# Real estate flow
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_subtype_pick_seeds_usd_currency_for_foreign_stock():
    """Picking 'foreign_stock' must seed extra.currency=USD + fx_rate
    so downstream price prompts and the saver know to convert."""
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "subtype",
            "draft": {"asset_type": "stock", "extra": {}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry._handle_stock_subtype_pick(
            db,
            100,
            user,
            "foreign_stock",
        )
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["draft_patch"]["subtype"] == "foreign_stock"
    extra = patch_kwargs["draft_patch"]["extra"]
    assert extra["currency"] == "USD"
    assert extra["fx_rate_vnd"] == float(asset_entry.USD_VND_RATE)


@pytest.mark.asyncio
async def test_stock_subtype_pick_no_currency_for_vn_stock():
    """vn_stock must NOT get a currency tag — the saver branches on it."""
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "subtype",
            "draft": {"asset_type": "stock", "extra": {}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry._handle_stock_subtype_pick(
            db,
            100,
            user,
            "vn_stock",
        )
    extra = update_step.await_args.kwargs["draft_patch"]["extra"]
    assert "currency" not in extra
    assert extra.get("exchange") == "HOSE"


@pytest.mark.asyncio
async def test_fund_quantity_prompt_uses_chung_chi_quy():
    """Fund subtype must prompt with 'chứng chỉ quỹ', not 'cổ phiếu'."""
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "quantity",
            "draft": {
                "asset_type": "stock",
                "subtype": "fund",
                "extra": {"ticker": "VESAF"},
            },
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry.wizard_service, "update_step", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "avg_price",
            "draft": {
                "asset_type": "stock",
                "subtype": "fund",
                "extra": {"ticker": "VESAF", "quantity": 100},
            },
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry.wizard_service, "update_step", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "avg_price",
            "draft": {
                "asset_type": "stock",
                "subtype": "foreign_stock",
                "extra": {
                    "ticker": "AAPL",
                    "quantity": 10,
                    "currency": "USD",
                    "fx_rate_vnd": float(asset_entry.USD_VND_RATE),
                },
            },
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    user = _user(
        {
            "flow": asset_entry.FLOW_STOCK,
            "step": "avg_price",
            "draft": {
                "asset_type": "stock",
                "subtype": "foreign_stock",
                "extra": {"ticker": "AAPL", "quantity": 10, "currency": "USD"},
            },
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    user = _user(
        {
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
        }
    )
    db = _db(user)
    created = _asset(
        asset_type="stock", value=int(Decimal("165") * asset_entry.USD_VND_RATE * 10)
    )
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ) as create_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("100_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry.wizard_service, "update_step", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        # Simulate the user picking "Nhập giá hiện tại" and typing "165".
        draft = user.wizard_state["draft"]
        await asset_entry._handle_stock_current_price_input(
            db,
            100,
            user,
            "165",
            draft,
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
    user = _user(
        {
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
        }
    )
    db = _db(user)
    created = _asset(asset_type="stock")
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ) as create_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("100_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
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
    user = _user(
        {
            "flow": asset_entry.FLOW_REAL_ESTATE,
            "step": "initial_value",
            "draft": {
                "asset_type": "real_estate",
                "subtype": "house_primary",
                "name": "Nhà Mỹ Đình",
                "extra": {},
            },
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.wizard_service, "update_step", AsyncMock()
        ) as update_step,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "2 tỷ", "chat": {"id": 100}, "from": {"id": 100}},
        )
    patch_kwargs = update_step.await_args.kwargs
    assert patch_kwargs["draft_patch"]["initial_value"] == float(
        Decimal("2_000_000_000")
    )
    assert patch_kwargs["step"] == "current_value"


@pytest.mark.asyncio
async def test_real_estate_current_value_advances_to_rental_ask():
    """Phase 3.8 changed real-estate flow: current_value step no
    longer creates the asset directly. It stashes both values into
    the draft and prompts the rental Y/N keyboard. Asset creation
    happens later in either ``_save_real_estate_no_rental`` (No
    branch) or ``_commit_rental`` (Yes branch).
    """
    user = _user(
        {
            "flow": asset_entry.FLOW_REAL_ESTATE,
            "step": "current_value",
            "draft": {
                "asset_type": "real_estate",
                "subtype": "house_primary",
                "name": "Nhà Mỹ Đình",
                "initial_value": float(Decimal("2_000_000_000")),
                "extra": {},
            },
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock()
        ) as create_mock,
        patch.object(asset_entry.wizard_service, "update_step", AsyncMock()) as advance,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "2.5 tỷ", "chat": {"id": 100}, "from": {"id": 100}},
        )
    # No asset should have been created yet — wizard pivots to ask.
    create_mock.assert_not_awaited()
    advance.assert_awaited_once()
    advance_kwargs = advance.await_args.kwargs
    assert advance_kwargs["step"] == "rental_ask"
    assert advance_kwargs["draft_patch"]["initial_value"] == float(
        Decimal("2_000_000_000")
    )
    assert advance_kwargs["draft_patch"]["current_value"] == float(
        Decimal("2_500_000_000")
    )
    # Confirmation message should mention rental Y/N.
    send.assert_called()
    sent_text = send.call_args.kwargs["text"]
    assert "BĐS cho thuê" in sent_text


@pytest.mark.asyncio
async def test_real_estate_rental_ask_no_creates_asset_no_rental():
    """User taps 'No' on the rental prompt → asset created without
    rental_metadata, and ``rental_service.mark_as_rental`` is NOT
    called.
    """
    user = _user(
        {
            "flow": asset_entry.FLOW_REAL_ESTATE,
            "step": "rental_ask",
            "draft": {
                "asset_type": "real_estate",
                "subtype": "house_primary",
                "name": "Nhà Mỹ Đình",
                "initial_value": float(Decimal("2_000_000_000")),
                "current_value": float(Decimal("2_500_000_000")),
                "extra": {},
            },
        }
    )
    db = _db(user)
    created = _asset(asset_type="real_estate", value=2_500_000_000)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ) as create_mock,
        patch.object(
            asset_entry.rental_service, "mark_as_rental", AsyncMock()
        ) as mark_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("2_500_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:rental_ask:no",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    create_mock.assert_awaited_once()
    mark_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_estate_rental_full_flow_marks_with_metadata():
    """Yes → rent → expenses → status:rented → done.

    Asserts the final ``_commit_rental`` call goes through and
    ``mark_as_rental`` receives a validated metadata bundle with
    rent=15tr, expenses=1.5tr, status=rented.
    """
    # We test the final step (rental_extra:done) which collapses all
    # the previously-collected draft into a save action.
    user = _user(
        {
            "flow": asset_entry.FLOW_REAL_ESTATE,
            "step": "rental_extra",
            "draft": {
                "asset_type": "real_estate",
                "subtype": "house_primary",
                "name": "Nhà Mỹ Đình",
                "initial_value": float(Decimal("2_500_000_000")),
                "current_value": float(Decimal("2_500_000_000")),
                "extra": {},
                "rental": {
                    "monthly_rent": float(Decimal("15000000")),
                    "monthly_expenses": float(Decimal("1500000")),
                    "occupancy_status": "rented",
                },
            },
        }
    )
    db = _db(user)
    created = _asset(asset_type="real_estate", value=2_500_000_000)
    marked = _asset(asset_type="real_estate", value=2_500_000_000)
    marked.is_rental = True
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ),
        patch.object(
            asset_entry.rental_service, "mark_as_rental", AsyncMock(return_value=marked)
        ) as mark_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("2_500_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:rental_extra:done",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    mark_mock.assert_awaited_once()
    metadata_arg = mark_mock.await_args.args[3]
    assert metadata_arg.monthly_rent == Decimal("15000000")
    assert metadata_arg.monthly_expenses == Decimal("1500000")
    assert metadata_arg.occupancy_status == "rented"


@pytest.mark.asyncio
async def test_real_estate_rental_status_vacant_skips_extras():
    """Status=vacant → no tenant/lease prompts, save immediately."""
    user = _user(
        {
            "flow": asset_entry.FLOW_REAL_ESTATE,
            "step": "rental_status",
            "draft": {
                "asset_type": "real_estate",
                "subtype": "house_primary",
                "name": "Nhà Trống",
                "initial_value": float(Decimal("3_000_000_000")),
                "current_value": float(Decimal("3_000_000_000")),
                "extra": {},
                "rental": {
                    "monthly_rent": float(Decimal("20000000")),
                    "monthly_expenses": float(Decimal("2000000")),
                },
            },
        }
    )
    db = _db(user)
    created = _asset(asset_type="real_estate", value=3_000_000_000)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "create_asset", AsyncMock(return_value=created)
        ),
        patch.object(
            asset_entry.rental_service,
            "mark_as_rental",
            AsyncMock(return_value=created),
        ) as mark_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("3_000_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "wizard_service", asset_entry.wizard_service),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:rental_status:vacant",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    mark_mock.assert_awaited_once()
    metadata_arg = mark_mock.await_args.args[3]
    assert metadata_arg.occupancy_status == "vacant"


@pytest.mark.asyncio
async def test_rental_rent_input_negative_rejected():
    """Negative rent is rejected with a friendly nudge; wizard stays
    at the rental_rent step (no advance, no save)."""
    user = _user(
        {
            "flow": asset_entry.FLOW_REAL_ESTATE,
            "step": "rental_rent",
            "draft": {"rental": {}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry.wizard_service, "update_step", AsyncMock()) as advance,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "-15tr", "chat": {"id": 100}, "from": {"id": 100}},
        )
    advance.assert_not_awaited()
    send.assert_called()


@pytest.mark.asyncio
async def test_rental_expenses_zero_keyword_accepted():
    """User types '0' for expenses → wizard advances to status step
    with monthly_expenses=0."""
    user = _user(
        {
            "flow": asset_entry.FLOW_REAL_ESTATE,
            "step": "rental_expenses",
            "draft": {"rental": {"monthly_rent": float(Decimal("15000000"))}},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry.wizard_service, "update_step", AsyncMock()) as advance,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        await asset_entry.handle_asset_text_input(
            db,
            {"text": "0", "chat": {"id": 100}, "from": {"id": 100}},
        )
    advance.assert_awaited_once()
    kwargs = advance.await_args.kwargs
    assert kwargs["step"] == "rental_status"
    assert kwargs["draft_patch"]["rental"]["monthly_expenses"] == 0.0


@pytest.mark.asyncio
async def test_mark_rental_pick_starts_subwizard():
    """Picking an existing real-estate asset from the menu starts
    FLOW_MARK_RENTAL at the rental_rent step with mode=mark_existing.
    """
    user = _user()
    db = _db(user)
    re_asset = _asset(asset_type="real_estate", value=2_500_000_000)
    re_asset.is_rental = False
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service,
            "get_asset_by_id",
            AsyncMock(return_value=re_asset),
        ),
        patch.object(
            asset_entry.wizard_service, "start_flow", AsyncMock()
        ) as start_flow,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
        consumed = await asset_entry.handle_asset_rental_callback(
            db,
            {
                "id": "cb1",
                "data": f"asset_rental:pick:{re_asset.id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    assert consumed is True
    start_flow.assert_awaited_once()
    args, kwargs = start_flow.await_args.args, start_flow.await_args.kwargs
    # Handler calls start_flow(db, user_id, FLOW, step=..., draft=...).
    assert args[2] == asset_entry.FLOW_MARK_RENTAL
    assert kwargs["step"] == "rental_rent"
    assert kwargs["draft"]["mode"] == "mark_existing"
    assert kwargs["draft"]["target_asset_id"] == str(re_asset.id)


@pytest.mark.asyncio
async def test_mark_existing_rental_does_not_expose_undo_button():
    """Codex P1 (PR #225): the mark-existing flow used to call
    ``_post_save`` which renders ``add_more_keyboard(undo_asset_id=...)``
    — and that undo callback HARD-DELETES the referenced asset. For a
    pre-existing real-estate row, tapping undo would silently destroy
    actual financial state. The fix routes mark-existing through
    ``_post_mark_existing`` instead, which never offers an undo
    button.
    """
    user = _user(
        {
            "flow": asset_entry.FLOW_MARK_RENTAL,
            "step": "rental_extra",
            "draft": {
                "mode": "mark_existing",
                "target_asset_id": str(uuid.uuid4()),
                "rental": {
                    "monthly_rent": float(Decimal("15000000")),
                    "monthly_expenses": float(Decimal("1500000")),
                    "occupancy_status": "rented",
                },
            },
        }
    )
    db = _db(user)
    marked = _asset(asset_type="real_estate", value=2_500_000_000)
    marked.is_rental = True
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.rental_service, "mark_as_rental", AsyncMock(return_value=marked)
        ),
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("2_500_000_000"),
                    asset_count=1,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "_mark_onboarding_first_asset_done", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        await asset_entry.handle_asset_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_add:rental_extra:done",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    # Inspect every send_message: none of them should attach a
    # reply_markup that contains an "asset_add:undo:*" callback.
    for call in send.call_args_list:
        markup = call.kwargs.get("reply_markup") or {}
        for row in markup.get("inline_keyboard", []):
            for btn in row:
                cb = btn.get("callback_data", "")
                assert (
                    "undo" not in cb
                ), f"mark_existing flow leaked undo button: {cb!r}"


@pytest.mark.asyncio
async def test_mark_rental_pick_already_rental_rejected():
    """Picking an asset that's already a rental shows a friendly
    "already marked" message and does NOT start a wizard.
    """
    user = _user()
    db = _db(user)
    re_asset = _asset(asset_type="real_estate", value=2_500_000_000)
    re_asset.is_rental = True
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service,
            "get_asset_by_id",
            AsyncMock(return_value=re_asset),
        ),
        patch.object(
            asset_entry.wizard_service, "start_flow", AsyncMock()
        ) as start_flow,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        await asset_entry.handle_asset_rental_callback(
            db,
            {
                "id": "cb1",
                "data": f"asset_rental:pick:{re_asset.id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )
    start_flow.assert_not_awaited()
    send.assert_called()


# -----------------------------------------------------------------
# Callback dispatch
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_cancel_clears_state():
    user = _user({"flow": "asset_add_cash", "step": "amount", "draft": {}})
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
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
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry, "_start_cash_subtype_pick", AsyncMock()) as starter,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
    ):
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

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_asset_by_id", AsyncMock(return_value=asset)
        ),
        patch.object(
            asset_entry.asset_service, "hard_delete", AsyncMock(return_value=True)
        ) as delete_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate",
            AsyncMock(
                return_value=MagicMock(
                    total=Decimal("0"),
                    asset_count=0,
                )
            ),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "hard_delete", AsyncMock()
        ) as delete_mock,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_asset_by_id", AsyncMock(return_value=None)
        ),
        patch.object(
            asset_entry.asset_service, "hard_delete", AsyncMock(return_value=False)
        ) as delete_mock,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    with patch.object(
        asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ):
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
    with patch.object(
        asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
    ):
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
    user = _user(
        {
            "flow": asset_entry.FLOW_PICKER,
            "step": "type",
            "draft": {},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear,
    ):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB-002 20 triệu", "chat": {"id": 100}, "from": {"id": 100}},
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
    user = _user(
        {
            "flow": asset_entry.FLOW_CASH,
            "step": "subtype",
            "draft": {"asset_type": "cash"},
        }
    )
    db = _db(user)
    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "VCB-002 20 triệu", "chat": {"id": 100}, "from": {"id": 100}},
        )
    assert consumed is True
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_asset_wizard_sets_picker_state():
    """After starting the wizard, wizard_state must be the picker
    sentinel — NOT null. That's what closes the leak window."""
    user = _user(state={"flow": "asset_add_cash", "step": "amount", "draft": {}})
    db = _db(user)
    with (
        patch.object(
            asset_entry.wizard_service, "start_flow", AsyncMock()
        ) as start_flow,
        patch.object(asset_entry, "send_message", AsyncMock()),
    ):
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
    user = _user(
        {
            "flow": asset_entry.FLOW_CASH,
            "step": "amount",
            "draft": {"asset_type": "cash"},
        }
    )
    db = _db(user)
    with (
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
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
    with (
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        cancelled = await asset_entry.cancel_wizard(db, 100, user)
    assert cancelled is False
    clear.assert_not_awaited()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_asset_manage_delete_flow_filters_by_type_then_soft_deletes():
    user = _user()
    db = _db(user)
    stock = _asset(asset_type="stock", value=120_000_000)
    stock.name = "VCB"
    stock.subtype = "vn_stock"

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service,
            "get_user_assets",
            AsyncMock(return_value=[stock]),
        ) as list_mock,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_asset_manage_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_manage:delete_type:stock",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )

    assert consumed is True
    list_mock.assert_awaited_once_with(db, user.id, asset_type="stock")
    reply_markup = send.await_args.kwargs["reply_markup"]
    callbacks = [
        button["callback_data"]
        for row in reply_markup["inline_keyboard"]
        for button in row
    ]
    assert f"asset_manage:delete_confirm:{stock.id}" in callbacks

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_asset_by_id", AsyncMock(return_value=stock)
        ),
        patch.object(
            asset_entry.asset_service, "soft_delete", AsyncMock(return_value=stock)
        ) as delete_mock,
        patch.object(
            asset_entry.asset_service,
            "get_user_assets",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            asset_entry.rental_service,
            "pause_streams_for_asset",
            AsyncMock(return_value=False),
        ) as pause_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate_stored_current",
            AsyncMock(return_value=MagicMock(total=Decimal("0"))),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_asset_manage_callback(
            db,
            {
                "id": "cb2",
                "data": f"asset_manage:delete:{stock.id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )

    assert consumed is True
    delete_mock.assert_awaited_once_with(db, user.id, stock.id)
    pause_mock.assert_awaited_once_with(db, user.id, stock.id)
    success_text = send.await_args_list[0].kwargs["text"]
    assert "Đã xoá" in success_text
    assert "Dòng tiền" in success_text
    assert "Dòng thuê" not in success_text  # non-rental → no rental note


@pytest.mark.asyncio
async def test_asset_manage_delete_rental_pauses_income_stream():
    """A rental real-estate asset deletion must also pause its linked
    income stream — otherwise cash-flow forecaster keeps crediting rent
    from a property the user just removed.
    """
    user = _user()
    db = _db(user)
    house = _asset(asset_type="real_estate", value=2_500_000_000)
    house.name = "Nhà Oceanpark"
    house.subtype = "house"
    house.is_rental = True

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_asset_by_id", AsyncMock(return_value=house)
        ),
        patch.object(
            asset_entry.asset_service, "soft_delete", AsyncMock(return_value=house)
        ),
        patch.object(
            asset_entry.asset_service,
            "get_user_assets",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            asset_entry.rental_service,
            "pause_streams_for_asset",
            AsyncMock(return_value=True),  # rental stream existed and was paused
        ) as pause_mock,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate_stored_current",
            AsyncMock(return_value=MagicMock(total=Decimal("0"))),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_asset_manage_callback(
            db,
            {
                "id": "cb_rental_delete",
                "data": f"asset_manage:delete:{house.id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )

    assert consumed is True
    pause_mock.assert_awaited_once_with(db, user.id, house.id)
    success_text = send.await_args_list[0].kwargs["text"]
    assert "Đã xoá" in success_text
    assert "Dòng thuê" in success_text  # user told rental income paused


@pytest.mark.asyncio
async def test_asset_manage_delete_confirm_uses_decisive_wording():
    """The confirmation dialog must NOT use the old 'ẩn... không xoá lịch sử'
    copy that confused users into thinking the action is fake. It must
    state plainly that the asset will disappear and totals will recalc.
    """
    user = _user()
    db = _db(user)
    house = _asset(asset_type="real_estate", value=2_500_000_000)
    house.name = "Nhà Oceanpark"
    house.subtype = "house"
    house.is_rental = True

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_asset_by_id", AsyncMock(return_value=house)
        ),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        await asset_entry.handle_asset_manage_callback(
            db,
            {
                "id": "cb_confirm",
                "data": f"asset_manage:delete_confirm:{house.id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )

    text = send.await_args.kwargs["text"]
    # Decisive wording: tells user the asset will be removed + totals recalc.
    assert "biến mất khỏi danh mục" in text
    assert "tính lại" in text
    # Rental warning surfaced for is_rental=True.
    assert "thuê hàng tháng" in text
    # Confusing legacy copy must be gone.
    assert "ẩn tài sản" not in text
    assert "không xoá lịch sử" not in text


@pytest.mark.asyncio
async def test_asset_manage_delete_stale_button_re_renders_list():
    """If the user taps a delete_confirm button on a stale list message
    (asset already gone), we should re-render a fresh list instead of
    leaving them with a dead-end 'không còn trong danh sách' message.
    """
    user = _user()
    db = _db(user)
    gone = _asset(asset_type="stock", value=120_000_000)
    gone.is_active = False  # already soft-deleted

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_asset_by_id", AsyncMock(return_value=gone)
        ),
        patch.object(
            asset_entry.asset_service,
            "get_user_assets",
            AsyncMock(return_value=[]),
        ) as list_mock,
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        await asset_entry.handle_asset_manage_callback(
            db,
            {
                "id": "cb_stale",
                "data": f"asset_manage:delete_confirm:{gone.id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )

    # Two messages: the friendly recovery + the fresh list (here: empty state).
    assert send.await_count == 2
    list_mock.assert_awaited_once_with(db, user.id, asset_type="stock")


@pytest.mark.asyncio
async def test_asset_manage_delete_empty_type_shows_empty_state():
    user = _user()
    db = _db(user)

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_user_assets", AsyncMock(return_value=[])
        ),
        patch.object(asset_entry, "answer_callback", AsyncMock()),
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_asset_manage_callback(
            db,
            {
                "id": "cb1",
                "data": "asset_manage:delete_type:crypto",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )

    assert consumed is True
    assert "Không có tài sản loại Tiền số" in send.await_args.kwargs["text"]


# -----------------------------------------------------------------
# Phase 3.9.5 dashboard edit flow
# -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_edit_callback_starts_ownership_checked_edit_wizard():
    user = _user()
    db = _db(user)
    asset = _asset()
    asset.user_id = user.id

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service, "get_asset_by_id", AsyncMock(return_value=asset)
        ) as get_asset,
        patch.object(asset_entry.wizard_service, "start_flow", AsyncMock()) as start,
        patch.object(asset_entry, "answer_callback", AsyncMock()) as answer,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_dashboard_callback(
            db,
            {
                "id": "cb1",
                "data": f"dashboard:edit:{asset.id}",
                "message": {"chat": {"id": 100}, "message_id": 1},
                "from": {"id": 100},
            },
        )

    assert consumed is True
    answer.assert_awaited_once_with("cb1")
    get_asset.assert_awaited_once_with(db, user.id, asset.id)
    start.assert_awaited_once()
    assert start.await_args.args[:4] == (db, user.id, asset_entry.FLOW_EDIT_ASSET)
    assert start.await_args.kwargs["step"] == "current_value"
    assert start.await_args.kwargs["draft"]["asset_id"] == str(asset.id)
    assert "Giá trị hiện tại" in send.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_dashboard_edit_text_updates_value_and_refreshes_report():
    asset = _asset(value=100_000_000)
    user = _user(
        {
            "flow": asset_entry.FLOW_EDIT_ASSET,
            "step": "current_value",
            "draft": {"asset_id": str(asset.id), "return_to_dashboard": True},
        }
    )
    db = _db(user)
    updated = _asset(value=120_000_000)
    updated.id = asset.id
    updated.user_id = user.id

    with (
        patch.object(
            asset_entry, "get_user_by_telegram_id", AsyncMock(return_value=user)
        ),
        patch.object(
            asset_entry.asset_service,
            "update_current_value",
            AsyncMock(return_value=updated),
        ) as update_value,
        patch.object(
            asset_entry.net_worth_calculator,
            "calculate_stored_current",
            AsyncMock(return_value=MagicMock(total=Decimal("120000000"))),
        ),
        patch.object(asset_entry, "update_user_level", AsyncMock(return_value=None)),
        patch.object(asset_entry.wizard_service, "clear", AsyncMock()) as clear,
        patch.object(asset_entry, "show_asset_dashboard_report", AsyncMock()) as report,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        consumed = await asset_entry.handle_asset_text_input(
            db,
            {"text": "120 triệu", "chat": {"id": 100}, "from": {"id": 100}},
        )

    assert consumed is True
    update_value.assert_awaited_once_with(db, user.id, asset.id, Decimal("120000000"))
    clear.assert_awaited_once_with(db, user.id)
    assert "Đã cập nhật" in send.await_args.kwargs["text"]
    report.assert_awaited_once_with(db, 100, user)


@pytest.mark.asyncio
async def test_grouped_dashboard_picker_uses_one_user_scoped_asset_query():
    user = _user()
    db = _db(user)
    first = _asset(value=10_000_000)
    second = _asset(value=20_000_000)
    first.user_id = second.user_id = user.id

    with (
        patch.object(
            asset_entry.asset_service,
            "get_user_assets",
            AsyncMock(return_value=[first, second]),
        ) as get_assets,
        patch.object(asset_entry, "send_message", AsyncMock()) as send,
    ):
        await asset_entry.show_asset_edit_picker(
            db, 100, user, [str(first.id), str(second.id)]
        )

    get_assets.assert_awaited_once_with(db, user.id)
    callbacks = [
        button["callback_data"]
        for row in send.await_args.kwargs["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert f"asset:edit:{first.id}" in callbacks
    assert f"asset:edit:{second.id}" in callbacks
