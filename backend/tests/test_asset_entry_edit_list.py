from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.bot.handlers import asset_entry


@pytest.mark.asyncio
async def test_show_asset_edit_list_filters_by_subtype():
    user = SimpleNamespace(id=uuid.uuid4(), settings={})
    db = object()
    chat_id = 123

    fund = SimpleNamespace(
        id=uuid.uuid4(),
        name="TCEF",
        current_value=Decimal("1000000"),
        asset_type="stock",
        subtype="fund",
        extra={"ticker": "TCEF"},
    )
    stock = SimpleNamespace(
        id=uuid.uuid4(),
        name="FPT",
        current_value=Decimal("2000000"),
        asset_type="stock",
        subtype="vn_stock",
        extra={"ticker": "FPT"},
    )

    with patch.object(asset_entry.asset_service, "get_user_assets", AsyncMock(return_value=[fund, stock])), \
         patch.object(asset_entry, "_sort_assets_for_dashboard", return_value=[fund, stock]), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send_message:
        await asset_entry.show_asset_edit_list(db, chat_id, user, "stock", subtype="fund")

    markup = send_message.await_args.kwargs["reply_markup"]
    # Each asset renders as a single row: ✏️ / 🗑 action icons then the content
    # label (asset_manage:noop), so read the label off the no-op button.
    labels = [
        b["text"]
        for row in markup["inline_keyboard"]
        for b in row
        if b.get("callback_data") == "asset_manage:noop"
    ]
    assert len(labels) == 1
    assert "TCEF" in labels[0]
    # The subtype filter must keep the edit action wired to the fund only.
    edit_cbs = [
        b["callback_data"]
        for row in markup["inline_keyboard"]
        for b in row
        if b.get("callback_data", "").startswith("asset_manage:edit:")
    ]
    assert len(edit_cbs) == 1


@pytest.mark.asyncio
async def test_show_asset_edit_list_without_subtype_does_not_crash():
    user = SimpleNamespace(id=uuid.uuid4(), settings={})
    db = object()

    asset = SimpleNamespace(
        id=uuid.uuid4(),
        name="BTC",
        current_value=Decimal("3000000"),
        asset_type="crypto",
        subtype="",
        extra={"symbol": "BTC"},
    )

    with patch.object(asset_entry.asset_service, "get_user_assets", AsyncMock(return_value=[asset])), \
         patch.object(asset_entry, "_sort_assets_for_dashboard", return_value=[asset]), \
         patch.object(asset_entry, "send_message", AsyncMock()) as send_message:
        await asset_entry.show_asset_edit_list(db, 456, user, "crypto")

    assert send_message.await_count == 1
