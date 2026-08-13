from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.market_data.analytics import alerts as alerts_module
from backend.market_data.analytics.alerts import (
    check_movements,
    format_alert_message,
    severity_for_change,
)
from backend.market_data.cache.price_cache import PriceCache
from backend.market_data.normalizer import SNAPSHOT_SOURCE, PriceQuote
from backend.tests.test_market_data.fakes import FakeAsyncRedis


def test_severity_for_change_thresholds():
    assert severity_for_change(Decimal("5.0")) == "info"
    assert severity_for_change(Decimal("7.0")) == "warning"
    assert severity_for_change(Decimal("10.1")) == "critical"


def test_alert_message_uses_vietnamese_persona():
    message = format_alert_message("HPG", Decimal("6.5"), Decimal("30000"), "info")

    assert "Bé Tiền" in message
    assert "HPG" in message
    assert "tăng" in message


NOW = datetime(2026, 8, 10, 9, 45, tzinfo=timezone.utc)


def _quote(price: str, *, source: str = "ssi", fetched_at: datetime = NOW) -> PriceQuote:
    return PriceQuote(
        symbol="HPG",
        price=Decimal(price),
        currency="VND",
        asset_type="stock",
        fetched_at=fetched_at,
        source=source,
    )


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def _run_check(baseline: PriceQuote, current: PriceQuote):
    """Run check_movements against a seeded baseline with one eligible holder."""
    redis = FakeAsyncRedis()
    cache = PriceCache(redis)
    await cache.set_last_known(baseline)
    session = _FakeSession()
    holder = MagicMock(id=uuid4(), telegram_id=4242)
    notifier = MagicMock()
    notifier.send_message = AsyncMock(return_value={"ok": True})

    with (
        patch.object(alerts_module, "alerts_enabled", return_value=True),
        patch.object(alerts_module, "get_session_factory", return_value=lambda: session),
        patch.object(
            alerts_module, "_users_holding", AsyncMock(return_value=[(holder, True)])
        ),
        patch.object(alerts_module, "_can_send", AsyncMock(return_value=True)),
        patch.object(alerts_module, "get_notifier", return_value=notifier),
    ):
        sent = await check_movements([current], cache=cache)

    return sent, notifier


@pytest.mark.asyncio
async def test_check_movements_alerts_on_a_live_baseline():
    sent, notifier = await _run_check(
        _quote("30000", fetched_at=NOW - timedelta(minutes=15)), _quote("33000")
    )

    assert len(sent) == 1
    assert sent[0].symbol == "HPG"
    assert sent[0].change_pct == Decimal("10")
    notifier.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_movements_ignores_a_snapshot_baseline():
    # Regression: a market_snapshot baseline is an end-of-day price. Comparing a
    # live quote against it reported an overnight move as "trong 15 phút".
    sent, notifier = await _run_check(
        _quote(
            "30000",
            source=SNAPSHOT_SOURCE,
            fetched_at=NOW - timedelta(days=1),
        ),
        _quote("33000"),
    )

    assert sent == []
    notifier.send_message.assert_not_awaited()
