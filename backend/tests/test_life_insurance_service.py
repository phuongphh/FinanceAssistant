import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.wealth.services import life_insurance_service as svc


@pytest.mark.asyncio
async def test_create_autocalculates_total_paid(monkeypatch):
    created = {}

    async def fake_create_asset(*args, **kwargs):
        created.update(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), extra=kwargs.get("extra"))

    monkeypatch.setattr("backend.wealth.services.life_insurance_service.asset_service.create_asset", fake_create_asset)
    d = date(2026, 1, 1)
    await svc.create_life_insurance(AsyncMock(), uuid.uuid4(), company_name="AIA", monthly_payment_date=15, monthly_amount=Decimal("1000000"), contract_end_year=2035, start_date=d)
    assert created["asset_type"] == "life_insurance"
    assert created["extra"]["company_name"] == "AIA"
    assert created["extra"]["total_paid"] > 0


@pytest.mark.asyncio
async def test_update_and_delete(monkeypatch):
    fake = SimpleNamespace(id=uuid.uuid4(), asset_type="life_insurance", name="Old", extra={}, current_value=Decimal("1"), initial_value=Decimal("1"))
    db = AsyncMock()
    monkeypatch.setattr(svc, "get_life_insurance_by_id", AsyncMock(return_value=fake))
    out = await svc.update_life_insurance(db, uuid.uuid4(), fake.id, company_name="Manulife", total_paid=Decimal("2000000"))
    assert out.name == "Manulife"
    assert out.current_value == Decimal("2000000")
    monkeypatch.setattr("backend.wealth.services.life_insurance_service.asset_service.soft_delete", AsyncMock(return_value=fake))
    deleted = await svc.delete_life_insurance(db, uuid.uuid4(), fake.id)
    assert deleted is fake
