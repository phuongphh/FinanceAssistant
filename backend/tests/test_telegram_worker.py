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

def _make_fake_session() -> MagicMock:
    """Async-session double that supports commit/rollback/execute/flush."""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    # Services now flush() instead of commit() (Phase B1).
    session.flush = AsyncMock()
    # route_update issues an UPDATE to stamp user_id before commit —
    # execute must be awaitable.
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    return session


class TestRouteUpdate:
    @pytest.mark.asyncio
    async def test_menu_message_calls_cmd_menu(self):
        """A plain /menu message should trigger the Phase 3.6 menu
        handler. When the message has no ``from`` field the user lookup
        returns None — the handler still renders the (un-personalised)
        main menu so the bot doesn't go silent on edge cases.
        """
        fake_session = _make_fake_session()
        factory = MagicMock(return_value=fake_session)

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ), patch(
            "backend.bot.handlers.menu_handler.cmd_menu",
            new_callable=AsyncMock,
        ) as mock_cmd_menu, patch(
            "backend.bot.handlers.onboarding.handle_onboarding_callback",
            new_callable=AsyncMock,
        ):
            await telegram_worker.route_update(
                {
                    "update_id": 1,
                    "message": {"text": "/menu", "chat": {"id": 123}},
                }
            )

        # Handler is awaited with (db, chat_id, user). User is None here
        # because the message had no ``from`` field for telegram_id.
        mock_cmd_menu.assert_awaited_once()
        args, _ = mock_cmd_menu.await_args
        assert args[1] == 123
        assert args[2] is None
        fake_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stamps_resolved_user_id_on_row(self):
        """After a handler resolves the user, route_update must issue an
        UPDATE on telegram_updates so the row carries user_id for
        per-user replay / audit / deletion (CLAUDE.md §0 multi-tenant
        rule).
        """
        import uuid as _uuid

        resolved_uid = _uuid.uuid4()
        fake_user = MagicMock()
        fake_user.id = resolved_uid
        fake_user.is_onboarded = False
        fake_user.display_name = None
        fake_user.get_greeting_name.return_value = "bạn"

        fake_session = _make_fake_session()
        factory = MagicMock(return_value=fake_session)

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ), patch(
            "backend.services.dashboard_service.get_or_create_user",
            new_callable=AsyncMock, return_value=(fake_user, True),
        ), patch(
            "backend.bot.handlers.onboarding.resume_or_start",
            new_callable=AsyncMock,
        ):
            await telegram_worker.route_update(
                {
                    "update_id": 77,
                    "message": {
                        "text": "/start",
                        "chat": {"id": 123},
                        "from": {"id": 999},
                    },
                }
            )

        # route_update should have issued at least one execute (the UPDATE).
        assert fake_session.execute.await_count >= 1
        fake_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_triggers_rollback(self):
        fake_session = _make_fake_session()
        factory = MagicMock(return_value=fake_session)

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ), patch(
            "backend.bot.handlers.menu_handler.cmd_menu",
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
# _maybe_auto_exit_asset_wizard — UX: button taps that aren't asset_add:*
# clear an active asset-entry wizard so the user isn't trapped on their
# next free-text message.
# ---------------------------------------------------------------------------


def _wizard_user(*, flow: str | None, step: str | None = None) -> MagicMock:
    """Build a fake user with the given wizard_state shape."""
    import uuid as _uuid

    user = MagicMock()
    user.id = _uuid.uuid4()
    user.wizard_state = (
        {"flow": flow, "step": step, "draft": {}} if flow else None
    )
    return user


class TestAutoExitAssetWizard:
    @pytest.mark.asyncio
    async def test_clears_when_callback_is_menu_and_user_in_asset_wizard(self):
        """Menu tap mid asset-wizard → wizard_service.clear() called."""
        user = _wizard_user(flow="asset_add_picker", step="type")
        fake_db = MagicMock()
        dashboard_service = MagicMock()
        dashboard_service.get_user_by_telegram_id = AsyncMock(return_value=user)

        with patch(
            "backend.services.wizard_service.clear", new_callable=AsyncMock
        ) as mock_clear:
            await telegram_worker._maybe_auto_exit_asset_wizard(
                fake_db,
                telegram_id=999,
                callback_data="menu:assets:advisor",
                dashboard_service=dashboard_service,
            )

        mock_clear.assert_awaited_once_with(fake_db, user.id)

    @pytest.mark.asyncio
    async def test_no_clear_for_asset_add_callback(self):
        """asset_add:* callbacks belong to the wizard itself — never clear."""
        user = _wizard_user(flow="asset_add_cash", step="amount")
        fake_db = MagicMock()
        dashboard_service = MagicMock()
        dashboard_service.get_user_by_telegram_id = AsyncMock(return_value=user)

        with patch(
            "backend.services.wizard_service.clear", new_callable=AsyncMock
        ) as mock_clear:
            await telegram_worker._maybe_auto_exit_asset_wizard(
                fake_db,
                telegram_id=999,
                callback_data="asset_add:cancel",
                dashboard_service=dashboard_service,
            )

        mock_clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_clear_when_no_wizard_state(self):
        user = _wizard_user(flow=None)
        fake_db = MagicMock()
        dashboard_service = MagicMock()
        dashboard_service.get_user_by_telegram_id = AsyncMock(return_value=user)

        with patch(
            "backend.services.wizard_service.clear", new_callable=AsyncMock
        ) as mock_clear:
            await telegram_worker._maybe_auto_exit_asset_wizard(
                fake_db,
                telegram_id=999,
                callback_data="menu:assets:advisor",
                dashboard_service=dashboard_service,
            )

        mock_clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_clear_for_storytelling_flow(self):
        """Storytelling state is owned by story:* callbacks and may hold
        unsaved transactions in draft.pending. Don't touch it."""
        user = _wizard_user(flow="storytelling", step="confirm_pending")
        fake_db = MagicMock()
        dashboard_service = MagicMock()
        dashboard_service.get_user_by_telegram_id = AsyncMock(return_value=user)

        with patch(
            "backend.services.wizard_service.clear", new_callable=AsyncMock
        ) as mock_clear:
            await telegram_worker._maybe_auto_exit_asset_wizard(
                fake_db,
                telegram_id=999,
                callback_data="menu:assets:advisor",
                dashboard_service=dashboard_service,
            )

        mock_clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_clear_for_pending_intent_flow(self):
        """intent_pending_action / intent_awaiting_clarify have their own
        TTL + handlers — leave them alone."""
        user = _wizard_user(flow="intent_pending_action")
        fake_db = MagicMock()
        dashboard_service = MagicMock()
        dashboard_service.get_user_by_telegram_id = AsyncMock(return_value=user)

        with patch(
            "backend.services.wizard_service.clear", new_callable=AsyncMock
        ) as mock_clear:
            await telegram_worker._maybe_auto_exit_asset_wizard(
                fake_db,
                telegram_id=999,
                callback_data="menu:assets:advisor",
                dashboard_service=dashboard_service,
            )

        mock_clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clears_for_briefing_callback(self):
        """Tapping a briefing button (e.g. "💎 Thêm tài sản") while mid
        wizard should also exit — the briefing handler will spin up its
        own flow if needed."""
        user = _wizard_user(flow="asset_add_stock", step="ticker")
        fake_db = MagicMock()
        dashboard_service = MagicMock()
        dashboard_service.get_user_by_telegram_id = AsyncMock(return_value=user)

        with patch(
            "backend.services.wizard_service.clear", new_callable=AsyncMock
        ) as mock_clear:
            await telegram_worker._maybe_auto_exit_asset_wizard(
                fake_db,
                telegram_id=999,
                callback_data="briefing:add_asset",
                dashboard_service=dashboard_service,
            )

        mock_clear.assert_awaited_once_with(fake_db, user.id)

    @pytest.mark.asyncio
    async def test_no_clear_when_telegram_id_missing(self):
        """Anonymous callbacks (no `from.id`) can't be tied to a user."""
        fake_db = MagicMock()
        dashboard_service = MagicMock()
        dashboard_service.get_user_by_telegram_id = AsyncMock()

        with patch(
            "backend.services.wizard_service.clear", new_callable=AsyncMock
        ) as mock_clear:
            await telegram_worker._maybe_auto_exit_asset_wizard(
                fake_db,
                telegram_id=None,
                callback_data="menu:main",
                dashboard_service=dashboard_service,
            )

        dashboard_service.get_user_by_telegram_id.assert_not_awaited()
        mock_clear.assert_not_awaited()


# ---------------------------------------------------------------------------
# recover_orphaned_updates — picks up stuck rows at startup.
# ---------------------------------------------------------------------------

def _fake_execute(candidates: list, claim_results: list):
    """Build an execute side_effect that replays a SELECT + N UPDATEs.

    ``candidates`` is what ``SELECT update_id, payload`` should return
    (a list of 2-tuples). ``claim_results`` is a list of booleans, one
    per candidate, indicating whether our worker won the atomic claim
    for that row.
    """
    select_result = MagicMock()
    select_result.all = MagicMock(return_value=candidates)

    update_results = [MagicMock(rowcount=1 if won else 0) for won in claim_results]

    calls = [select_result, *update_results]
    it = iter(calls)

    async def side_effect(stmt, *a, **kw):
        return next(it)

    return side_effect


class TestRecoverOrphanedUpdates:
    @pytest.mark.asyncio
    async def test_claims_and_spawns_task_per_orphan(self):
        """Happy path: this worker wins every claim and schedules all."""
        candidates = [
            (101, {"update_id": 101}),
            (102, {"update_id": 102}),
        ]
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.commit = AsyncMock()
        fake_session.execute = AsyncMock(
            side_effect=_fake_execute(candidates, [True, True])
        )
        factory = MagicMock(return_value=fake_session)

        spawned: list = []

        def fake_create_task(coro):
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
    async def test_skips_rows_lost_to_concurrent_worker(self):
        """Guards the cross-worker duplicate-dispatch bug (Codex P1).

        Two uvicorn workers both scan for orphans; the other worker
        already claimed row 102. Our atomic UPDATE returns rowcount=0
        for that row — we must NOT schedule it.
        """
        candidates = [
            (201, {"update_id": 201}),  # we win
            (202, {"update_id": 202}),  # lost to another worker
        ]
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.commit = AsyncMock()
        fake_session.execute = AsyncMock(
            side_effect=_fake_execute(candidates, [True, False])
        )
        factory = MagicMock(return_value=fake_session)

        spawned: list = []

        def fake_create_task(coro):
            coro.close()
            spawned.append(True)
            return MagicMock()

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ), patch.object(
            telegram_worker.asyncio, "create_task", side_effect=fake_create_task
        ):
            count = await telegram_worker.recover_orphaned_updates()

        assert count == 1
        assert len(spawned) == 1

    @pytest.mark.asyncio
    async def test_no_orphans_returns_zero(self):
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.commit = AsyncMock()
        fake_session.execute = AsyncMock(side_effect=_fake_execute([], []))
        factory = MagicMock(return_value=fake_session)

        with patch.object(
            telegram_worker, "get_session_factory", return_value=factory
        ):
            count = await telegram_worker.recover_orphaned_updates()

        assert count == 0


