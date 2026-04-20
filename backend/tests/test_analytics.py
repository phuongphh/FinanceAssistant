"""Tests for the analytics module (Issue #31).

The DB-writing half is only exercised by smoke-testing that `track()` never
raises and that `_persist` swallows errors — we don't spin up Postgres here,
so the integration path is covered by the admin SQL/CLI in practice.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

import pytest

from backend import analytics
from backend.analytics import (
    EventType,
    Event_,
    sanitize_properties,
    track,
)


class TestSanitizeProperties:
    def test_drops_pii_keys(self):
        props = {
            "source": "manual",
            "phone": "0912345678",
            "email": "foo@bar.com",
            "message": "secret content",
            "merchant_name": "Phở Bát Đàn",
            "note": "user typed this",
            "content": "body text",
            "text": "x",
            "token": "abc",
            "password": "y",
            "secret": "z",
            "address": "123 abc st",
            "raw_text": "anything",
            "body": "raw",
        }
        clean = sanitize_properties(props)
        assert clean == {"source": "manual"}

    def test_keeps_allowed_keys(self):
        clean = sanitize_properties({
            "button": "del_tx",
            "has_args": True,
            "load_time_ms": 845,
            "from": "food",
            "to": "transport",
        })
        assert clean == {
            "button": "del_tx",
            "has_args": True,
            "load_time_ms": 845,
            "from": "food",
            "to": "transport",
        }

    def test_pii_key_match_is_case_insensitive(self):
        assert sanitize_properties({"Phone": "123"}) == {}
        assert sanitize_properties({"PHONE": "123"}) == {}
        assert sanitize_properties({"userMessage": "x"}) == {}

    def test_truncates_long_strings(self):
        clean = sanitize_properties({"button": "x" * 500})
        assert len(clean["button"]) == 200

    def test_none_input(self):
        assert sanitize_properties(None) == {}

    def test_empty_input(self):
        assert sanitize_properties({}) == {}

    def test_drops_non_json_values(self):
        clean = sanitize_properties({
            "ok": "yes",
            "obj": object(),
            "nested_ok": {"a": 1, "b": [1, 2, 3]},
            "nested_bad": {"func": lambda x: x},
        })
        assert "ok" in clean
        assert "nested_ok" in clean
        assert "obj" not in clean
        assert "nested_bad" not in clean

    def test_drops_non_string_keys(self):
        clean = sanitize_properties({1: "bad", "good": "ok"})
        assert clean == {"good": "ok"}


class TestEventTypeConstants:
    def test_all_seven_events_defined(self):
        names = {
            EventType.BOT_STARTED,
            EventType.TRANSACTION_CREATED,
            EventType.BUTTON_TAPPED,
            EventType.CATEGORY_CHANGED,
            EventType.TRANSACTION_DELETED,
            EventType.MINIAPP_OPENED,
            EventType.MINIAPP_LOADED,
        }
        assert len(names) == 7

    def test_values_are_snake_case_strings(self):
        for attr in dir(EventType):
            if attr.startswith("_"):
                continue
            value = getattr(EventType, attr)
            assert isinstance(value, str)
            assert value == value.lower()
            assert " " not in value


class TestTrackDispatch:
    def test_track_never_raises_without_loop(self):
        """Called from sync context — should not crash even if DB fails."""
        with patch("backend.analytics._persist") as mock_persist:
            # Mock returns a coroutine that fails — verify track() swallows
            async def boom(event):
                raise RuntimeError("db down")
            mock_persist.side_effect = boom
            # Should NOT raise
            track(EventType.BOT_STARTED, properties={"x": 1})

    def test_track_schedules_on_running_loop(self):
        """In async context, track() should fire a task and return immediately."""
        captured: list[Event_] = []

        async def fake_persist(event):
            captured.append(event)

        async def runner():
            with patch("backend.analytics._persist", side_effect=fake_persist):
                uid = uuid.uuid4()
                track(EventType.BUTTON_TAPPED, user_id=uid, properties={"button": "del_tx"})
                # Yield so scheduled task runs
                await asyncio.sleep(0)
                await analytics.flush_pending(timeout=1.0)

        asyncio.run(runner())
        assert len(captured) == 1
        assert captured[0].event_type == EventType.BUTTON_TAPPED
        assert captured[0].properties == {"button": "del_tx"}

    def test_track_sanitizes_properties_before_persist(self):
        captured: list[Event_] = []

        async def fake_persist(event):
            captured.append(event)

        async def runner():
            with patch("backend.analytics._persist", side_effect=fake_persist):
                track(
                    EventType.TRANSACTION_CREATED,
                    properties={"source": "manual", "merchant_name": "leak!", "phone": "x"},
                )
                await asyncio.sleep(0)
                await analytics.flush_pending(timeout=1.0)

        asyncio.run(runner())
        assert captured[0].properties == {"source": "manual"}

    def test_atrack_awaits_persist(self):
        captured: list[Event_] = []

        async def fake_persist(event):
            captured.append(event)

        async def runner():
            with patch("backend.analytics._persist", side_effect=fake_persist):
                await analytics.atrack(
                    EventType.MINIAPP_LOADED,
                    properties={"load_time_ms": 500},
                )

        asyncio.run(runner())
        assert len(captured) == 1
        assert captured[0].properties == {"load_time_ms": 500}
