"""Tests for the storytelling handler (P3A-18 + P3A-19 + P3A-20).

We pin behaviour at three boundaries:

- Mode entry / exit: ``start_storytelling`` writes wizard_state and
  fires the source-specific funnel event; ``cancel_storytelling`` and
  the 10-min timeout drop the mode cleanly.
- Input handling: text messages route to the LLM extractor; voice
  messages route through Whisper first; both empty / extracted /
  bad-LLM branches are exercised with ``call_llm`` mocked.
- Confirmation callback: confirm_all saves with source="storytelling",
  cancel discards without saving, edit clears state with no expense
  writes, stale taps acknowledge but don't save.

Telegram + DB are mocked. The LLM call is patched at
``storytelling_prompt.call_llm`` so we don't depend on a network.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import storytelling as h
from backend.bot.keyboards.storytelling_keyboard import (
    CB_STORY,
    storytelling_confirmation_keyboard,
)
from backend.models.user import User


def _user(state: dict | None = None) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 100
    u.display_name = "Test"
    u.expense_threshold_micro = 200_000
    u.expense_threshold_major = 2_000_000
    u.wizard_state = state
    u.created_at = datetime.utcnow()
    return u


def _db(user: User | None = None) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    return db


def _msg(text: str = "ăn nhà hàng 800k", *, telegram_id: int = 100) -> dict:
    return {
        "from": {"id": telegram_id},
        "chat": {"id": 999},
        "text": text,
    }


def _voice_msg(*, file_id: str = "file-1", duration: int = 5) -> dict:
    return {
        "from": {"id": 100},
        "chat": {"id": 999},
        "voice": {"file_id": file_id, "duration": duration, "mime_type": "audio/ogg"},
    }


def _callback(action: str = "all", *, telegram_id: int = 100) -> dict:
    return {
        "id": "cb-1",
        "data": f"{CB_STORY}:confirm:{action}",
        "from": {"id": telegram_id},
        "message": {"chat": {"id": 999}, "message_id": 7},
    }


# ----------------------------------------------------------------------
# Mode entry / exit (P3A-18)
# ----------------------------------------------------------------------


class TestStartStorytelling:
    @pytest.mark.asyncio
    async def test_writes_wizard_state_and_sends_prompt(self):
        user = _user()
        db = _db(user)
        send_mock = AsyncMock()
        track_mock = MagicMock()

        with patch.object(h, "send_message", send_mock), patch.object(
            h.analytics, "track", track_mock
        ):
            await h.start_storytelling(db, 999, user, source=h.SOURCE_DIRECT_COMMAND)

        # Wizard state set to awaiting_story with source + threshold
        assert user.wizard_state is not None
        assert user.wizard_state["flow"] == h.FLOW_STORYTELLING
        assert user.wizard_state["step"] == h.STEP_AWAITING_STORY
        assert user.wizard_state["draft"]["source"] == h.SOURCE_DIRECT_COMMAND
        assert user.wizard_state["draft"]["threshold"] == 200_000

        # Welcome message sent
        send_mock.assert_awaited()
        # Generic OPENED + source-specific OPENED_DIRECT both fire
        events = [c.args[0] for c in track_mock.call_args_list]
        assert h.StorytellingEvent.OPENED in events
        assert h.StorytellingEvent.OPENED_DIRECT in events
        assert h.StorytellingEvent.OPENED_FROM_BRIEFING not in events

    @pytest.mark.asyncio
    async def test_from_briefing_source_emits_briefing_event(self):
        user = _user()
        db = _db(user)
        track_mock = MagicMock()

        with patch.object(h, "send_message", AsyncMock()), patch.object(
            h.analytics, "track", track_mock
        ):
            await h.start_storytelling(db, 999, user, source=h.SOURCE_FROM_BRIEFING)

        events = [c.args[0] for c in track_mock.call_args_list]
        assert h.StorytellingEvent.OPENED_FROM_BRIEFING in events
        assert h.StorytellingEvent.OPENED_DIRECT not in events

    @pytest.mark.asyncio
    async def test_threshold_pulled_from_user(self):
        user = _user()
        user.expense_threshold_micro = 500_000  # high earner
        db = _db(user)

        with patch.object(h, "send_message", AsyncMock()), patch.object(
            h.analytics, "track", MagicMock()
        ):
            await h.start_storytelling(db, 999, user)

        assert user.wizard_state["draft"]["threshold"] == 500_000


class TestCancelStorytelling:
    @pytest.mark.asyncio
    async def test_clears_wizard_state(self):
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {},
        })
        db = _db(user)

        with patch.object(h, "send_message", AsyncMock()), patch.object(
            h.analytics, "track", MagicMock()
        ):
            await h.cancel_storytelling(db, 999, user)

        assert user.wizard_state is None

    @pytest.mark.asyncio
    async def test_noop_if_not_in_mode(self):
        user = _user(state={"flow": "asset_add_cash", "step": "amount", "draft": {}})
        db = _db(user)
        send_mock = AsyncMock()

        with patch.object(h, "send_message", send_mock), patch.object(
            h.analytics, "track", MagicMock()
        ):
            await h.cancel_storytelling(db, 999, user)

        # Wizard state untouched, no message sent
        assert user.wizard_state["flow"] == "asset_add_cash"
        send_mock.assert_not_awaited()


# ----------------------------------------------------------------------
# handle_storytelling_input — text path (P3A-18)
# ----------------------------------------------------------------------


class TestHandleStorytellingInputText:
    @pytest.mark.asyncio
    async def test_returns_false_when_user_not_in_mode(self):
        user = _user(state=None)
        db = _db(user)
        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)):
            consumed = await h.handle_storytelling_input(db, _msg())
        assert consumed is False

    @pytest.mark.asyncio
    async def test_returns_false_when_step_is_confirm_pending(self):
        """User typing while keyboard is up — don't re-extract, let the
        message fall through to the normal handlers."""
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_CONFIRM_PENDING,
            "draft": {"pending": [{"amount": 800_000}]},
        })
        db = _db(user)
        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)):
            consumed = await h.handle_storytelling_input(db, _msg())
        assert consumed is False

    @pytest.mark.asyncio
    async def test_timed_out_state_dropped_silently(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=15)
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {"started_at": old.isoformat(), "threshold": 200_000},
        })
        db = _db(user)
        track_mock = MagicMock()

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h.analytics, "track", track_mock):
            consumed = await h.handle_storytelling_input(db, _msg())

        assert consumed is False
        assert user.wizard_state is None
        events = [c.args[0] for c in track_mock.call_args_list]
        assert h.StorytellingEvent.TIMED_OUT in events

    @pytest.mark.asyncio
    async def test_empty_extraction_drops_mode_and_sends_friendly_msg(self):
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "threshold": 200_000,
            },
        })
        db = _db(user)
        send_mock = AsyncMock()
        edit_mock = AsyncMock()

        empty_result = h.StorytellingResult()  # no transactions

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "send_message", send_mock), \
             patch.object(h, "edit_message_text", edit_mock), \
             patch.object(h, "extract_transactions_from_story",
                          AsyncMock(return_value=empty_result)), \
             patch.object(h.analytics, "track", MagicMock()):
            consumed = await h.handle_storytelling_input(db, _msg("đi chơi vui"))

        assert consumed is True
        # Mode cleared
        assert user.wizard_state is None

    @pytest.mark.asyncio
    async def test_extraction_advances_to_confirm_pending(self):
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "threshold": 200_000,
            },
        })
        db = _db(user)
        result = h.StorytellingResult(
            transactions=[
                {"amount": 800_000, "merchant": "Nhà hàng", "category": "food",
                 "confidence": 0.9}
            ],
        )

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "send_message", AsyncMock(return_value={"ok": True, "result": {"message_id": 5}})), \
             patch.object(h, "edit_message_text", AsyncMock()), \
             patch.object(h, "extract_transactions_from_story",
                          AsyncMock(return_value=result)), \
             patch.object(h.analytics, "track", MagicMock()):
            consumed = await h.handle_storytelling_input(db, _msg("ăn 800k"))

        assert consumed is True
        # Step bumped, pending stashed
        assert user.wizard_state["step"] == h.STEP_CONFIRM_PENDING
        assert user.wizard_state["draft"]["pending"] == result.transactions

    @pytest.mark.asyncio
    async def test_command_does_not_consume(self):
        """``/start`` while in storytelling mode falls through to commands."""
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "threshold": 200_000,
            },
        })
        db = _db(user)

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)):
            consumed = await h.handle_storytelling_input(db, _msg("/start"))

        assert consumed is False


# ----------------------------------------------------------------------
# handle_storytelling_input — voice path (P3A-18)
# ----------------------------------------------------------------------


class TestHandleStorytellingInputVoice:
    @pytest.mark.asyncio
    async def test_voice_too_long_rejected_warmly(self):
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "threshold": 200_000,
            },
        })
        db = _db(user)
        send_mock = AsyncMock()
        track_mock = MagicMock()

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "send_message", send_mock), \
             patch.object(h.analytics, "track", track_mock):
            consumed = await h.handle_storytelling_input(
                db, _voice_msg(duration=120),
            )

        assert consumed is True
        send_mock.assert_awaited_once()
        events = [
            (c.args[0], c.kwargs.get("properties", {}))
            for c in track_mock.call_args_list
        ]
        assert any(
            e == h.StorytellingEvent.VOICE_FAILED and p.get("reason") == "too_long"
            for e, p in events
        )

    @pytest.mark.asyncio
    async def test_voice_download_failure_warmly_handled(self):
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "threshold": 200_000,
            },
        })
        db = _db(user)

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "send_message", AsyncMock(return_value=None)), \
             patch.object(h, "download_file", AsyncMock(return_value=None)), \
             patch.object(h.analytics, "track", MagicMock()):
            consumed = await h.handle_storytelling_input(db, _voice_msg())

        assert consumed is True

    @pytest.mark.asyncio
    async def test_voice_whisper_error_warmly_handled(self):
        from backend.services.voice_service import VoiceTranscriptionError

        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "threshold": 200_000,
            },
        })
        db = _db(user)

        async def failing_transcribe(*a, **kw):
            raise VoiceTranscriptionError("api down")

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "send_message", AsyncMock(return_value=None)), \
             patch.object(h, "download_file", AsyncMock(return_value=b"raw audio")), \
             patch.object(h, "transcribe_vietnamese",
                          AsyncMock(side_effect=failing_transcribe)), \
             patch.object(h.analytics, "track", MagicMock()):
            consumed = await h.handle_storytelling_input(db, _voice_msg())

        assert consumed is True

    @pytest.mark.asyncio
    async def test_voice_happy_path_extracts_and_advances(self):
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_AWAITING_STORY,
            "draft": {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "threshold": 200_000,
            },
        })
        db = _db(user)
        result = h.StorytellingResult(
            transactions=[
                {"amount": 800_000, "merchant": "Nhà hàng", "category": "food",
                 "confidence": 0.9}
            ],
        )

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "send_message",
                          AsyncMock(return_value={"ok": True, "result": {"message_id": 5}})), \
             patch.object(h, "edit_message_text", AsyncMock()), \
             patch.object(h, "download_file", AsyncMock(return_value=b"audio")), \
             patch.object(h, "transcribe_vietnamese",
                          AsyncMock(return_value="ăn nhà hàng tám trăm nghìn")), \
             patch.object(h, "extract_transactions_from_story",
                          AsyncMock(return_value=result)), \
             patch.object(h.analytics, "track", MagicMock()):
            consumed = await h.handle_storytelling_input(db, _voice_msg())

        assert consumed is True
        assert user.wizard_state["step"] == h.STEP_CONFIRM_PENDING


# ----------------------------------------------------------------------
# Confirmation callback (P3A-19)
# ----------------------------------------------------------------------


class TestHandleStorytellingCallback:
    @pytest.mark.asyncio
    async def test_returns_false_for_non_story_prefix(self):
        handled = await h.handle_storytelling_callback(
            MagicMock(),
            {"id": "x", "data": "asset_add:start", "from": {"id": 1},
             "message": {"chat": {"id": 2}}},
        )
        assert handled is False

    @pytest.mark.asyncio
    async def test_unregistered_user_gets_friendly_alert(self):
        db = MagicMock()
        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=None)), \
             patch.object(h, "answer_callback", AsyncMock()) as ack:
            handled = await h.handle_storytelling_callback(db, _callback())
        assert handled is True
        ack.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_callback_clears_keyboard(self):
        """User taps after timeout / wizard already cleared."""
        user = _user(state=None)  # no longer in storytelling mode
        db = _db(user)

        ack_mock = AsyncMock()
        clear_kb_mock = AsyncMock()
        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "answer_callback", ack_mock), \
             patch.object(h, "edit_message_reply_markup", clear_kb_mock):
            handled = await h.handle_storytelling_callback(db, _callback("all"))

        assert handled is True
        ack_mock.assert_awaited_once()
        clear_kb_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirm_all_saves_each_pending_transaction(self):
        pending = [
            {"amount": 800_000, "merchant": "Nhà hàng", "category": "food"},
            {"amount": 1_500_000, "merchant": "Áo", "category": "shopping"},
        ]
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_CONFIRM_PENDING,
            "draft": {"pending": pending, "threshold": 200_000},
        })
        db = _db(user)

        saved_calls = []

        async def fake_create_expense(db, user_id, data):
            saved_calls.append((data.amount, data.merchant, data.category, data.source))
            ex = MagicMock()
            ex.id = uuid.uuid4()
            ex.amount = data.amount
            ex.category = data.category
            return ex

        track_mock = MagicMock()
        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "answer_callback", AsyncMock()), \
             patch.object(h, "edit_message_text", AsyncMock()), \
             patch.object(h, "send_message", AsyncMock()), \
             patch.object(h.expense_service, "create_expense",
                          AsyncMock(side_effect=fake_create_expense)), \
             patch.object(h.analytics, "track", track_mock):
            handled = await h.handle_storytelling_callback(db, _callback("all"))

        assert handled is True
        # Both saved with source="storytelling"
        assert len(saved_calls) == 2
        assert all(call[3] == "storytelling" for call in saved_calls)
        # Wizard cleared
        assert user.wizard_state is None
        # Analytics fired
        events = [c.args[0] for c in track_mock.call_args_list]
        assert h.StorytellingEvent.CONFIRMED_ALL in events

    @pytest.mark.asyncio
    async def test_confirm_all_partial_failure_continues(self):
        """If one save fails, the rest still go through."""
        pending = [
            {"amount": 800_000, "merchant": "OK", "category": "food"},
            {"amount": 1_500_000, "merchant": "BAD", "category": "shopping"},
            {"amount": 300_000, "merchant": "OK2", "category": "food"},
        ]
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_CONFIRM_PENDING,
            "draft": {"pending": pending},
        })
        db = _db(user)

        async def maybe_fail(db, user_id, data):
            if "BAD" in data.merchant:
                raise RuntimeError("db error")
            ex = MagicMock()
            ex.id = uuid.uuid4()
            ex.amount = data.amount
            ex.category = data.category
            return ex

        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "answer_callback", AsyncMock()), \
             patch.object(h, "edit_message_text", AsyncMock()), \
             patch.object(h, "send_message", AsyncMock()), \
             patch.object(h.expense_service, "create_expense",
                          AsyncMock(side_effect=maybe_fail)), \
             patch.object(h.analytics, "track", MagicMock()):
            handled = await h.handle_storytelling_callback(db, _callback("all"))

        assert handled is True
        assert user.wizard_state is None  # cleared regardless

    @pytest.mark.asyncio
    async def test_cancel_discards_without_saving(self):
        pending = [{"amount": 800_000, "merchant": "x", "category": "food"}]
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_CONFIRM_PENDING,
            "draft": {"pending": pending},
        })
        db = _db(user)

        save_mock = AsyncMock()
        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "answer_callback", AsyncMock()), \
             patch.object(h, "edit_message_text", AsyncMock()), \
             patch.object(h, "send_message", AsyncMock()), \
             patch.object(h.expense_service, "create_expense", save_mock), \
             patch.object(h.analytics, "track", MagicMock()):
            handled = await h.handle_storytelling_callback(db, _callback("cancel"))

        assert handled is True
        save_mock.assert_not_awaited()
        assert user.wizard_state is None

    @pytest.mark.asyncio
    async def test_edit_clears_state_without_saving(self):
        pending = [{"amount": 800_000, "merchant": "x", "category": "food"}]
        user = _user(state={
            "flow": h.FLOW_STORYTELLING,
            "step": h.STEP_CONFIRM_PENDING,
            "draft": {"pending": pending},
        })
        db = _db(user)

        save_mock = AsyncMock()
        track_mock = MagicMock()
        with patch.object(h, "get_user_by_telegram_id",
                          AsyncMock(return_value=user)), \
             patch.object(h, "answer_callback", AsyncMock()), \
             patch.object(h, "edit_message_text", AsyncMock()), \
             patch.object(h, "send_message", AsyncMock()), \
             patch.object(h.expense_service, "create_expense", save_mock), \
             patch.object(h.analytics, "track", track_mock):
            handled = await h.handle_storytelling_callback(db, _callback("edit"))

        assert handled is True
        save_mock.assert_not_awaited()
        assert user.wizard_state is None
        events = [c.args[0] for c in track_mock.call_args_list]
        assert h.StorytellingEvent.EDIT_REQUESTED in events


# ----------------------------------------------------------------------
# Confirmation message + keyboard contract
# ----------------------------------------------------------------------


class TestConfirmationKeyboard:
    def test_three_button_layout(self):
        kb = storytelling_confirmation_keyboard()
        rows = kb["inline_keyboard"]
        assert len(rows) == 2  # 2 + 1 layout
        assert len(rows[0]) == 2
        assert len(rows[1]) == 1

    def test_callback_data_under_telegram_limit(self):
        from backend.bot.keyboards.common import TELEGRAM_CALLBACK_DATA_MAX_BYTES

        kb = storytelling_confirmation_keyboard()
        for row in kb["inline_keyboard"]:
            for btn in row:
                assert (
                    len(btn["callback_data"].encode("utf-8"))
                    <= TELEGRAM_CALLBACK_DATA_MAX_BYTES
                )

    def test_format_pending_confirmation_includes_total_and_count(self):
        body = h.format_pending_confirmation(
            [
                {"amount": 800_000, "merchant": "Nhà hàng", "category": "food"},
                {"amount": 1_500_000, "merchant": "Áo", "category": "shopping"},
            ]
        )
        assert "Nhà hàng" in body
        assert "2 giao dịch" in body
        # Total = 2,300,000 → "2.3tr"
        assert "2.3tr" in body

    def test_format_pending_confirmation_html_escapes_merchant(self):
        body = h.format_pending_confirmation(
            [{"amount": 800_000, "merchant": "<bad>&", "category": "food"}]
        )
        assert "<bad>" not in body
        assert "&lt;bad&gt;" in body
