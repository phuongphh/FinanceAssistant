"""Tests for the new step 6 (FIRST_ASSET) in onboarding (P3A-9).

Verifies:
- step_5_aha_moment now transitions to AHA_MOMENT (not COMPLETED)
- complete_onboarding routes into step_6_first_asset (not finalisation)
- step_6_first_asset prompts with the 4-button keyboard
- skip → onboarding_skipped_asset=True + onboarding_completed_at set
- note_first_asset_added_if_needed completes onboarding only when on FIRST_ASSET
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import onboarding as onboarding_handlers
from backend.bot.personality.onboarding_flow import OnboardingStep
from backend.models.user import User


def _user(step: OnboardingStep = OnboardingStep.FIRST_TRANSACTION) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.telegram_id = 100
    u.display_name = "Trang"
    u.onboarding_step = int(step)
    u.onboarding_completed_at = None
    u.onboarding_skipped = False
    u.onboarding_skipped_asset = False
    u.created_at = datetime.now(timezone.utc)
    return u


def _db(user: User | None = None) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_step5_no_longer_finalises_onboarding():
    user = _user(OnboardingStep.FIRST_TRANSACTION)
    db = _db(user)
    with patch.object(onboarding_handlers, "send_message", AsyncMock()), \
         patch.object(onboarding_handlers.onboarding_service, "set_step",
                      AsyncMock()) as set_step, \
         patch.object(onboarding_handlers.onboarding_service, "mark_completed",
                      AsyncMock()) as mark_completed:
        await onboarding_handlers.step_5_aha_moment(db, 100, user)

    set_step.assert_awaited_once()
    # User is parked at AHA_MOMENT, not COMPLETED.
    assert set_step.await_args.args[2] == OnboardingStep.AHA_MOMENT
    mark_completed.assert_not_awaited()
    assert user.onboarding_completed_at is None


@pytest.mark.asyncio
async def test_complete_onboarding_routes_into_step_6():
    user = _user(OnboardingStep.AHA_MOMENT)
    db = _db(user)
    with patch.object(onboarding_handlers, "send_message", AsyncMock()), \
         patch.object(onboarding_handlers, "edit_message_text", AsyncMock()), \
         patch.object(onboarding_handlers, "answer_callback", AsyncMock()), \
         patch.object(onboarding_handlers.onboarding_service, "set_step",
                      AsyncMock()) as set_step, \
         patch.object(onboarding_handlers.onboarding_service, "mark_completed",
                      AsyncMock()) as mark_completed:
        await onboarding_handlers.complete_onboarding(
            db, 100, message_id=1, callback_id="cb1", user=user,
        )
    # Routed into step 6 — sets the FIRST_ASSET step.
    set_step.assert_awaited_once()
    assert set_step.await_args.args[2] == OnboardingStep.FIRST_ASSET
    mark_completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_first_asset_finalises_onboarding():
    user = _user(OnboardingStep.FIRST_ASSET)
    db = _db(user)
    with patch.object(onboarding_handlers, "send_message", AsyncMock()), \
         patch.object(onboarding_handlers, "edit_message_text", AsyncMock()), \
         patch.object(onboarding_handlers, "answer_callback", AsyncMock()), \
         patch.object(onboarding_handlers.onboarding_service, "mark_completed",
                      AsyncMock()) as mark_completed:
        await onboarding_handlers.handle_first_asset_choice(
            db, 100, message_id=1, callback_id="cb1", user=user, choice="skip",
        )
    assert user.onboarding_skipped_asset is True
    mark_completed.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_asset_choice_cash_routes_to_wizard():
    user = _user(OnboardingStep.FIRST_ASSET)
    db = _db(user)
    with patch.object(onboarding_handlers, "send_message", AsyncMock()), \
         patch.object(onboarding_handlers, "edit_message_text", AsyncMock()), \
         patch.object(onboarding_handlers, "answer_callback", AsyncMock()):
        # Patch the wizard module that gets imported lazily.
        import backend.bot.handlers.asset_entry as asset_entry
        with patch.object(asset_entry, "_start_cash_subtype_pick",
                          AsyncMock()) as starter:
            await onboarding_handlers.handle_first_asset_choice(
                db, 100, message_id=1, callback_id="cb1", user=user,
                choice="cash",
            )
    starter.assert_awaited_once()


@pytest.mark.asyncio
async def test_note_first_asset_added_finalises_when_on_step_6():
    user = _user(OnboardingStep.FIRST_ASSET)
    db = _db(user)
    with patch.object(onboarding_handlers.onboarding_service, "mark_completed",
                      AsyncMock()) as mark_completed:
        await onboarding_handlers.note_first_asset_added_if_needed(db, user)
    mark_completed.assert_awaited_once()


@pytest.mark.asyncio
async def test_note_first_asset_added_noop_when_already_complete():
    user = _user(OnboardingStep.COMPLETED)
    db = _db(user)
    with patch.object(onboarding_handlers.onboarding_service, "mark_completed",
                      AsyncMock()) as mark_completed:
        await onboarding_handlers.note_first_asset_added_if_needed(db, user)
    mark_completed.assert_not_awaited()
