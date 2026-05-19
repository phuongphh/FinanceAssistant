from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.intent.handlers.action_delete_asset import ActionDeleteAssetHandler
from backend.intent.intents import IntentResult, IntentType


def _user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.telegram_id = 12345
    return u


@pytest.mark.asyncio
async def test_delete_asset_scopes_list_by_subtype_when_no_name_match():
    intent = IntentResult(
        intent=IntentType.ACTION_DELETE_ASSET,
        confidence=0.95,
        raw_text="xóa tài sản quỹ",
        parameters={"asset_type": "stock", "asset_subtype": "fund"},
    )

    with (
        patch(
            "backend.intent.handlers.action_delete_asset.asset_entry_handlers.show_asset_delete_list",
            AsyncMock(),
        ) as show_list,
        patch(
            "backend.intent.handlers.action_delete_asset.asset_entry_handlers.show_asset_delete_type_picker",
            AsyncMock(),
        ) as show_type_picker,
    ):
        out = await ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    show_list.assert_awaited_once()
    _, _, _, asset_type = show_list.await_args.args
    assert asset_type == "stock"
    assert show_list.await_args.kwargs["subtype"] == "fund"
    show_type_picker.assert_not_called()


@pytest.mark.asyncio
async def test_delete_asset_name_match_respects_subtype():
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

    with (
        patch(
            "backend.intent.handlers.action_delete_asset.asset_service.get_user_assets",
            AsyncMock(return_value=[fund, stock]),
        ),
        patch(
            "backend.intent.handlers.action_delete_asset.asset_entry_handlers._confirm_asset_delete",
            AsyncMock(),
        ) as confirm,
        patch(
            "backend.intent.handlers.action_delete_asset.asset_entry_handlers.show_asset_delete_list",
            AsyncMock(),
        ) as show_list,
    ):
        out = await ActionDeleteAssetHandler().handle(intent, _user(), MagicMock())

    assert out == ""
    confirm.assert_awaited_once()
    called_asset_id = confirm.await_args.args[3]
    assert called_asset_id == str(fund.id)
    show_list.assert_not_called()
