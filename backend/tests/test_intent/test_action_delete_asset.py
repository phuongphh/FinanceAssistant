from __future__ import annotations

import sys
import uuid
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.intents import IntentResult, IntentType

# Import isolation: prevent this unit test from dragging heavy optional
# dependencies via backend.bot.handlers.asset_entry -> twin stack.
_fake_asset_entry = ModuleType("backend.bot.handlers.asset_entry")
_fake_asset_entry.show_asset_delete_list = AsyncMock()
_fake_asset_entry.show_asset_delete_type_picker = AsyncMock()
_fake_asset_entry._confirm_asset_delete = AsyncMock()

with patch.dict(sys.modules, {"backend.bot.handlers.asset_entry": _fake_asset_entry}):
    from backend.intent.handlers.action_delete_asset import ActionDeleteAssetHandler
    import backend.intent.handlers.action_delete_asset as delete_mod


def _user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.telegram_id = 12345
    return u


def _reset_mocks() -> None:
    delete_mod.asset_entry_handlers.show_asset_delete_list.reset_mock()
    delete_mod.asset_entry_handlers.show_asset_delete_type_picker.reset_mock()
    delete_mod.asset_entry_handlers._confirm_asset_delete.reset_mock()


@pytest.mark.asyncio
async def test_delete_asset_scopes_list_by_subtype_when_no_name_match():
    _reset_mocks()
    intent = IntentResult(
        intent=IntentType.ACTION_DELETE_ASSET,
        confidence=0.95,
        raw_text="xóa tài sản quỹ",
        parameters={"asset_type": "stock", "asset_subtype": "fund"},
    )

    out = await ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    delete_mod.asset_entry_handlers.show_asset_delete_list.assert_awaited_once()
    _, _, _, asset_type = delete_mod.asset_entry_handlers.show_asset_delete_list.await_args.args
    assert asset_type == "stock"
    assert delete_mod.asset_entry_handlers.show_asset_delete_list.await_args.kwargs["subtype"] == "fund"
    delete_mod.asset_entry_handlers.show_asset_delete_type_picker.assert_not_called()


@pytest.mark.asyncio
async def test_delete_asset_name_match_respects_subtype():
    _reset_mocks()
    intent = IntentResult(
        intent=IntentType.ACTION_DELETE_ASSET,
        confidence=0.95,
        raw_text="xóa tài sản tcef",
        parameters={"asset_type": "stock", "asset_subtype": "fund", "asset_name": "tcef"},
    )
    fund = SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        name="TCEF",
        asset_type="stock",
        subtype="fund",
    )
    stock = SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        name="TCEF",
        asset_type="stock",
        subtype="vn_stock",
    )

    with patch.object(delete_mod.asset_service, "get_user_assets", AsyncMock(return_value=[fund, stock])):
        out = await ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    delete_mod.asset_entry_handlers._confirm_asset_delete.assert_awaited_once()
    called_asset_id = delete_mod.asset_entry_handlers._confirm_asset_delete.await_args.args[3]
    assert called_asset_id == str(fund.id)
    delete_mod.asset_entry_handlers.show_asset_delete_list.assert_not_called()


@pytest.mark.asyncio
async def test_delete_asset_matches_ticker_in_extra():
    _reset_mocks()
    intent = IntentResult(
        intent=IntentType.ACTION_DELETE_ASSET,
        confidence=0.95,
        raw_text="xóa tài sản tcef",
        parameters={"asset_name": "tcef"},
    )
    matched = SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        name="Quỹ trái phiếu dài hạn",
        asset_type="stock",
        subtype="fund",
        extra={"ticker": "TCEF"},
    )

    with patch.object(delete_mod.asset_service, "get_user_assets", AsyncMock(return_value=[matched])):
        out = await ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    delete_mod.asset_entry_handlers._confirm_asset_delete.assert_awaited_once()
    called_asset_id = delete_mod.asset_entry_handlers._confirm_asset_delete.await_args.args[3]
    assert called_asset_id == str(matched.id)
