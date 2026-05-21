from decimal import Decimal
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_assets_submenu_has_life_insurance_button():
    from backend.bot.formatters.menu_formatter import format_submenu

    _, kb = format_submenu(None, "assets", level="young_prof")
    callbacks = [row[0]["callback_data"] for row in kb["inline_keyboard"]]
    assert "menu:assets:life_insurance" in callbacks


@pytest.mark.asyncio
async def test_life_insurance_empty_state(monkeypatch):
    from backend.bot.handlers import menu_handler

    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(menu_handler, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.wealth.services.life_insurance_service.get_life_insurance_list", 
        AsyncMock(return_value=[])
    )

    await menu_handler._action_assets_life_insurance(db=None, user=SimpleNamespace(id=1), chat_id=1, message_id=None)
    assert "Chưa có hợp đồng" in sent["text"]


@pytest.mark.asyncio
async def test_life_insurance_list_renders(monkeypatch):
    from backend.bot.handlers import menu_handler

    sent = {}

    async def fake_send_message(**kwargs):
        sent.update(kwargs)

    item = SimpleNamespace(name="AIA", extra={"company_name":"AIA", "monthly_payment_date":10, "monthly_amount":1000000, "contract_end_year":2035, "total_paid":5000000}, current_value=Decimal("5000000"))
    monkeypatch.setattr(menu_handler, "send_message", fake_send_message)
    monkeypatch.setattr(
        "backend.wealth.services.life_insurance_service.get_life_insurance_list", 
        AsyncMock(return_value=[item])
    )
    await menu_handler._action_assets_life_insurance(db=None, user=SimpleNamespace(id=1), chat_id=1, message_id=None)
    assert "Tổng BHNT" in sent["text"]
    assert "AIA" in sent["text"]
