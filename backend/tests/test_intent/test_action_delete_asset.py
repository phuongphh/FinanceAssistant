from __future__ import annotations

import importlib
import sys
import uuid
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.intents import IntentResult, IntentType


def _user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.telegram_id = 12345
    return u


@pytest.fixture
def delete_handler_module():
    """Import handler with a lightweight fake ``asset_entry`` dependency.

    CI intent suite may run without heavy optional deps (e.g. numpy from Twin
    modules). ``action_delete_asset`` only needs a few async functions from
    ``asset_entry``; stub that module so import stays isolated.
    """
    fake_asset_entry = ModuleType("backend.bot.handlers.asset_entry")
    fake_asset_entry.show_asset_delete_list = AsyncMock()
    fake_asset_entry.show_asset_delete_type_picker = AsyncMock()
    fake_asset_entry._confirm_asset_delete = AsyncMock()

    with patch.dict(sys.modules, {"backend.bot.handlers.asset_entry": fake_asset_entry}):
        mod = importlib.import_module("backend.intent.handlers.action_delete_asset")
        mod = importlib.reload(mod)
        yield mod


@pytest.mark.asyncio
async def test_delete_asset_scopes_list_by_subtype_when_no_name_match(delete_handler_module):
    intent = IntentResult(
        intent=IntentType.ACTION_DELETE_ASSET,
        confidence=0.95,
        raw_text="xóa tài sản quỹ",
        parameters={"asset_type": "stock", "asset_subtype": "fund"},
    )

    out = await delete_handler_module.ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    delete_handler_module.asset_entry_handlers.show_asset_delete_list.assert_awaited_once()
    _, _, _, asset_type = delete_handler_module.asset_entry_handlers.show_asset_delete_list.await_args.args
    assert asset_type == "stock"
    assert (
        delete_handler_module.asset_entry_handlers.show_asset_delete_list.await_args.kwargs["subtype"]
        == "fund"
    )
    delete_handler_module.asset_entry_handlers.show_asset_delete_type_picker.assert_not_called()


@pytest.mark.asyncio
async def test_delete_asset_name_match_respects_subtype(delete_handler_module):
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

    with patch.object(
        delete_handler_module.asset_service,
        "get_user_assets",
        AsyncMock(return_value=[fund, stock]),
    ):
        out = await delete_handler_module.ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    delete_handler_module.asset_entry_handlers._confirm_asset_delete.assert_awaited_once()
    called_asset_id = delete_handler_module.asset_entry_handlers._confirm_asset_delete.await_args.args[3]
    assert called_asset_id == str(fund.id)
    delete_handler_module.asset_entry_handlers.show_asset_delete_list.assert_not_called()


def test_asset_matches_exactly_normalizes_diacritics_and_case(delete_handler_module):
    asset = SimpleNamespace(name="Vàng SJC", extra={})
    assert delete_handler_module._asset_matches_exactly(asset, "vang sjc")
    assert delete_handler_module._asset_matches_exactly(asset, "VANG SJC")
    assert not delete_handler_module._asset_matches_exactly(asset, "vang")


def test_asset_matches_exactly_checks_ticker(delete_handler_module):
    asset = SimpleNamespace(name="Quỹ XYZ", extra={"ticker": "TCEF"})
    assert delete_handler_module._asset_matches_exactly(asset, "tcef")
    assert not delete_handler_module._asset_matches_exactly(asset, "tce")


def test_asset_matches_exactly_empty_query(delete_handler_module):
    asset = SimpleNamespace(name="TCEF", extra={})
    assert not delete_handler_module._asset_matches_exactly(asset, "")
    assert not delete_handler_module._asset_matches_exactly(asset, "   ")


@pytest.mark.asyncio
async def test_delete_asset_exact_match_breaks_substring_tie(delete_handler_module):
    """When ``asset_name`` substring-matches multiple assets but exactly
    matches one (by name or ticker), open the confirm card for that one.
    Fixes "Xóa tài sản TCEF" falling through when "TCEF" also substrings
    a fund named e.g. "TCEF Long".
    """
    intent = IntentResult(
        intent=IntentType.ACTION_DELETE_ASSET,
        confidence=0.95,
        raw_text="xóa tài sản tcef",
        parameters={"asset_name": "tcef"},
    )
    exact = SimpleNamespace(
        id=uuid.uuid4(), is_active=True, name="TCEF", asset_type="stock", subtype="fund",
    )
    substring = SimpleNamespace(
        id=uuid.uuid4(), is_active=True, name="TCEF Long Bond", asset_type="stock", subtype="fund",
    )

    with patch.object(
        delete_handler_module.asset_service,
        "get_user_assets",
        AsyncMock(return_value=[exact, substring]),
    ):
        out = await delete_handler_module.ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    delete_handler_module.asset_entry_handlers._confirm_asset_delete.assert_awaited_once()
    called_asset_id = delete_handler_module.asset_entry_handlers._confirm_asset_delete.await_args.args[3]
    assert called_asset_id == str(exact.id)


@pytest.mark.asyncio
async def test_delete_asset_matches_ticker_in_extra(delete_handler_module):
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

    with patch.object(
        delete_handler_module.asset_service,
        "get_user_assets",
        AsyncMock(return_value=[matched]),
    ):
        out = await delete_handler_module.ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    delete_handler_module.asset_entry_handlers._confirm_asset_delete.assert_awaited_once()
    called_asset_id = delete_handler_module.asset_entry_handlers._confirm_asset_delete.await_args.args[3]
    assert called_asset_id == str(matched.id)
