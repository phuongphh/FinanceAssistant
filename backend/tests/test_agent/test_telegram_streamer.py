"""TelegramStreamer unit tests — buffering, flushing, overflow,
graceful degradation when Telegram API is unavailable."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.agent.streaming import TelegramStreamer
from backend.agent.streaming.telegram_streamer import (
    PLACEHOLDER_TEXT,
    TELEGRAM_MAX_MESSAGE_LEN,
    _split_for_overflow,
)


def _ok_send_message():
    """Mock that returns a successful sendMessage response with a stable id."""
    return AsyncMock(
        return_value={"ok": True, "result": {"message_id": 42}}
    )


def _ok_edit_message():
    return AsyncMock(return_value={"ok": True})


@pytest.mark.asyncio
class TestStartLifecycle:
    async def test_start_sends_typing_and_placeholder(self):
        send = _ok_send_message()
        edit = _ok_edit_message()
        action = AsyncMock(return_value={"ok": True})

        s = TelegramStreamer(
            chat_id=123,
            send_message=send,
            edit_message_text=edit,
            send_chat_action=action,
        )
        await s.start()

        action.assert_awaited_once_with(123, "typing")
        send.assert_awaited_once()
        # Placeholder is the first arg to send_message after chat_id.
        assert send.call_args.args[1] == PLACEHOLDER_TEXT
        assert s._active is not None
        assert s._active.message_id == 42

    async def test_start_idempotent(self):
        send = _ok_send_message()
        s = TelegramStreamer(
            chat_id=1, send_message=send,
            edit_message_text=AsyncMock(),
            send_chat_action=AsyncMock(),
        )
        await s.start()
        await s.start()
        # send_message called only once despite two start()s.
        assert send.await_count == 1

    async def test_start_degrades_when_send_returns_none(self):
        s = TelegramStreamer(
            chat_id=1,
            send_message=AsyncMock(return_value=None),
            edit_message_text=AsyncMock(),
            send_chat_action=AsyncMock(),
        )
        await s.start()
        # Active not set when placeholder send fails — degraded mode.
        assert s._active is None


@pytest.mark.asyncio
class TestBufferingAndFlush:
    async def test_small_chunks_buffer_no_edit(self):
        send = _ok_send_message()
        edit = _ok_edit_message()
        s = TelegramStreamer(
            chat_id=1,
            min_chunk_chars=100,
            flush_interval=0.0,
            send_message=send,
            edit_message_text=edit,
            send_chat_action=AsyncMock(),
        )
        await s.start()

        # Small chunks well under the threshold.
        await s.send_chunk("hi ")
        await s.send_chunk("there")

        # No edit triggered yet (buffer 8 < 100).
        edit.assert_not_awaited()
        assert s._buffer == "hi there"

    async def test_finish_flushes_remaining(self):
        send = _ok_send_message()
        edit = _ok_edit_message()
        s = TelegramStreamer(
            chat_id=1,
            min_chunk_chars=1000,
            flush_interval=0.0,
            send_message=send,
            edit_message_text=edit,
            send_chat_action=AsyncMock(),
        )
        await s.start()
        await s.send_chunk("a tiny answer")
        # Below threshold — no edit yet.
        edit.assert_not_awaited()

        await s.finish()
        edit.assert_awaited()  # final flush
        # The active message text now includes the buffer.
        text_arg = edit.await_args.args[2]
        assert "a tiny answer" in text_arg

    async def test_threshold_triggers_edit(self):
        send = _ok_send_message()
        edit = _ok_edit_message()
        s = TelegramStreamer(
            chat_id=1,
            min_chunk_chars=10,
            flush_interval=0.0,
            send_message=send,
            edit_message_text=edit,
            send_chat_action=AsyncMock(),
        )
        await s.start()
        await s.send_chunk("12345678901234567890")  # 20 chars > 10
        edit.assert_awaited()


@pytest.mark.asyncio
class TestOverflow:
    async def test_split_helper_splits_at_newline(self):
        text = "a" * 50 + "\n" + "b" * 50
        head, tail = _split_for_overflow(text, head_max=70)
        assert head.endswith("\n")
        assert "b" * 50 == tail

    async def test_split_helper_hard_split_when_no_newline(self):
        text = "a" * 100
        head, tail = _split_for_overflow(text, head_max=40)
        assert len(head) == 40
        assert head + tail == text

    async def test_overflow_opens_new_message(self):
        # Use a large send_chunk that exceeds the message limit.
        send = AsyncMock(side_effect=[
            {"ok": True, "result": {"message_id": 1}},  # placeholder
            {"ok": True, "result": {"message_id": 2}},  # overflow
        ])
        edit = _ok_edit_message()
        s = TelegramStreamer(
            chat_id=1,
            min_chunk_chars=1,
            flush_interval=0.0,
            send_message=send,
            edit_message_text=edit,
            send_chat_action=AsyncMock(),
        )
        await s.start()

        big_text = "x" * (TELEGRAM_MAX_MESSAGE_LEN + 100)
        await s.send_chunk(big_text)
        await s.finish()

        # send_message called twice: placeholder + overflow placeholder.
        assert send.await_count == 2
        # edit called for both messages (head into msg 1, tail into msg 2).
        assert edit.await_count >= 2
        edited_ids = {c.args[1] for c in edit.await_args_list}
        assert edited_ids == {1, 2}


@pytest.mark.asyncio
class TestEditFailureFallback:
    async def test_edit_failure_falls_back_to_send(self):
        send = AsyncMock(
            side_effect=[
                # Placeholder
                {"ok": True, "result": {"message_id": 7}},
                # Fallback fresh message
                {"ok": True, "result": {"message_id": 8}},
            ]
        )
        # First edit fails (returns None), second wouldn't be reached.
        edit = AsyncMock(return_value=None)
        s = TelegramStreamer(
            chat_id=1,
            min_chunk_chars=1,
            flush_interval=0.0,
            send_message=send,
            edit_message_text=edit,
            send_chat_action=AsyncMock(),
        )
        await s.start()
        await s.send_chunk("hello world")  # triggers flush

        # Fallback send_message used since edit failed.
        assert send.await_count == 2  # placeholder + fallback
        # Fallback's text is the rendered content (not placeholder).
        fallback_text = send.await_args_list[1].args[1]
        assert "hello world" in fallback_text


@pytest.mark.asyncio
class TestFlushIntervalRespected:
    async def test_consecutive_flushes_dont_spam(self):
        # When flush_interval is positive and time hasn't passed,
        # subsequent send_chunks should buffer rather than re-edit.
        loop = asyncio.get_event_loop()
        send = _ok_send_message()
        edit = _ok_edit_message()
        s = TelegramStreamer(
            chat_id=1,
            min_chunk_chars=5,
            flush_interval=10.0,
            send_message=send,
            edit_message_text=edit,
            send_chat_action=AsyncMock(),
        )
        await s.start()

        await s.send_chunk("first chunk over 5 chars")
        # First flush happens (last_flush_at was 0).
        assert edit.await_count == 1
        # Second chunk should NOT flush — interval not elapsed.
        await s.send_chunk("second chunk")
        assert edit.await_count == 1  # still only one
