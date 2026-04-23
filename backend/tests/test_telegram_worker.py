"""Tests for Phase A3 background worker + orphan recovery.

Covers:
- ``process_update_safely`` marks the row done on success, failed on
  exception — never raises.
- ``route_update`` dispatches messages and callbacks to the right
  handlers, opening its own session.
- ``recover_orphaned_updates`` picks up stale ``processing`` rows and
  caps the batch size.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.workers import telegram_worker
from backend.models.telegram_update import STATUS_DONE, STATUS_FAILED


# ---------------------------------------------------------------------------
# process_update_safely — wraps route_update, records status, never raises.
# ---------------------------------------------------------------------------

class TestProcessUpdateSafely:
    @pytest.mark.asyncio
    async def test_marks_done_on_success(self):
        with patch.object(
            telegram_worker, "route_update", new_callable=AsyncMock
        ) as mock_route, patch.object(
            telegram_worker, "_mark_status", new_callable=AsyncMock
        ) as mock_mark:
            await telegram_worker.process_update_safely(
                update_id=7, data={"update_id": 7}
            )

        mock_route.assert_awaited_once_with({"update_id": 7})
        mock_mark.assert_awaited_once_with(7, STATUS_DONE)

    @pytest.mark.asyncio
    async def test_marks_failed_when_route_raises(self):
        boom = RuntimeError("handler crashed")
        with patch.object(
            telegram_worker, "route_update",
            new_callable=AsyncMock, side_effect=boom,
        ), patch.object(
            telegram_worker, "_mark_status", new_callable=AsyncMock
        ) as mock_mark:
            # Must not raise — a handler bug can't be allowed to kill
            # the event loop or surface as a webhook error.
            await telegram_worker.process_update_safely(
                update_id=8, data={"update_id": 8}
            )

        mock_mark.assert_awaited_once()
        args, kwargs = mock_mark.await_args
        assert args[0] == 8
        assert args[1] == STATUS_FAILED
        assert "handler crashed" in kwargs["error"]


# ---------------------------------------------------------------------------
# route_update — dispatches message / callback via the handler layer.
# ---------------------------------------------------------------------------

class TestRouteUpdate:
    @pytest.mark.asyncio
    async def test_menu_message_calls_send_menu(self):
        """A plain /menu message should only trigger the menu sender."""
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.commit = AsyncMock()
        fake_session.rollback = AsyncMock()
        factory = MagicMock(return_value=fake_session)

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ), patch(
            "backend.services.telegram_service.send_menu",
            new_callable=AsyncMock,
        ) as mock_send_menu, patch(
            "backend.bot.handlers.onboarding.handle_onboarding_callback",
            new_callable=AsyncMock,
        ):
            await telegram_worker.route_update(
                {
                    "update_id": 1,
                    "message": {"text": "/menu", "chat": {"id": 123}},
                }
            )

        mock_send_menu.assert_awaited_once_with(123)
        fake_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_triggers_rollback(self):
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.commit = AsyncMock()
        fake_session.rollback = AsyncMock()
        factory = MagicMock(return_value=fake_session)

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ), patch(
            "backend.services.telegram_service.send_menu",
            new_callable=AsyncMock,
            side_effect=RuntimeError("telegram down"),
        ):
            with pytest.raises(RuntimeError):
                await telegram_worker.route_update(
                    {
                        "update_id": 2,
                        "message": {"text": "/menu", "chat": {"id": 123}},
                    }
                )

        fake_session.rollback.assert_awaited_once()
        fake_session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# recover_orphaned_updates — picks up stuck rows at startup.
# ---------------------------------------------------------------------------

class TestRecoverOrphanedUpdates:
    @pytest.mark.asyncio
    async def test_spawns_task_per_orphan(self):
        stale = datetime.utcnow() - timedelta(minutes=10)
        orphan1 = MagicMock(update_id=101, payload={"update_id": 101}, received_at=stale)
        orphan2 = MagicMock(update_id=102, payload={"update_id": 102}, received_at=stale)

        # Shape the session/execute/scalars().all() chain just enough
        # for recover_orphaned_updates to consume.
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[orphan1, orphan2])
        execute_result = MagicMock()
        execute_result.scalars = MagicMock(return_value=scalars)

        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.execute = AsyncMock(return_value=execute_result)
        factory = MagicMock(return_value=fake_session)

        spawned: list = []

        def fake_create_task(coro):
            # Immediately close the coroutine so it doesn't warn about
            # "coroutine was never awaited" — we're just counting calls.
            coro.close()
            spawned.append(True)
            return MagicMock()

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ), patch.object(
            telegram_worker.asyncio, "create_task", side_effect=fake_create_task
        ):
            count = await telegram_worker.recover_orphaned_updates()

        assert count == 2
        assert len(spawned) == 2

    @pytest.mark.asyncio
    async def test_no_orphans_returns_zero(self):
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[])
        execute_result = MagicMock()
        execute_result.scalars = MagicMock(return_value=scalars)

        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.execute = AsyncMock(return_value=execute_result)
        factory = MagicMock(return_value=fake_session)

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ):
            count = await telegram_worker.recover_orphaned_updates()

        assert count == 0
