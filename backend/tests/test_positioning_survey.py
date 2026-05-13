from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.handlers import positioning_survey as handler
from backend.feedback.services.prompt_scheduler import FeedbackPrompt, PromptScheduler
from backend.models.user import User
from backend.services.survey import positioning_survey_service as service


def _result(value=None, rows=None, rowcount=0):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.all.return_value = rows or []
    result.rowcount = rowcount
    return result


def _user() -> User:
    user = User()
    user.id = uuid.uuid4()
    user.telegram_id = 123
    user.is_active = True
    return user


@pytest.mark.asyncio
async def test_record_response_inserts_once():
    user_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(rowcount=1))

    inserted = await service.record_response(db, user_id, "personal_cfo")

    assert inserted is True
    stmt = db.execute.await_args.args[0]
    assert "ON CONFLICT" in str(stmt)


@pytest.mark.asyncio
async def test_record_response_duplicate_returns_false_without_insert():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(rowcount=0))

    inserted = await service.record_response(db, uuid.uuid4(), "unclear")

    assert inserted is False


def test_survey_keyboard_has_four_options_and_short_callbacks():
    keyboard = service.survey_keyboard()

    rows = keyboard["inline_keyboard"]
    assert [row[0]["text"] for row in rows] == [
        "📊 App quản lý chi tiêu",
        "🤖 Trợ lý tài chính cá nhân",
        "🔮 Công cụ nhìn tương lai tài chính",
        "🤔 Chưa hiểu rõ",
    ]
    assert all(len(row[0]["callback_data"].encode("utf-8")) <= 64 for row in rows)


@pytest.mark.asyncio
async def test_positioning_callback_records_and_acknowledges():
    user = _user()
    db = MagicMock()

    with patch.object(handler.dashboard_service, "get_user_by_telegram_id", AsyncMock(return_value=user)), \
         patch.object(handler.positioning_survey_service, "record_response", AsyncMock(return_value=True)) as record, \
         patch.object(handler, "answer_callback", AsyncMock()) as answer:
        handled = await handler.handle_positioning_survey_callback(
            db,
            {
                "id": "cb1",
                "data": "positioning_survey:future_tool",
                "from": {"id": 123},
            },
        )

    assert handled is True
    record.assert_awaited_once_with(db, user.id, "future_tool")
    assert "Cảm ơn" in answer.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_day7_prompt_uses_positioning_survey_keyboard():
    user = _user()
    prompt = FeedbackPrompt(
        id="post_onboarding_day_7",
        trigger="account_age_days == 7",
        message="Day 7 follow-up",
        cta_button="CTA",
        skip_button="Skip",
        cooldown_days=60,
    )
    scheduler = PromptScheduler([prompt])
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    with patch.object(PromptScheduler, "_within_prompt_cooldown", AsyncMock(return_value=False)), \
         patch.object(PromptScheduler, "_hit_monthly_rate_limit", AsyncMock(return_value=False)), \
         patch.object(PromptScheduler, "_metrics", AsyncMock(return_value={"account_age_days": 7})), \
         patch("backend.feedback.services.prompt_scheduler.ContextSnapshotService") as snapshot_cls, \
         patch("backend.feedback.services.prompt_scheduler.send_telegram", AsyncMock()) as send:
        snapshot_cls.return_value.capture = AsyncMock(return_value={})
        await scheduler._send_prompt(db, user, prompt, {"account_age_days": 7})

    payload = send.await_args.args[1]
    assert "Day 7 follow-up" in payload["text"]
    assert "Bé Tiền tò mò" in payload["text"]
    assert payload["reply_markup"]["inline_keyboard"][1][0]["callback_data"] == "positioning_survey:personal_cfo"


@pytest.mark.asyncio
async def test_kpi_snapshot_calculates_alignment_and_alert():
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_result(
            rows=[
                ("expense_tracker", 8),
                ("personal_cfo", 6),
                ("future_tool", 6),
                ("unclear", 2),
            ]
        )
    )

    snapshot = await service.kpi_snapshot(db)

    assert snapshot.total == 22
    assert round(snapshot.aligned_percent) == 55
    assert round(snapshot.misaligned_percent) == 45
    assert snapshot.should_alert is True
