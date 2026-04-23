"""Tests for Phase A1 webhook dedup — ``_claim_update`` + webhook shape.

The webhook must:
- Return 200 in a single DB round-trip for the happy path.
- Skip processing (and not enqueue) on a duplicate ``update_id``.
- Still ack malformed updates so Telegram stops retrying.
- Only enqueue a background task when the claim succeeded.

Downstream handler behavior lives in test_telegram_worker.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _close_coro(coro):
    """Stand-in for ``asyncio.create_task`` in tests.

    Closes the passed coroutine so pytest doesn't warn about
    "coroutine was never awaited" — we only care that create_task was
    called, not that the work runs.
    """
    try:
        coro.close()
    except AttributeError:
        pass
    return MagicMock()


# ---------------------------------------------------------------------------
# Unit: _claim_update atomically inserts and returns True/False by rowcount.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claim_update_returns_true_when_row_inserted():
    from backend.routers.telegram import _claim_update

    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    fake_db.commit = AsyncMock()

    claimed = await _claim_update(fake_db, update_id=111, payload={"x": 1})

    assert claimed is True
    fake_db.execute.assert_awaited_once()
    fake_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_update_returns_false_when_duplicate():
    from backend.routers.telegram import _claim_update

    fake_db = MagicMock()
    # Postgres ON CONFLICT DO NOTHING → rowcount 0 when the row already exists.
    fake_db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    fake_db.commit = AsyncMock()

    claimed = await _claim_update(fake_db, update_id=111, payload={"x": 1})

    assert claimed is False


# ---------------------------------------------------------------------------
# Integration: webhook endpoint — verify + claim + enqueue contract.
# ---------------------------------------------------------------------------

class TestWebhookDedup:
    @patch("backend.routers.telegram.asyncio.create_task", side_effect=_close_coro)
    @patch("backend.routers.telegram._claim_update", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_first_time_update_is_claimed_and_enqueued(
        self, mock_settings, mock_claim, mock_create_task
    ):
        mock_settings.telegram_webhook_secret = ""
        mock_claim.return_value = True

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "update_id": 42,
                "message": {"text": "/menu", "chat": {"id": 123}},
            },
        )

        assert resp.status_code == 200
        mock_claim.assert_awaited_once()
        mock_create_task.assert_called_once()

    @patch("backend.routers.telegram.asyncio.create_task", side_effect=_close_coro)
    @patch("backend.routers.telegram._claim_update", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_duplicate_update_is_skipped(
        self, mock_settings, mock_claim, mock_create_task
    ):
        mock_settings.telegram_webhook_secret = ""
        mock_claim.return_value = False  # Already seen

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={
                "update_id": 42,
                "message": {"text": "/menu", "chat": {"id": 123}},
            },
        )

        assert resp.status_code == 200
        mock_claim.assert_awaited_once()
        # The whole point: no background work is scheduled for a retry.
        mock_create_task.assert_not_called()

    @patch("backend.routers.telegram.asyncio.create_task", side_effect=_close_coro)
    @patch("backend.routers.telegram._claim_update", new_callable=AsyncMock)
    @patch("backend.routers.telegram.settings")
    def test_missing_update_id_is_acked_without_work(
        self, mock_settings, mock_claim, mock_create_task
    ):
        mock_settings.telegram_webhook_secret = ""

        resp = client.post(
            "/api/v1/telegram/webhook",
            json={"message": {"text": "hi", "chat": {"id": 1}}},  # no update_id
        )

        assert resp.status_code == 200
        mock_claim.assert_not_awaited()
        mock_create_task.assert_not_called()
