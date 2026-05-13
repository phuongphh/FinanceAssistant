from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.bot.handlers import twin_handler


class FakeNotifier:
    def __init__(self):
        self.messages = []
        self.photos = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))

    async def send_photo(self, chat_id, photo, **kwargs):
        self.photos.append((chat_id, photo, kwargs))


class FakeUser:
    id = uuid.uuid4()
    display_name = "An"

    def get_greeting_name(self):
        return "An"


@pytest.mark.asyncio
async def test_twin_handler_empty_state_uses_notifier(monkeypatch):
    async def fake_snapshot(db, user_id):
        return SimpleNamespace(
            actual_nw=Decimal("9000000"),
            projection=None,
            latest_cone=None,
            cone_age_days=None,
            is_stale=True,
            delta_vs_p50=None,
        )

    monkeypatch.setattr(
        twin_handler.twin_query_service, "get_twin_snapshot", fake_snapshot
    )
    notifier = FakeNotifier()

    await twin_handler.send_twin_current(
        object(), chat_id=123, user=FakeUser(), notifier=notifier
    )

    assert notifier.photos == []
    assert "tối thiểu 10tr" in notifier.messages[0][1]


@pytest.mark.asyncio
async def test_twin_handler_sends_photo_with_cone_caption(monkeypatch):
    cone = [
        {"year": 0, "p10": "100000000", "p50": "100000000", "p90": "100000000"},
        {"year": 10, "p10": "150000000", "p50": "220000000", "p90": "350000000"},
    ]

    async def fake_snapshot(db, user_id):
        return SimpleNamespace(
            actual_nw=Decimal("100000000"),
            projection=SimpleNamespace(cone_data=cone),
            latest_cone=cone,
            cone_age_days=2,
            is_stale=False,
            delta_vs_p50=Decimal("0"),
        )

    async def fake_latest(db, user_id, scenario=None):
        return None

    async def fake_narrative(db, user, cone_data, cone_age_days=None):
        return "Mình theo dõi vùng này để bạn điều chỉnh nhẹ nhàng khi cần."

    monkeypatch.setattr(
        twin_handler.twin_query_service, "get_twin_snapshot", fake_snapshot
    )
    monkeypatch.setattr(
        twin_handler.twin_query_service, "get_latest_projection", fake_latest
    )
    monkeypatch.setattr(
        twin_handler, "render_projection_chart", lambda cone, optimal=None: b"png-bytes"
    )
    monkeypatch.setattr(twin_handler, "build_twin_narrative", fake_narrative)
    notifier = FakeNotifier()

    await twin_handler.send_twin_current(
        object(), chat_id=123, user=FakeUser(), notifier=notifier
    )

    assert notifier.messages == []
    assert notifier.photos[0][1] == b"png-bytes"
    caption = notifier.photos[0][2]["caption"]
    assert "có thể nằm trong khoảng 150tr — 350tr" in caption
    assert "cập nhật 2 ngày trước" in caption


@pytest.mark.asyncio
async def test_compare_optimal_uses_content_renderer(monkeypatch):
    from backend.ports.content_renderer import ChannelContent

    cone_current = [
        {"year": 0, "p10": "100000000", "p50": "100000000", "p90": "100000000"},
        {"year": 10, "p10": "150000000", "p50": "220000000", "p90": "350000000"},
    ]
    cone_optimal = [
        {"year": 0, "p10": "100000000", "p50": "100000000", "p90": "100000000"},
        {"year": 10, "p10": "180000000", "p50": "300000000", "p90": "450000000"},
    ]
    current = SimpleNamespace(
        cone_data=cone_current,
        monthly_savings=Decimal("10000000"),
        allocation_snapshot={
            "stocks_vn": Decimal("0.5"),
            "cash_savings": Decimal("0.5"),
        },
        base_net_worth=Decimal("100000000"),
    )
    optimal = SimpleNamespace(
        cone_data=cone_optimal,
        monthly_savings=Decimal("11000000"),
        allocation_snapshot={
            "stocks_vn": Decimal("0.6"),
            "cash_savings": Decimal("0.4"),
        },
    )

    async def fake_latest(db, user_id, scenario=None):
        if scenario == twin_handler.twin_projection_service.SCENARIO_OPTIMAL:
            return optimal
        return current

    class FakeRenderer:
        def __init__(self):
            self.snapshot = None

        def render_twin_comparison(self, snapshot):
            self.snapshot = snapshot
            return ChannelContent(
                text="rendered comparison",
                images=(b"comparison-png",),
                buttons=(),
                filename=snapshot.filename,
            )

    monkeypatch.setattr(
        twin_handler.twin_query_service, "get_latest_projection", fake_latest
    )
    notifier = FakeNotifier()
    renderer = FakeRenderer()

    await twin_handler.send_twin_compare_optimal(
        object(), chat_id=123, user=FakeUser(), notifier=notifier, renderer=renderer
    )

    assert renderer.snapshot is not None
    assert renderer.snapshot.current_p50 == Decimal("220000000")
    assert renderer.snapshot.optimal_p50 == Decimal("300000000")
    assert notifier.photos[0][1] == b"comparison-png"
    assert notifier.photos[0][2]["caption"] == "rendered comparison"
