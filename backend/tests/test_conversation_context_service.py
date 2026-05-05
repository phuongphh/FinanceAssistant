"""Unit tests for the short-term conversation context service.

These tests use plain MagicMock for the DB so they're hermetic — no
PostgreSQL needed. The service is defensively wrapped, so we mainly
assert the truncation, role validation, and TTL filtering logic.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.conversation_context import (
    ROLE_ASSISTANT,
    ROLE_USER,
    ConversationContext,
)
from backend.services import conversation_context_service as svc


def _row(role: str, content: str, *, intent: str | None = None,
         created_at: datetime | None = None) -> ConversationContext:
    return ConversationContext(
        user_id=uuid.uuid4(),
        role=role,
        content=content,
        intent=intent,
        created_at=created_at or datetime.now(timezone.utc),
    )


def _scalars_mock(rows: list) -> MagicMock:
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=rows)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars)
    return result


def _db_with_rows(rows: list) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_mock(rows))
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
class TestSaveMessage:
    async def test_persists_user_message(self):
        db = _db_with_rows([])
        uid = uuid.uuid4()
        await svc.save_message(
            db, user_id=uid, role=ROLE_USER, content="hello",
        )
        db.add.assert_called_once()
        added = db.add.call_args.args[0]
        assert isinstance(added, ConversationContext)
        assert added.user_id == uid
        assert added.role == ROLE_USER
        assert added.content == "hello"

    async def test_truncates_long_content(self):
        db = _db_with_rows([])
        long_text = "x" * (svc.MAX_CONTENT_CHARS + 50)
        await svc.save_message(
            db, user_id=uuid.uuid4(), role=ROLE_ASSISTANT, content=long_text,
        )
        added = db.add.call_args.args[0]
        # Truncation cap is exact: cut to MAX_CONTENT_CHARS-1 chars + the
        # ellipsis marker. Total length matches the cap.
        assert len(added.content) == svc.MAX_CONTENT_CHARS
        assert added.content.endswith("…")

    async def test_skips_empty_content(self):
        db = _db_with_rows([])
        await svc.save_message(
            db, user_id=uuid.uuid4(), role=ROLE_USER, content="",
        )
        await svc.save_message(
            db, user_id=uuid.uuid4(), role=ROLE_USER, content="   ",
        )
        db.add.assert_not_called()

    async def test_skips_unknown_role(self):
        db = _db_with_rows([])
        await svc.save_message(
            db, user_id=uuid.uuid4(), role="system", content="hi",
        )
        db.add.assert_not_called()

    async def test_swallows_db_errors(self):
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock(side_effect=RuntimeError("connection lost"))
        # Must not raise — the service is advisory.
        await svc.save_message(
            db, user_id=uuid.uuid4(), role=ROLE_USER, content="hi",
        )


@pytest.mark.asyncio
class TestGetRecentMessages:
    async def test_returns_chronological_order(self):
        # The query orders DESC; service flips back to ASC.
        newest = _row(ROLE_ASSISTANT, "newest")
        middle = _row(ROLE_USER, "middle")
        oldest = _row(ROLE_ASSISTANT, "oldest")
        db = _db_with_rows([newest, middle, oldest])
        out = await svc.get_recent_messages(db, user_id=uuid.uuid4())
        assert [t.content for t in out] == ["oldest", "middle", "newest"]

    async def test_filters_non_context_rows(self):
        # The mock DB returns whatever it's given for any SELECT.
        # Stray rows must not be turned into context turns.
        valid = _row(ROLE_USER, "valid")
        stray = MagicMock(spec=[])  # has no role/content/intent attrs
        db = _db_with_rows([valid, stray])
        out = await svc.get_recent_messages(db, user_id=uuid.uuid4())
        assert len(out) == 1
        assert out[0].content == "valid"

    async def test_empty_buffer_returns_empty_list(self):
        db = _db_with_rows([])
        out = await svc.get_recent_messages(db, user_id=uuid.uuid4())
        assert out == []

    async def test_zero_limit_short_circuits(self):
        db = MagicMock()
        db.execute = AsyncMock()
        out = await svc.get_recent_messages(
            db, user_id=uuid.uuid4(), limit=0,
        )
        assert out == []
        db.execute.assert_not_called()

    async def test_swallows_db_errors(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("pool exhausted"))
        out = await svc.get_recent_messages(db, user_id=uuid.uuid4())
        assert out == []


class TestFormatHistoryForPrompt:
    def test_renders_user_and_assistant_lines(self):
        history = [
            svc.ConversationTurn(
                role=ROLE_USER, content="tháng trước tôi chi bao nhiêu?",
                intent=None, created_at=datetime.now(timezone.utc),
            ),
            svc.ConversationTurn(
                role=ROLE_ASSISTANT, content="Tổng chi: 15tr.",
                intent=None, created_at=datetime.now(timezone.utc),
            ),
        ]
        out = svc.format_history_for_prompt(history)
        assert "User: tháng trước" in out
        assert "Bé Tiền: Tổng chi" in out

    def test_empty_returns_empty_string(self):
        assert svc.format_history_for_prompt([]) == ""