# ---------------------------------------------------------------------------
# run_recovery_loop — periodic, cancellable.
# ---------------------------------------------------------------------------

class TestRecoveryLoop:
    @pytest.mark.asyncio
    async def test_loop_invokes_recovery_on_interval_and_exits_on_cancel(self):
        """The loop should call recover_orphaned_updates at the configured
        cadence and exit cleanly when cancelled. We use a very short
        interval and a fake recover that signals progress via an event.
        """
        import asyncio as real_asyncio

        calls = real_asyncio.Event()
        call_count = {"n": 0}

        async def fake_recover():
            call_count["n"] += 1
            if call_count["n"] >= 2:
                calls.set()
            return 0

        with patch.object(
            telegram_worker, "recover_orphaned_updates", side_effect=fake_recover
        ):
            task = real_asyncio.create_task(
                telegram_worker.run_recovery_loop(interval_seconds=0)
            )
            await real_asyncio.wait_for(calls.wait(), timeout=2.0)
            task.cancel()
            with pytest.raises(real_asyncio.CancelledError):
                await task

        assert call_count["n"] >= 2

    @pytest.mark.asyncio
    async def test_loop_continues_after_recovery_exception(self):
        """A single failing pass must not kill the loop."""
        import asyncio as real_asyncio

        call_count = {"n": 0}
        done = real_asyncio.Event()

        async def flaky_recover():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("db hiccup")
            if call_count["n"] >= 2:
                done.set()
            return 0

        with patch.object(
            telegram_worker, "recover_orphaned_updates", side_effect=flaky_recover
        ):
            task = real_asyncio.create_task(
                telegram_worker.run_recovery_loop(interval_seconds=0)
            )
            await real_asyncio.wait_for(done.wait(), timeout=2.0)
            task.cancel()
            with pytest.raises(real_asyncio.CancelledError):
                await task

        assert call_count["n"] >= 2
