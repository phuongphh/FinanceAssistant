"""Routing tests for the Phase 4.3 Twin habit-loop callback handler.

Avoids spinning up the worker: we mock ``send_message``, ``answer_callback``,
and the services that hit the DB so the test stays pure-Python while
verifying that the prefix dispatch + payload shape is correct.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.bot.handlers import twin_callback_handler as h
from backend.twin.services.causality_service import CausalityBreakdown
from backend.twin.services.action_suggestion_service import ActionSuggestion
from backend.twin.services.return_tease_service import ReturnTease
from datetime import datetime, timezone


@dataclass
class _Sent:
    chat_id: int
    text: str
    reply_markup: dict | None


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[_Sent] = []
        self.acked: list[str] = []
        self.flushed = False
        self.event_writes: list[object] = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **_):
        self.sent.append(_Sent(chat_id, text, reply_markup))

    async def answer_callback(self, callback_id, text=None, show_alert=False):
        self.acked.append(callback_id)


class _FakeDB:
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    def add(self, obj):
        self._recorder.event_writes.append(obj)

    async def flush(self):
        self._recorder.flushed = True


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(h, "send_message", rec.send_message)
    monkeypatch.setattr(h, "answer_callback", rec.answer_callback)
    return rec


@pytest.fixture
def fake_user():
    return SimpleNamespace(id=uuid4(), telegram_id=42, wealth_level="mass_affluent")


def _callback(data: str, telegram_id: int | None = 42, chat_id: int | None = 7) -> dict:
    return {
        "id": "cb-1",
        "data": data,
        "from": {"id": telegram_id} if telegram_id is not None else {},
        "message": {"chat": {"id": chat_id}} if chat_id is not None else {},
    }


@pytest.mark.asyncio
async def test_unknown_callback_returns_false(recorder):
    assert (
        await h.handle_twin_callback(_FakeDB(recorder), _callback("menu:assets"))
        is False
    )
    assert (
        await h.handle_action_suggestion_callback(
            _FakeDB(recorder), _callback("menu:assets")
        )
        is False
    )
    # Non-matching path doesn't ack the spinner — that's the worker's
    # fallback's job, not ours.
    assert recorder.acked == []


@pytest.mark.asyncio
async def test_twin_causality_renders_breakdown_and_offers_action(
    recorder, fake_user, monkeypatch
):
    breakdown = CausalityBreakdown(
        direction="positive",
        delta_pct=Decimal("1.2"),
        delta_absolute_vnd=Decimal("5000000"),
        factors=(),
        text="Vì sao Twin nhích lên?\n✓ Thêm tiết kiệm (80%)",
        forward_sentence=None,
        show_breakdown=True,
    )

    async def _attribute(_db, _user_id, period_days=7):
        return breakdown

    async def _get_user(_db, _telegram_id):
        return fake_user

    monkeypatch.setattr(h.causality_service, "attribute_delta", _attribute)
    monkeypatch.setattr(h, "get_user_by_telegram_id", _get_user)

    handled = await h.handle_twin_callback(
        _FakeDB(recorder), _callback("twin:causality")
    )

    assert handled is True
    assert recorder.acked == ["cb-1"]
    assert len(recorder.sent) == 1
    sent = recorder.sent[0]
    assert "Vì sao Twin nhích lên" in sent.text
    # Causality answer chains to the action suggestion.
    assert sent.reply_markup is not None
    button = sent.reply_markup["inline_keyboard"][0][0]
    assert button["callback_data"] == "twin:action"


@pytest.mark.asyncio
async def test_twin_causality_no_chain_when_breakdown_silent(
    recorder, fake_user, monkeypatch
):
    silent = CausalityBreakdown(
        direction="stable",
        delta_pct=Decimal("0.0"),
        delta_absolute_vnd=Decimal("0"),
        factors=(),
        text="Twin của anh ổn định tuần này.",
        forward_sentence=None,
        show_breakdown=False,
    )

    async def _attribute(_db, _user_id, period_days=7):
        return silent

    async def _get_user(_db, _telegram_id):
        return fake_user

    monkeypatch.setattr(h.causality_service, "attribute_delta", _attribute)
    monkeypatch.setattr(h, "get_user_by_telegram_id", _get_user)

    await h.handle_twin_callback(_FakeDB(recorder), _callback("twin:causality"))

    assert recorder.sent[0].reply_markup is None


@pytest.mark.asyncio
async def test_twin_action_uses_callback_buttons_not_url(
    recorder, fake_user, monkeypatch
):
    suggestion = ActionSuggestion(
        type="positive_goal",
        title="Cập nhật mục tiêu",
        description="Thêm mốc nhỏ",
        time_estimate_minutes=5,
        deep_link="betien://goals/progress",
        buttons=(),
    )
    breakdown = CausalityBreakdown(
        direction="positive",
        delta_pct=Decimal("1.0"),
        delta_absolute_vnd=Decimal("3000000"),
        factors=(),
        text="",
        forward_sentence=None,
        show_breakdown=True,
    )

    async def _attribute(_db, _user_id, period_days=7):
        return breakdown

    async def _suggest(_db, _user_id, *, state_segment, delta_pct, has_goal):
        return suggestion

    async def _log(_db, _user_id, _event, _suggestion):
        return None

    async def _has_goal(_db, _user_id):
        return True

    async def _get_user(_db, _telegram_id):
        return fake_user

    monkeypatch.setattr(h.causality_service, "attribute_delta", _attribute)
    monkeypatch.setattr(h.action_suggestion_service, "suggest_action", _suggest)
    monkeypatch.setattr(h.action_suggestion_service, "log_action_event", _log)
    monkeypatch.setattr(h, "_has_active_goal", _has_goal)
    monkeypatch.setattr(h, "get_user_by_telegram_id", _get_user)

    await h.handle_twin_callback(_FakeDB(recorder), _callback("twin:action"))

    keyboard = recorder.sent[0].reply_markup["inline_keyboard"][0]
    # Both buttons must be callback_data — using ``url`` with the
    # ``betien://`` deep link would crash the Telegram Bot API.
    assert all("callback_data" in btn and "url" not in btn for btn in keyboard)
    assert any(btn["callback_data"] == "twin:action_done:positive_goal" for btn in keyboard)
    assert any(btn["callback_data"] == "action_suggestion:dismiss:positive_goal" for btn in keyboard)


@pytest.mark.asyncio
async def test_action_done_records_return_tease(recorder, fake_user, monkeypatch):
    tease = ReturnTease(
        confirmation="Tuyệt — Bé Tiền đã ghi nhận 💚",
        tease="Sáng mai mở lại nhé.",
        briefing_tag="twin_check_back_in",
        send_at=datetime(2026, 5, 19, 1, 0, tzinfo=timezone.utc),
    )

    calls: list[tuple] = []

    async def _record(_db, user_id, *, action_title):
        calls.append((user_id, action_title))
        return tease

    async def _get_user(_db, _telegram_id):
        return fake_user

    monkeypatch.setattr(h.return_tease_service, "record_action_completed", _record)
    monkeypatch.setattr(h, "get_user_by_telegram_id", _get_user)

    await h.handle_twin_callback(
        _FakeDB(recorder), _callback("twin:action_done:positive_goal")
    )

    assert calls == [(fake_user.id, "positive_goal")]
    assert "ghi nhận" in recorder.sent[0].text
    assert "Sáng mai" in recorder.sent[0].text


@pytest.mark.asyncio
async def test_dismiss_logs_event_for_30day_suppression(
    recorder, fake_user, monkeypatch
):
    async def _get_user(_db, _telegram_id):
        return fake_user

    monkeypatch.setattr(h, "get_user_by_telegram_id", _get_user)

    db = _FakeDB(recorder)
    handled = await h.handle_action_suggestion_callback(
        db, _callback("action_suggestion:dismiss:negative_review")
    )

    assert handled is True
    assert recorder.flushed is True
    assert len(recorder.event_writes) == 1
    event = recorder.event_writes[0]
    assert event.event_type == "action_suggestion.dismissed"
    assert event.properties == {"suggestion_type": "negative_review"}
    assert "nhắc nhẹ" in recorder.sent[0].text
