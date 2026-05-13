from __future__ import annotations

from dataclasses import dataclass
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend import analytics
from backend.bot.keyboards.common import build_callback
from backend.models.positioning_survey import (
    ALIGNED_POSITIONING_RESPONSES,
    MISALIGNED_POSITIONING_RESPONSES,
    PositioningSurveyResponse,
    VALID_POSITIONING_RESPONSES,
)

SURVEY_PATH = Path(__file__).resolve().parents[3] / "content" / "survey" / "positioning_survey.yaml"
DEFAULT_SOURCE_PROMPT_ID = "post_onboarding_day_7"


@dataclass(frozen=True)
class PositioningSurveyOption:
    key: str
    label: str
    order: int
    aligned: bool


@dataclass(frozen=True)
class PositioningSurveyCopy:
    question: str
    ack: str
    duplicate_ack: str
    callback_prefix: str
    target_aligned_percent: int
    alert_misaligned_percent: int
    minimum_responses_for_alert: int
    options: tuple[PositioningSurveyOption, ...]


def load_copy(path: Path = SURVEY_PATH) -> PositioningSurveyCopy:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    options = tuple(
        sorted(
            (
                PositioningSurveyOption(
                    key=key,
                    label=str(value["label"]),
                    order=int(value["order"]),
                    aligned=bool(value.get("aligned", False)),
                )
                for key, value in (data.get("options") or {}).items()
            ),
            key=lambda item: item.order,
        )
    )
    return PositioningSurveyCopy(
        question=str(data["question"]),
        ack=str(data["ack"]),
        duplicate_ack=str(data.get("duplicate_ack") or data["ack"]),
        callback_prefix=str(data.get("callback_prefix") or "positioning_survey"),
        target_aligned_percent=int(data.get("target_aligned_percent", 60)),
        alert_misaligned_percent=int(data.get("alert_misaligned_percent", 30)),
        minimum_responses_for_alert=int(data.get("minimum_responses_for_alert", 20)),
        options=options,
    )


def survey_keyboard(copy: PositioningSurveyCopy | None = None) -> dict[str, Any]:
    copy = copy or load_copy()
    return {
        "inline_keyboard": [
            [
                {
                    "text": option.label,
                    "callback_data": build_callback(copy.callback_prefix, option.key),
                }
            ]
            for option in copy.options
        ]
    }


def append_question(message: str, copy: PositioningSurveyCopy | None = None) -> str:
    copy = copy or load_copy()
    return f"{message.rstrip()}\n\n{copy.question}"


async def has_response(db: AsyncSession, user_id) -> bool:
    existing = (
        await db.execute(
            select(PositioningSurveyResponse.id)
            .where(PositioningSurveyResponse.user_id == user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return existing is not None


async def record_response(
    db: AsyncSession,
    user_id,
    response: str,
    *,
    source_prompt_id: str | None = DEFAULT_SOURCE_PROMPT_ID,
) -> bool:
    """Insert one positioning response.

    Returns True for a new row and False if the user already answered.
    The database UNIQUE(user_id) constraint is enforced with an
    INSERT .. ON CONFLICT DO NOTHING, so duplicate taps do not throw and
    do not force a transaction rollback.
    """
    if response not in VALID_POSITIONING_RESPONSES:
        raise ValueError(f"unknown positioning response: {response!r}")
    stmt = (
        insert(PositioningSurveyResponse)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            response=response,
            source_prompt_id=source_prompt_id,
            created_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    result = await db.execute(stmt)
    inserted = (getattr(result, "rowcount", 0) or 0) > 0
    if not inserted:
        return False

    analytics.track(
        "positioning_survey_response",
        user_id=user_id,
        properties={
            "response": response,
            "aligned": response in ALIGNED_POSITIONING_RESPONSES,
        },
    )
    return True


@dataclass(frozen=True)
class PositioningKPI:
    counts: dict[str, int]
    total: int
    aligned_percent: float
    misaligned_percent: float
    target_aligned_percent: int
    alert_misaligned_percent: int
    minimum_responses_for_alert: int

    @property
    def should_alert(self) -> bool:
        return (
            self.total >= self.minimum_responses_for_alert
            and self.misaligned_percent > self.alert_misaligned_percent
        )


async def kpi_snapshot(db: AsyncSession) -> PositioningKPI:
    copy = load_copy()
    rows = (
        await db.execute(
            select(PositioningSurveyResponse.response, func.count())
            .group_by(PositioningSurveyResponse.response)
        )
    ).all()
    counts = {option.key: 0 for option in copy.options}
    counts.update({response: int(count) for response, count in rows})
    total = sum(counts.values())
    aligned = sum(counts.get(key, 0) for key in ALIGNED_POSITIONING_RESPONSES)
    misaligned = sum(counts.get(key, 0) for key in MISALIGNED_POSITIONING_RESPONSES)
    return PositioningKPI(
        counts=counts,
        total=total,
        aligned_percent=(aligned / total * 100) if total else 0.0,
        misaligned_percent=(misaligned / total * 100) if total else 0.0,
        target_aligned_percent=copy.target_aligned_percent,
        alert_misaligned_percent=copy.alert_misaligned_percent,
        minimum_responses_for_alert=copy.minimum_responses_for_alert,
    )
